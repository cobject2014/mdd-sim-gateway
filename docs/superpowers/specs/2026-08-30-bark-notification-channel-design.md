# Bark Notification Channel Design

Date: 2026-08-30
Status: proposed
Reference: SimAdmin notification-channel behavior and Bark's public API documentation

## Goal

Add a first-class Bark notification channel to MDD Sim Gateway so an incoming VoWiFi SMS can be pushed to an iPhone. Keep the integration isolated from the SIM, IMS, call, and SMS ingestion paths so future upstream merges remain low-conflict.

## Scope

The first release will:

- accept the complete Bark push URL copied from the iOS app;
- support the public Bark service and self-hosted Bark-compatible servers;
- forward incoming SMS by default and allow all existing notification events to be enabled individually;
- make the receiving SIM's own number and the SMS text the default Bark message content so
  notifications remain unambiguous when the gateway manages multiple SIMs;
- support the existing per-event title and content templates;
- support notification group, sound, and interruption level;
- support optional Bark-compatible AES-128-CBC encrypted pushes, enabled by default for a new Bark configuration;
- fail closed when encryption is enabled but cannot be performed;
- reuse the existing delivery retry and metadata-only delivery history;
- provide settings validation and a test-send endpoint and button;
- preserve HTTPS certificate verification by default.

This release will not deploy a Bark server, manage iOS settings, implement replies from Bark, or change SMS reception, IMS, modem, cellular-radio, or flight-mode behavior.

## Design Principles

### Isolate provider behavior

Bark request construction, validation, encryption, response inspection, and secret redaction will live in a new module:

`control/app/notification_channels/bark.py`

The module exposes a deliberately small interface:

```python
def validate_config(config: dict) -> None: ...
def send(config: dict, payload: dict) -> dict: ...
```

It may use a small internal `build_request` helper for deterministic unit tests. It will not import FastAPI, configuration persistence, the SMS store, AMI, or device control.

The existing `notify_push.py` remains the channel coordinator. Its only provider-specific changes are importing the Bark adapter, including `bark` in enabled-channel checks, and dispatching the canonical notification payload to `bark.send`. This keeps the event producer and retry code provider-neutral.

### Isolate HTTP and UI glue

FastAPI keeps the existing notification endpoint convention. `main.py` only adds:

- Bark configuration validation in the settings endpoint;
- `POST /api/notifications/bark/test`, which builds the existing synthetic event payload and calls the adapter off the event loop.

The Bark settings card will be placed in a new React component rather than adding another long inline block to `UnifiedPages.jsx`. The parent page passes the current config, update callback, event-checkbox renderer, template editor, toast callback, and test API method. No Bark state will leak into device or message views.

## Configuration Contract

The new top-level settings object is `settings.bark`:

```yaml
bark:
  enabled: false
  push_url: ""
  verify_tls: true
  encryption:
    enabled: true
    algorithm: aes-128-cbc
    key: ""
    iv: ""
  group: MDD SMS
  sound: ""
  level: active
  message_templates: {}
  events:
    incoming_sms: true
    incoming_call: false
    missed_call: false
    voicemail_received: false
    keepalive_result: false
    balance_low: false
    software_update: false
```

The standard configuration merge will preserve new defaults when upgrading an older installation. `push_url`, `encryption.key`, and `encryption.iv` are secrets and must not appear in logs, delivery history, support bundles, or exception strings. Existing configuration storage remains protected by the host's `0600` file permissions.

`push_url` is the full test URL copied from Bark, for example an HTTPS server URL followed by the device key. The adapter parses it without echoing it in errors. It accepts only HTTP or HTTPS, rejects embedded credentials, fragments, query strings, and URLs without a device-key path segment. HTTPS certificate verification defaults to on. HTTP remains available for an explicitly configured self-hosted LAN service.

`level` is restricted to `active`, `timeSensitive`, `critical`, or `passive`. The adapter sends optional group and sound fields only when non-empty.

## Incoming SMS Message Contract

For `incoming_sms`, the default Bark notification is intentionally receiver-centric:

```text
Title: MDD · 收到短信 · <receiving number or SIM identity>

收件号码: <receiving SIM's MSISDN>

短信内容:
<SMS text>
```

The receiving number comes from the canonical payload's `msisdn` field, which belongs to the
SIM line that received the message. It must never be populated from `from`, which is the remote
sender. When a carrier has not exposed an MSISDN, the title and recipient line fall back to the
configured SIM name, then ICCID, then line id so two managed SIMs cannot produce indistinguishable
notifications. The sender remains available as the `{{from}}` template variable for an operator
who later wants a custom format, but it is not part of the default Bark content requested here.

