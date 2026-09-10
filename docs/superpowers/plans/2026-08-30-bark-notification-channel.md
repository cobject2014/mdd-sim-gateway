# Bark Notification Channel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an encrypted, first-class Bark notification channel that forwards each incoming SMS with the receiving SIM's own number and the SMS text to iOS.

**Architecture:** Put Bark URL validation, receiver-centric formatting, encryption, HTTP delivery, and response validation in a new provider module. Keep existing event ingestion unchanged; add only small registration wrappers in the notification coordinator, settings API, and notification page, with the Bark UI in its own component.

**Tech Stack:** Python 3, FastAPI, requests, cryptography, React 18, Vite, Node test runner, Python unittest.

**Spec:** `docs/superpowers/specs/2026-08-30-bark-notification-channel-design.md`

## Global Constraints

- Default Bark forwarding is enabled only for `incoming_sms`; every other existing event starts disabled.
- Default SMS content contains the receiving line's `msisdn` and `text`, never the remote sender in place of the receiving number.
- Receiver fallback order is `msisdn`, `sim_name`, `iccid`, `instance`, then `SIM`.
- Encryption is AES-128-CBC with PKCS#7 padding and is enabled by default for new Bark configurations.
- Encryption failure must fail closed; no code path may retry a failed encrypted delivery as plaintext.
- Bark secrets and SMS content must not be written to application logs, delivery history, or support bundles.
- TLS verification defaults to enabled. HTTP is accepted only as an explicit administrator choice for a self-hosted service.
- Do not change SMS ingestion, IMS, VoWiFi, modem, cellular-radio, flight-mode, or engine-container behavior.
- Keep provider implementation and UI presentation in new files; shared files receive registration-only changes where practical.
- Do not copy SimAdmin Rust source. Implement Bark's documented HTTP contract in the existing Python/React architecture.

---

### Task 1: Independent Bark Provider Adapter

**Files:**
- Create: `control/app/notification_channels/__init__.py`
- Create: `control/app/notification_channels/bark.py`
- Create: `tests/test_bark_channel.py`

**Interfaces:**
- Consumes: a configuration `dict` and an enriched canonical payload `dict` containing `event`, `msisdn`, `sim_name`, `iccid`, `instance`, `text`, `title`, and `content`.
- Produces: `validate_config(config: dict) -> None`, `default_message(payload: dict) -> dict[str, str]`, `build_request(config: dict, payload: dict) -> tuple[str, dict, dict]`, and `send(config: dict, payload: dict) -> dict`.

- [ ] **Step 1: Write failing URL, message, and encryption tests**

Create `tests/test_bark_channel.py` with focused tests like:

