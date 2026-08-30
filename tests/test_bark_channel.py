import base64
import json
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.padding import PKCS7

from control.app.notification_channels import bark
from control.app import main, notify_push
from fastapi import HTTPException


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
            with self.subTest(payload=payload):
                self.assertIn(expected, bark.default_message({
                    "event": "incoming_sms", "text": "hello", **payload,
                })["title"])

    def test_encrypted_request_round_trips_and_contains_no_plaintext(self):
        config = {
            "push_url": "https://api.day.app/device-secret",
            "encryption": {"enabled": True, "algorithm": "aes-128-cbc",
                           "key": "0123456789ABCDEF", "iv": "FEDCBA9876543210"},
        }
        url, body, kwargs = bark.build_request(config, {
            "title": "MDD · 收到短信 · +15413006437",
            "content": "收件号码: +15413006437\n\n短信内容:\nprivate body",
        })
        encoded = json.dumps(body, ensure_ascii=False)
        self.assertEqual(url, config["push_url"])
        self.assertEqual(kwargs, {"timeout": 8, "verify": True})
        self.assertEqual(set(body), {"ciphertext"})
        self.assertNotIn("private body", encoded)
        decryptor = Cipher(algorithms.AES(b"0123456789ABCDEF"),
                           modes.CBC(b"FEDCBA9876543210")).decryptor()
        padded = decryptor.update(base64.b64decode(body["ciphertext"])) + decryptor.finalize()
        unpadder = PKCS7(128).unpadder()
        decoded = json.loads((unpadder.update(padded) + unpadder.finalize()).decode())
        self.assertEqual(decoded["body"], "收件号码: +15413006437\n\n短信内容:\nprivate body")

    def test_plaintext_request_uses_optional_bark_fields(self):
        url, body, kwargs = bark.build_request({
            "push_url": "http://bark.internal/device-key",
            "group": "MDD", "sound": "alarm", "level": "timeSensitive",
            "verify_tls": False, "encryption": {"enabled": False},
        }, {"title": "Title", "content": "Body"})
        self.assertEqual(url, "http://bark.internal/device-key")
        self.assertEqual(body, {"title": "Title", "body": "Body", "group": "MDD",
                                "sound": "alarm", "level": "timeSensitive"})
        self.assertEqual(kwargs, {"timeout": 8, "verify": False})

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

    @patch("control.app.notification_channels.bark.requests.Session")
    def test_send_disables_environment_proxy_and_accepts_success(self, session_factory):
        session = MagicMock()
        response = MagicMock(status_code=200)
        response.json.return_value = {"code": 200, "message": "success"}
        session.post.return_value = response
        session_factory.return_value = session

        result = bark.send({
            "push_url": "https://api.day.app/device-secret", "verify_tls": True,
            "encryption": {"enabled": False},
        }, {"title": "Title", "content": "Body"})

        self.assertEqual(result, {"ok": True, "status_code": 200})
        self.assertFalse(session.trust_env)
        self.assertTrue(session.post.call_args.kwargs["verify"])
        response.raise_for_status.assert_called_once_with()
        session.close.assert_called_once_with()

    @patch("control.app.notification_channels.bark.requests.Session")
    def test_send_rejects_bark_error_without_leaking_secrets(self, session_factory):
        session = MagicMock()
        response = MagicMock(status_code=200)
        response.json.return_value = {"code": 400, "message": "private body +15413006437"}
        session.post.return_value = response
        session_factory.return_value = session
        config = {
            "push_url": "https://api.day.app/device-secret",
            "encryption": {"enabled": True, "key": "0123456789ABCDEF",
                           "iv": "FEDCBA9876543210"},
        }

        with self.assertRaises(RuntimeError) as failed:
            bark.send(config, {"title": "+15413006437", "content": "private body"})

        message = str(failed.exception)
        for secret in ("device-secret", "private body", "+15413006437",
                       "0123456789ABCDEF", "FEDCBA9876543210"):
            self.assertNotIn(secret, message)

    @patch("control.app.notification_channels.bark.requests.Session")
    def test_send_rejects_an_invalid_json_response_without_echoing_it(self, session_factory):
        session = MagicMock()
        response = MagicMock(status_code=200)
        response.headers = {"Content-Type": "application/json; charset=utf-8"}
        response.json.side_effect = ValueError("private invalid response")
        session.post.return_value = response
        session_factory.return_value = session

        with self.assertRaisesRegex(RuntimeError, "^Bark returned an invalid response$") as failed:
            bark.send({
                "push_url": "https://api.day.app/device-secret",
                "encryption": {"enabled": False},
            }, {"title": "Title", "content": "private body"})
        self.assertNotIn("private", str(failed.exception))

    @patch("control.app.notification_channels.bark.requests.Session")
    def test_request_errors_are_sanitized(self, session_factory):
        import requests

        session = MagicMock()
        session.post.side_effect = requests.RequestException(
            "https://api.day.app/device-secret private body")
        session_factory.return_value = session
        with self.assertRaisesRegex(RuntimeError, "^Bark request failed$"):
            bark.send({
                "push_url": "https://api.day.app/device-secret",
                "encryption": {"enabled": False},
            }, {"title": "Title", "content": "private body"})

    def test_enabled_bark_settings_are_validated_without_leaking_values(self):
        body = {
            "bark": {
                "enabled": True,
                "push_url": "https://api.day.app/device-secret",
                "encryption": {"enabled": True, "key": "short",
                               "iv": "FEDCBA9876543210"},
            }
        }
        with self.assertRaises(HTTPException) as failed:
            main.api_put_settings(body)
        self.assertEqual(failed.exception.status_code, 400)
        detail = str(failed.exception.detail)
        self.assertIn("invalid Bark configuration", detail)
        self.assertNotIn("device-secret", detail)
        self.assertNotIn("FEDCBA9876543210", detail)


class BarkApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_endpoint_removes_test_event_and_uses_a_receiving_number(self):
        body = {
            "_test_event": notify_push.EV_INCOMING_SMS,
            "push_url": "https://api.day.app/device-secret",
            "encryption": {"enabled": False},
        }
        with patch.object(main.asyncio, "to_thread", new_callable=AsyncMock,
                          return_value={"ok": True}) as offload:
            result = await main.api_bark_test(body)

        self.assertEqual(result, {"ok": True})
        self.assertNotIn("_test_event", body)
        self.assertIs(offload.call_args.args[0], notify_push.send_bark)
        self.assertIs(offload.call_args.args[1], body)
        payload = offload.call_args.args[2]
        self.assertEqual(payload["event"], notify_push.EV_INCOMING_SMS)
        self.assertTrue(payload["msisdn"])

    async def test_endpoint_returns_a_generic_error_for_invalid_secret_config(self):
        body = {
            "push_url": "https://api.day.app/device-secret",
            "encryption": {"enabled": True, "key": "0123456789ABCDEF", "iv": "short"},
        }
        with self.assertRaises(HTTPException) as failed:
            await main.api_bark_test(body)
        self.assertEqual(failed.exception.status_code, 400)
        self.assertEqual(failed.exception.detail, "Bark test delivery failed")
        self.assertNotIn("device-secret", str(failed.exception.detail))
        self.assertNotIn("0123456789ABCDEF", str(failed.exception.detail))


if __name__ == "__main__":
    unittest.main()
