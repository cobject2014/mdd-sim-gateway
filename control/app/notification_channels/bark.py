"""Bark push adapter.

This module deliberately depends only on HTTP and cryptography primitives.  It does not
know about SIM storage, VoWiFi, modem state, FastAPI, or configuration persistence.
"""
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
    """Validate administrator-provided settings without returning any secret value."""
    if not isinstance(config, dict):
        raise ValueError("Bark configuration must be an object")
    _push_url(config)
    level = str(config.get("level") or "active")
    if level not in LEVELS:
        raise ValueError("Bark notification level is invalid")
    encryption = config.get("encryption") or {}
    if not isinstance(encryption, dict):
        raise ValueError("Bark encryption configuration must be an object")
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
    """Build the receiver-centric default used for incoming SMS notifications."""
    receiver = _receiver(payload)
    return {
        "title": f"MDD · 收到短信 · {receiver}",
        "content": f"收件号码: {receiver}\n\n短信内容:\n{payload.get('text') or ''}",
    }


def _plaintext_body(config: dict, payload: dict) -> dict:
    body = {
        "title": str(payload.get("title") or ""),
        "body": str(payload.get("content") or ""),
    }
    for field in ("group", "sound"):
        value = str(config.get(field) or "").strip()
        if value:
            body[field] = value
    level = str(config.get("level") or "active")
    if level != "active" or "level" in config:
        body["level"] = level
    return body


def _encrypt(body: dict, key: bytes, iv: bytes) -> str:
    plaintext = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    padder = PKCS7(128).padder()
    padded = padder.update(plaintext) + padder.finalize()
    encryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).encryptor()
    ciphertext = encryptor.update(padded) + encryptor.finalize()
    return base64.b64encode(ciphertext).decode("ascii")


def build_request(config: dict, payload: dict) -> tuple[str, dict, dict]:
    """Return the destination, JSON body, and safe requests kwargs for one delivery."""
    validate_config(config)
    url = _push_url(config)
    body = _plaintext_body(config, payload)
    encryption = config.get("encryption") or {}
    if encryption.get("enabled", True):
        key = str(encryption.get("key") or "").encode("utf-8")
        iv = str(encryption.get("iv") or "").encode("utf-8")
        body = {"ciphertext": _encrypt(body, key, iv)}
    return url, body, {
        "timeout": TIMEOUT_SECONDS,
        "verify": bool(config.get("verify_tls", True)),
    }


def send(config: dict, payload: dict) -> dict:
    """Send one push and expose no response body, SMS content, URL, or key in errors."""
    url, body, kwargs = build_request(config, payload)
    session = requests.Session()
    session.trust_env = False
    try:
        response = session.post(url, json=body, **kwargs)
        response.raise_for_status()
        try:
            result = response.json()
        except ValueError:
            content_type = str((response.headers or {}).get("Content-Type") or "").lower()
            if "json" in content_type:
                raise RuntimeError("Bark returned an invalid response") from None
            result = None
        if isinstance(result, dict) and "code" in result and str(result["code"]) != "200":
            raise RuntimeError("Bark rejected the notification")
        return {"ok": True, "status_code": response.status_code}
    except requests.RequestException:
        raise RuntimeError("Bark request failed") from None
    finally:
        session.close()