```python
import base64
import json
import unittest
from unittest.mock import MagicMock, patch

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.padding import PKCS7

from control.app.notification_channels import bark


class BarkChannelTests(unittest.TestCase):
    def test_default_sms_uses_receiving_number_and_text_not_sender(self):
        message = bark.default_message({
            "event": "incoming_sms", "msisdn": "+15413006437",
            "from": "+13322692937", "text": "verification 123456",
            "sim_name": "Tello", "iccid": "8901", "instance": "1",
        })
        self.assertIn("+15413006437", message["title"])
        self.assertIn("收件号码: +15413006437", message["content"])
        self.assertIn("verification 123456", message["content"])
        self.assertNotIn("+13322692937", message["content"])

    def test_receiver_identity_falls_back_without_msisdn(self):
        for payload, expected in (
            ({"sim_name": "Work SIM"}, "Work SIM"),
            ({"iccid": "89010002"}, "89010002"),
            ({"instance": "3"}, "3"),
            ({}, "SIM"),
        ):
            self.assertIn(expected, bark.default_message({
                "event": "incoming_sms", "text": "hello", **payload,
            })["title"])

    def test_encrypted_request_round_trips_and_contains_no_plaintext(self):
        config = {
            "push_url": "https://api.day.app/device-secret",
            "encryption": {"enabled": True, "algorithm": "aes-128-cbc",
                           "key": "0123456789ABCDEF", "iv": "FEDCBA9876543210"},
        }
        url, body, _kwargs = bark.build_request(config, {
            "title": "MDD · 收到短信 · +15413006437",
            "content": "收件号码: +15413006437\n\n短信内容:\nprivate body",
        })
        encoded = json.dumps(body, ensure_ascii=False)
        self.assertEqual(url, config["push_url"])
        self.assertNotIn("private body", encoded)
        decryptor = Cipher(algorithms.AES(b"0123456789ABCDEF"),
                           modes.CBC(b"FEDCBA9876543210")).decryptor()
        padded = decryptor.update(base64.b64decode(body["ciphertext"])) + decryptor.finalize()
        unpadder = PKCS7(128).unpadder()
        decoded = json.loads((unpadder.update(padded) + unpadder.finalize()).decode())
        self.assertEqual(decoded["body"], "收件号码: +15413006437\n\n短信内容:\nprivate body")

    def test_invalid_encryption_never_builds_plaintext(self):
        with self.assertRaisesRegex(ValueError, "16 UTF-8 bytes"):
            bark.build_request({
                "push_url": "https://api.day.app/device-secret",
                "encryption": {"enabled": True, "key": "short", "iv": "also-short"},
            }, {"title": "secret", "content": "private body"})

    def test_url_rejects_credentials_query_fragment_and_empty_key(self):
        for url in (
            "ftp://api.day.app/key",
            "https://user:password@api.day.app/key",
            "https://api.day.app/key?copy=1",
            "https://api.day.app/key#fragment",
            "https://api.day.app/",
        ):
            with self.subTest(url=url), self.assertRaises(ValueError):
                bark.validate_config({"push_url": url, "encryption": {"enabled": False}})
```

- [ ] **Step 2: Run the adapter tests and verify the expected import failure**

Run:

```bash
python -m unittest tests.test_bark_channel -v
```

Expected: FAIL because `control.app.notification_channels.bark` does not exist.

- [ ] **Step 3: Implement the isolated adapter**

Create the package marker and implement `bark.py` without importing FastAPI, configuration persistence, SMS storage, AMI, or device modules. Use this structure:

```python
from __future__ import annotations

import base64
import json
from urllib.parse import urlsplit

import requests
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.padding import PKCS7

TIMEOUT_SECONDS = 8
LEVELS = {"active", "timeSensitive", "critical", "passive"}


def _push_url(config: dict) -> str:
    value = str(config.get("push_url") or "").strip()
    parsed = urlsplit(value)
    if (parsed.scheme not in {"http", "https"} or not parsed.hostname
            or parsed.username is not None or parsed.password is not None
            or parsed.query or parsed.fragment or parsed.path.strip("/") == ""):
        raise ValueError("Bark push URL is invalid")
    return value.rstrip("/")


def validate_config(config: dict) -> None:
    if not isinstance(config, dict):
        raise ValueError("Bark configuration must be an object")
    _push_url(config)
    level = str(config.get("level") or "active")
    if level not in LEVELS:
        raise ValueError("Bark notification level is invalid")
    encryption = config.get("encryption") or {}
    if encryption.get("enabled", True):
        if str(encryption.get("algorithm") or "aes-128-cbc") != "aes-128-cbc":
            raise ValueError("Bark encryption algorithm is unsupported")
        for field in ("key", "iv"):
            if len(str(encryption.get(field) or "").encode("utf-8")) != 16:
                raise ValueError(f"Bark encryption {field} must be 16 UTF-8 bytes")


def _receiver(payload: dict) -> str:
    return str(payload.get("msisdn") or payload.get("sim_name")
               or payload.get("iccid") or payload.get("instance") or "SIM")


def default_message(payload: dict) -> dict[str, str]:
    receiver = _receiver(payload)
    return {
        "title": f"MDD · 收到短信 · {receiver}",
        "content": f"收件号码: {receiver}\n\n短信内容:\n{payload.get('text') or ''}",
    }
```