## Encrypted Push Flow

When encryption is enabled:

1. Build the normal Bark payload containing title, body, group, sound, and level.
2. Serialize it as compact UTF-8 JSON.
3. Apply PKCS#7 padding and encrypt with AES-128-CBC using the configured 16-byte key and 16-byte IV.
4. Base64-encode the ciphertext.
5. POST only the `ciphertext` field to the Bark device URL.
6. The Bark iOS notification extension decrypts it using the same algorithm, key, and IV configured in the app.

There is no plaintext fallback. Invalid key/IV length, encryption errors, or missing encryption settings fail validation or delivery. The user-facing UI explains that the same values must be entered in Bark and provides a local-browser generator using `crypto.getRandomValues`; generated values are not sent anywhere until the user saves the settings.

When encryption is disabled, the adapter sends the regular Bark JSON body. The UI labels this mode as exposing notification content to the Bark server and Apple APNs.

## Notification and Delivery Flow

The existing inbound flow is unchanged:

1. The engine reports an incoming SMS to the control plane.
2. The control plane stores and deduplicates the message.
3. `_dispatch_push` builds the canonical event payload, including the receiving line's `msisdn`
   and the SMS `text`.
4. `notify_push.dispatch` selects enabled channels.
5. The existing retry wrapper calls `bark.send` up to three times with the current delays.
6. Delivery history stores channel, event, line id, attempt count, HTTP status, and a sanitized error category only.

The adapter treats a non-2xx HTTP status, invalid JSON when a JSON response is returned, or a Bark response that explicitly reports failure as a failed attempt. Exceptions never include the request URL, response body, device key, encryption material, SMS body, or sender number.

## UI Behavior

The notification page adds a Bark card with:

- enable switch;
- password-style full push URL field;
- TLS verification switch;
- encryption switch, fixed AES-128-CBC algorithm label, password-style key and IV fields, and a generate button;
- group, sound, and notification-level fields;
- the existing message-template editor;
- the existing per-event checkboxes;
- a test button.

Saving an enabled Bark channel requires a valid push URL. Encrypted mode additionally requires valid key and IV lengths. The test button uses the unsaved card values so the user can verify them before saving, matching the existing notification-channel behavior.

## Error Handling and Security

- Network requests use the existing short notification timeout and do not inherit proxy environment variables implicitly.
- TLS verification remains enabled unless the administrator explicitly disables it.
- Encryption is performed locally in the control container before any HTTP request.
- Configuration validation runs both on save and test send.
- Encryption failure never triggers plaintext transmission.
- Delivery logs contain metadata only.
- Support-bundle redaction gains explicit Bark secret keys as defense in depth.
- The device key is treated as an authorization secret: it is masked in the UI and never returned in a provider error.
- No new inbound command, reply, or remote-control surface is added.

## Testing

Backend tests will cover:

- URL validation and device-path preservation for public and self-hosted URLs;
- rejection of unsafe or malformed URLs;
- plaintext request structure;
- AES-128-CBC deterministic fixture and decrypt round-trip;
- encrypted requests containing no plaintext title, body, sender, or number;
- no plaintext fallback on invalid encryption configuration;
- optional Bark fields and event templates;
- correct receiver-number selection for multiple SIMs, including the no-MSISDN identity fallback;
- proof that the default Bark content uses `msisdn` and `text`, not the sender number;
- provider success and failure response handling without secret leakage;
- dispatch gating and inclusion in `has_enabled_channel`;
- settings default merge and support-bundle redaction;
- test endpoint behavior.

Frontend tests will cover:

- the Bark API method and independent settings component;
- required fields and encryption warning text;
- default incoming-SMS-only event selection;
- translated notification-page labels.

The full Python test suite and WebUI production build must pass before deployment. Deployment will reuse the project's normal control-image path, preserve the running engine where possible, and verify that VoWiFi remains registered, flight mode stays enabled, and the cellular radio stays disabled.

## Upstream Merge Strategy

Provider code and UI code are new files. Shared-file edits are limited to small registration points in:

- `control/app/notify_push.py`;
- `control/app/config.py`;
- `control/app/main.py`;
- `webui/src/api.js`;
- `webui/src/views/UnifiedPages.jsx`;
- `webui/src/i18n.jsx`.

No existing event schema or public notification-channel behavior changes. This makes future upstream conflict resolution a matter of reapplying a few explicit registration lines while retaining the independent Bark modules and tests.

## Attribution

SimAdmin was used to identify useful Bark configuration fields and notification-channel UX. The implementation will be written for MDD Sim Gateway's Python/React architecture against Bark's documented public API; no Rust source will be copied.