`build_request` must produce a plaintext Bark body with `title`, `body`, and optional `group`, `sound`, and `level`, then replace that whole body with `{"ciphertext": base64_text}` when encryption is enabled. Use compact UTF-8 JSON, PKCS#7 padding, and AES-128-CBC. Return request kwargs containing `timeout=8` and `verify=config.get("verify_tls", True)`.

`send` must create a `requests.Session`, set `trust_env = False`, POST JSON, call `raise_for_status`, accept Bark's documented success code `200`, and raise only sanitized errors:

```python
def send(config: dict, payload: dict) -> dict:
    url, body, kwargs = build_request(config, payload)
    session = requests.Session()
    session.trust_env = False
    try:
        response = session.post(url, json=body, **kwargs)
        response.raise_for_status()
        try:
            result = response.json()
        except ValueError:
            result = None
        if isinstance(result, dict) and "code" in result and str(result["code"]) != "200":
            raise RuntimeError("Bark rejected the notification")
        return {"ok": True, "status_code": response.status_code}
    except requests.RequestException:
        raise RuntimeError("Bark request failed") from None
    finally:
        session.close()
```

- [ ] **Step 4: Add provider response and sanitized-error tests**

Add tests that patch `requests.Session`, confirm `trust_env` is false, confirm `verify_tls` is passed, accept `{"code": 200}`, reject `{"code": 400}`, and assert exceptions contain none of the device key, SMS body, receiver number, key, IV, or response body.

- [ ] **Step 5: Run the adapter tests**

Run:

```bash
python -m unittest tests.test_bark_channel -v
```

Expected: all Bark adapter tests PASS.

- [ ] **Step 6: Commit the independent provider**

```bash
git add control/app/notification_channels tests/test_bark_channel.py
git commit -m "feat(notify): add isolated Bark provider"
```

---

### Task 2: Register Bark in Configuration and Notification Dispatch

**Files:**
- Modify: `control/app/config.py:107-145,288-299`
- Modify: `control/app/notify_push.py:172-176,332-341,611-630`
- Modify: `tests/test_notify_push.py`
- Modify: `tests/test_bark_channel.py`

**Interfaces:**
- Consumes: Task 1's `bark.validate_config`, `bark.default_message`, and `bark.send`.
- Produces: `settings.bark`, `notify_push.send_bark(config, payload) -> dict`, and Bark participation in `has_enabled_channel` and `dispatch`.

- [ ] **Step 1: Write failing default-merge and dispatch tests**

Add tests with exact expectations:

```python
def test_bark_defaults_only_enable_incoming_sms(self):
    bark_cfg = config.DEFAULTS["settings"]["bark"]
    self.assertTrue(bark_cfg["encryption"]["enabled"])
    self.assertTrue(bark_cfg["events"][notify_push.EV_INCOMING_SMS])
    self.assertFalse(bark_cfg["events"][notify_push.EV_INCOMING_CALL])
    self.assertFalse(bark_cfg["events"][notify_push.EV_MISSED_CALL])


def test_bark_send_applies_receiver_message_and_templates(self):
    payload = notify_push.build_payload(
        notify_push.EV_INCOMING_SMS,
        {"id": "1", "name": "Tello", "msisdn": "+15413006437"},
        "+13322692937", "hello")
    with patch("control.app.notify_push.bark.send", return_value={"ok": True}) as send:
        notify_push.send_bark({"message_templates": {
            notify_push.EV_INCOMING_SMS: {"title": "Line {{msisdn}}"}
        }}, payload)
    enriched = send.call_args.args[1]
    self.assertEqual(enriched["title"], "Line +15413006437")
    self.assertIn("收件号码: +15413006437", enriched["content"])
    self.assertNotIn("+13322692937", enriched["content"])


def test_dispatch_calls_bark_only_for_enabled_events(self):
    settings = {"bark": {"enabled": True, "events": {
        notify_push.EV_INCOMING_SMS: True,
        notify_push.EV_INCOMING_CALL: False,
    }}}
    with patch("control.app.notify_push._deliver_with_retry") as deliver:
        notify_push.dispatch(settings, notify_push.EV_INCOMING_SMS,
                             {"id": "1", "msisdn": "+15413006437"},
                             "+13322692937", "hello")
        deliver.assert_called_once()
        self.assertEqual(deliver.call_args.args[0], "bark")
```

- [ ] **Step 2: Run the focused tests and verify missing Bark registration failures**

Run:

```bash
python -m unittest tests.test_notify_push tests.test_bark_channel -v
```

Expected: new tests FAIL because `settings.bark` and `notify_push.send_bark` are absent.

- [ ] **Step 3: Add Bark defaults and merge behavior**

Add `settings.bark` next to existing channels in `config.py` using the exact configuration contract from the spec. Add `bark` to the notification-channel merge loop and merge `encryption` one level below the channel so saved configurations from earlier versions retain new encryption defaults:

```python
for key in ("webhook", "telegram", "pushplus", "bark"):
    saved = data.get("settings", {}).get(key, {}) or {}
    merged = {**DEFAULTS["settings"][key], **saved}
    merged["events"] = {**DEFAULTS["settings"][key]["events"],
                        **(saved.get("events", {}) or {})}
    if key == "bark":
        merged["encryption"] = {**DEFAULTS["settings"][key]["encryption"],
                                **(saved.get("encryption", {}) or {})}
```

- [ ] **Step 4: Add the narrow coordinator wrapper**

Import the provider module without moving existing channel code:

```python
from .notification_channels import bark
```

Extend `build_notification_message` with an optional `default` argument while preserving every current caller:

```python
def build_notification_message(payload: dict, cfg: dict | None = None,
                               default: dict | None = None) -> dict:
    base = default if default is not None else _default_notification_message(payload)
    return _render_notification_message(payload, cfg or {}, base)
```

Add the provider wrapper:

```python
def send_bark(cfg: dict, payload: dict) -> dict:
    default = (bark.default_message(payload)
               if payload.get("event") == EV_INCOMING_SMS
               else _default_notification_message(payload))
    message = build_notification_message(payload, cfg, default=default)
    return bark.send(cfg, {**payload, **message})
```

Add `bark` to `has_enabled_channel`, then add one dispatch branch using the existing retry wrapper:

```python
bark_cfg = settings.get("bark") or {}
if bark_cfg.get("enabled") and _events_enabled(bark_cfg).get(event):
    _deliver_with_retry("bark", send_bark, bark_cfg, payload)
```

- [ ] **Step 5: Run coordinator and configuration tests**

Run:

```bash
python -m unittest tests.test_notify_push tests.test_bark_channel -v
```

Expected: all focused tests PASS and all existing Webhook, Telegram, and PushPlus assertions remain unchanged.

- [ ] **Step 6: Commit channel registration**

```bash
git add control/app/config.py control/app/notify_push.py tests/test_notify_push.py tests/test_bark_channel.py
git commit -m "feat(notify): register Bark SMS delivery"
```

---

### Task 3: Settings Validation, Test Endpoint, and Secret Redaction

**Files:**
- Modify: `control/app/main.py:4008-4025,4160-4204`
- Modify: `control/app/operations.py:20-55`
- Modify: `tests/test_bark_channel.py`
- Modify: `tests/test_operations.py:78-100,167-190`

**Interfaces:**
- Consumes: `notify_push.send_bark`, `notify_push.validate_message_templates`, and `bark.validate_config` from Tasks 1-2.
- Produces: `POST /api/notifications/bark/test` and support-bundle redaction for `bark.push_url`, `bark.encryption.key`, and `bark.encryption.iv`.

- [ ] **Step 1: Write failing settings, endpoint, and redaction tests**

Add tests that:

```python
def test_bark_settings_secrets_are_redacted(self):
    value = operations.redact({"bark": {
        "push_url": "https://api.day.app/device-secret",
        "encryption": {"key": "0123456789ABCDEF", "iv": "FEDCBA9876543210"},
        "group": "MDD SMS",
    }})
    self.assertEqual(value["bark"]["push_url"], "<redacted>")
    self.assertEqual(value["bark"]["encryption"]["key"], "<redacted>")
    self.assertEqual(value["bark"]["encryption"]["iv"], "<redacted>")
    self.assertEqual(value["bark"]["group"], "MDD SMS")
```

Patch `notify_push.send_bark` and call `asyncio.run(main.api_bark_test(body))`; assert `_test_event` is removed, the synthetic incoming-SMS payload contains a receiving `msisdn`, and invalid config raises HTTP 400 without embedding the push URL or keys in `detail`.

- [ ] **Step 2: Run focused tests and verify endpoint/redaction failures**

Run:

```bash
python -m unittest tests.test_bark_channel tests.test_operations -v
```

Expected: new tests FAIL because the endpoint and Bark path redaction are absent.

- [ ] **Step 3: Validate Bark on settings save**

Add `bark` to the existing message-template validation loop. When `body["bark"]["enabled"]` is true, call `bark.validate_config` and convert any `ValueError` to a generic HTTP 400 message that names the invalid field class but never includes its value:

```python
bark_cfg = body.get("bark") or {}
if bark_cfg.get("enabled"):
    try:
        bark.validate_config(bark_cfg)
    except ValueError as exc:
        raise HTTPException(400, f"invalid Bark configuration: {exc}") from None
```

- [ ] **Step 4: Add the test endpoint**

Follow the existing provider-test convention:

```python
@app.post("/api/notifications/bark/test")
async def api_bark_test(body: dict):
    try:
        event = _notification_test_event(body)
        bark.validate_config(body)
        return await asyncio.to_thread(notify_push.send_bark, body,
                                       _test_push_payload(event))
    except Exception as exc:
        log.warning("Bark test failed: %s", type(exc).__name__)
        raise HTTPException(400, "Bark test delivery failed") from None
```

Do not log `repr(exc)` and do not return provider response bodies.

- [ ] **Step 5: Add explicit Bark path redaction**

Keep generic `key` and `iv` names usable elsewhere by making the rule path-specific:

```python
if "bark" in path and key in {"push_url", "key", "iv"}:
    return True
```

Extend the support-bundle fixture with Bark secrets and assert none appear in the archive.

- [ ] **Step 6: Run API and redaction tests**

Run:

```bash
python -m unittest tests.test_bark_channel tests.test_operations -v
```

Expected: all focused tests PASS.

- [ ] **Step 7: Commit the API and security boundary**

```bash
git add control/app/main.py control/app/operations.py tests/test_bark_channel.py tests/test_operations.py
git commit -m "feat(api): configure and test Bark securely"
```

---

### Task 4: Independent Bark Settings Card

**Files:**
- Create: `webui/src/barkConfig.js`
- Create: `webui/src/views/BarkNotificationCard.jsx`
- Create: `webui/test/bark-config.test.js`
- Create: `tests/test_ui_bark_notification.py`
- Modify: `webui/src/api.js:87-91`
- Modify: `webui/src/views/UnifiedPages.jsx:1-8,590-607`
- Modify: `webui/src/i18n.jsx:289,446-447`
- Modify: `tests/test_ui_notification_templates.py`

**Interfaces:**
- Consumes: `api.testBark(config)`, existing `MessageTemplateEditor`, existing event-option renderer, `showToast`, and the `bark` settings object.
- Produces: `BarkNotificationCard` and `generateBarkEncryptionMaterial(cryptoProvider) -> {key: string, iv: string}`.

- [ ] **Step 1: Write failing pure-JS generator tests**

Create `webui/test/bark-config.test.js`:

```javascript
import assert from 'node:assert/strict'
import test from 'node:test'
import { generateBarkEncryptionMaterial } from '../src/barkConfig.js'

test('generates two independent 16-character ASCII values', () => {
  let seed = 0
  const cryptoProvider = { getRandomValues(bytes) {
    for (let i = 0; i < bytes.length; i += 1) bytes[i] = seed++
    return bytes
  } }
  const generated = generateBarkEncryptionMaterial(cryptoProvider)
  assert.equal(generated.key.length, 16)
  assert.equal(generated.iv.length, 16)
  assert.notEqual(generated.key, generated.iv)
  assert.match(generated.key + generated.iv, /^[A-Za-z0-9]+$/)
})
```

Create `tests/test_ui_bark_notification.py` that reads the independent component and parent source and asserts:

- `BarkNotificationCard.jsx` exists and contains password fields for push URL, key, and IV;
- it contains encryption, TLS, notification-level, group, sound, test, and plaintext-warning controls;
- it uses `api.testBark`;
- `UnifiedPages.jsx` imports and renders `<BarkNotificationCard` rather than embedding Bark fields inline;
- the template and event callbacks are passed from the parent;
- the subtitle names Bark alongside existing channels.

- [ ] **Step 2: Run frontend and source-contract tests and verify failures**

Run:

```bash
cd webui
npm test
cd ..
python -m unittest tests.test_ui_bark_notification tests.test_ui_notification_templates -v
```

Expected: FAIL because the helper, component, API method, and registration do not exist.

- [ ] **Step 3: Implement cryptographic material generation**

Create `webui/src/barkConfig.js` with no React dependency:

```javascript
const ALPHABET = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789'

function randomText(length, cryptoProvider) {
  const bytes = cryptoProvider.getRandomValues(new Uint8Array(length))
  return Array.from(bytes, value => ALPHABET[value % ALPHABET.length]).join('')
}

export function generateBarkEncryptionMaterial(cryptoProvider = globalThis.crypto) {
  if (!cryptoProvider?.getRandomValues) throw new Error('Secure random generation is unavailable')
  return { key: randomText(16, cryptoProvider), iv: randomText(16, cryptoProvider) }
}
```

- [ ] **Step 4: Implement the independent Bark card**

Create `BarkNotificationCard.jsx` with props:

```jsx
export default function BarkNotificationCard({
  config, onPatch, renderEventOptions, MessageTemplateEditor, showToast, t,
}) { /* controlled fields only */ }
```

The component must:

- update nested encryption without replacing sibling encryption fields;
- generate the key and IV only when the user clicks Generate;
- render the push URL, key, and IV as `type="password"`;
- explain that encrypted mode requires identical values in Bark;
- show a strong plaintext warning only when encryption is disabled;
- call `api.testBark({ ...config, _test_event: event })` from template tests and `api.testBark(config)` from the main test button;
- never print the push URL, key, or IV into the DOM outside their masked input values.

- [ ] **Step 5: Register the API and card with minimal parent changes**

Add:

```javascript
testBark: (config) => j('POST', '/api/notifications/bark/test', config || {}),
```

In `NotificationsPage`, add `const barkCfg = s.bark || {}` and render the component once. Pass callbacks that reuse the parent settings state, template editor, and event checkbox logic. Do not move or reformat existing Webhook, Telegram, or PushPlus cards.

Update `tests/test_ui_notification_templates.py` so the outbound channel list and test-method list include `Bark` and `testBark` while leaving all existing channel checks intact.

- [ ] **Step 6: Add Chinese and English labels**

Add translations for Bark push URL, encrypted push, encryption key, IV, Generate, group, sound, notification level, TLS validation, setup explanation, and plaintext warning. Update the notification page subtitle to `Webhook、Telegram、PushPlus、Bark 和投递状态` in Chinese and its English equivalent.

- [ ] **Step 7: Run frontend tests and production build**

Run:

```bash
cd webui
npm test
npm run build
cd ..
python -m unittest tests.test_ui_bark_notification tests.test_ui_notification_templates -v
```

Expected: Node tests PASS, Python UI contract tests PASS, and Vite production build exits 0.

- [ ] **Step 8: Commit the independent UI**

```bash
git add webui/src/barkConfig.js webui/src/views/BarkNotificationCard.jsx webui/test/bark-config.test.js webui/src/api.js webui/src/views/UnifiedPages.jsx webui/src/i18n.jsx tests/test_ui_bark_notification.py tests/test_ui_notification_templates.py
git commit -m "feat(webui): add isolated Bark notification settings"
```

---

### Task 5: Documentation, Full Verification, Push, and Safe Deployment

**Files:**
- Modify: `docs/TROUBLESHOOTING.md`
- Modify: `docs/RELEASE_CHECKLIST.md`

**Interfaces:**
- Consumes: completed Bark backend, API, UI, tests, and the existing deployment scripts.
- Produces: operator setup instructions, verified branch commits, pushed fork branch, and a deployed control plane that preserves the running VoWiFi engine and radio safety state.

- [ ] **Step 1: Document Bark setup and privacy modes**

Add concise instructions covering:

1. Install Bark on iPhone and copy its full test URL.
2. Paste the URL into Notifications → Bark.
3. Generate key/IV in MDD and enter the identical AES-128-CBC values in Bark's Push Encryption settings.
4. Send a test before enabling the channel.
5. Confirm an incoming SMS shows the receiving SIM number and content.
6. Explain that plaintext mode exposes notification content to the Bark server and APNs, while encrypted mode sends ciphertext.
7. For failures, check the metadata-only delivery log without pasting the push URL or encryption values into reports.

Add Bark test-send and encrypted incoming-SMS checks to the release checklist.

- [ ] **Step 2: Run the complete test suite from a clean working tree state**

Run:

```bash
python -m unittest discover -s tests -v
cd webui
npm test
npm run build
cd ..
git diff --check
```

Expected: all Python tests PASS, all Node tests PASS, Vite build exits 0, and `git diff --check` prints nothing.

- [ ] **Step 3: Commit documentation**

```bash
git add docs/TROUBLESHOOTING.md docs/RELEASE_CHECKLIST.md
git commit -m "docs: explain encrypted Bark SMS forwarding"
```

- [ ] **Step 4: Review branch scope before publishing**

Run:

```bash
git status --short --branch
git log --oneline upstream/main..HEAD
git diff --stat upstream/main...HEAD
```

Expected: no uncommitted files; Bark changes are isolated to the planned provider, registration, UI, test, and documentation files, plus the existing EC200A and microphone patch commits already on this fork branch.

- [ ] **Step 5: Push the private fork branch**

Run:

```bash
git push origin fix/ec200a-vowifi
```

Expected: the remote branch advances to the final Bark documentation commit.

- [ ] **Step 6: Deploy without restarting the VoWiFi engine**

On `192.168.3.13`, back up the current control-plane source files, sync the verified source, build the WebUI and control image, and reload only the control plane using the project's image-reuse path. Do not restart `mdd-sim-gateway-engine-1`, the orchestrator, pcscd, or modem services during this feature deployment.

Before and after deployment capture:

```bash
docker inspect -f '{{.Id}} {{.State.Running}}' mdd-sim-gateway-engine-1
docker exec mdd-sim-gateway-engine-1 asterisk -rx 'pjsip show registrations'
```

Expected: the engine container ID is unchanged and IMS remains `Registered`.

- [ ] **Step 7: Verify WebUI and radio safety after deployment**

Verify:

```bash
curl -sk -o /dev/null -w '%{http_code}\n' https://127.0.0.1:8443/
```

Expected: HTTP 200. Check device status JSON and assert EC200A is present, `flight_mode_active` is true, `cellular_radio_enabled` is false, and `vowifi_bridge_active` is true.

- [ ] **Step 8: Perform the user-configured end-to-end test**

After the user pastes the Bark URL and matching encryption values in the authenticated WebUI:

1. Use the Bark Test button and confirm the iPhone receives the encrypted test.
2. Send one SMS to the managed Tello number.
3. Confirm Bark displays the receiving Tello number and exact SMS content.
4. Confirm the delivery log contains `channel=bark`, `event=incoming_sms`, `status=delivered`, and no message body or secrets.

Do not claim end-to-end Bark delivery until all four observations pass.
