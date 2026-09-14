"""Unit tests for panel-managed runtime settings (no network, no DB rows).

Covers:
- runtime_settings.merge_settings: secret decryption, legacy plaintext tolerance,
  empty-value fallback to env, and per-field overrides.
- settings_api.prepare_section_values: encrypt-on-PUT, mask/empty => leave
  unchanged, unknown keys => 422.
- settings_api._mask_section: GET masking of configured secrets.
- gmail_client.get_transport: fake / smtp / auto cascade.
- gmail_client.SmtpTransport: real smtplib session mocked out (STARTTLS + login +
  from-address fallback chain) and _build_message sender precedence.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.api.settings_api import SECRET_MASK, _mask_section, prepare_section_values
from app.config import get_settings
from app.core.secrets import decrypt_secret, encrypt_secret
from app.services.gmail_client import (
    FakeTransport,
    RealGmailTransport,
    SmtpTransport,
    _build_message,
    get_transport,
)
from app.services.runtime_settings import is_secret_setting, merge_settings
from app.services.settings_service import DEFAULT_SETTINGS

SECRET = "sk-super-secret-token"


class TestMergeSettings:
    def test_empty_map_returns_env_settings(self):
        base = get_settings()
        merged = merge_settings({})
        assert merged is base or merged.model_dump() == base.model_dump()

    def test_plain_fields_override_env(self):
        env = get_settings()
        merged = merge_settings(
            {
                "smtp": {"host": "smtp.office365.com", "port": 587, "username": "m@x.com"},
                "telegram": {"chat_id": "12345"},
                "gmail": {"sender_email": "outreach@x.com", "sender_name": "Bot"},
                "ai": {"base_url": "https://llm.example.com/v1"},
            },
            base=env,
        )
        assert merged.SMTP_HOST == "smtp.office365.com"
        assert merged.SMTP_PORT == 587
        assert merged.SMTP_USERNAME == "m@x.com"
        assert merged.TELEGRAM_CHAT_ID == "12345"
        assert merged.GMAIL_SENDER_EMAIL == "outreach@x.com"
        assert merged.GMAIL_SENDER_NAME == "Bot"
        assert merged.OPENROUTER_BASE_URL == "https://llm.example.com/v1"

    def test_encrypted_secrets_are_decrypted(self):
        env = get_settings()
        merged = merge_settings(
            {
                "ai": {"api_key": encrypt_secret(SECRET)},
                "smtp": {"password": encrypt_secret("pw")},
                "telegram": {"bot_token": encrypt_secret("tok123")},
                "gmail": {"client_secret": encrypt_secret("gsec")},
            },
            base=env,
        )
        assert merged.OPENROUTER_API_KEY == SECRET
        assert merged.SMTP_PASSWORD == "pw"
        assert merged.TELEGRAM_BOT_TOKEN == "tok123"
        assert merged.GOOGLE_CLIENT_SECRET == "gsec"

    def test_legacy_plaintext_secret_is_tolerated(self):
        merged = merge_settings({"ai": {"api_key": "plaintext-legacy"}})
        assert merged.OPENROUTER_API_KEY == "plaintext-legacy"

    def test_empty_and_none_values_fall_back_to_env(self):
        env = get_settings().model_copy(update={"GMAIL_SENDER_EMAIL": "env@x.com"})
        merged = merge_settings(
            {"ai": {"api_key": ""}, "telegram": {"chat_id": None}, "gmail": {"sender_email": ""}},
            base=env,
        )
        assert merged.OPENROUTER_API_KEY == env.OPENROUTER_API_KEY
        assert merged.TELEGRAM_CHAT_ID == env.TELEGRAM_CHAT_ID
        assert merged.GMAIL_SENDER_EMAIL == "env@x.com"

    def test_is_secret_setting_markers(self):
        assert is_secret_setting("ai", "api_key")
        assert is_secret_setting("smtp", "password")
        assert is_secret_setting("telegram", "bot_token")
        assert not is_secret_setting("ai", "base_url")
        assert not is_secret_setting("smtp", "host")

    def test_every_secret_in_schema_is_marked(self):
        for section, entries in DEFAULT_SETTINGS.items():
            for key, spec in entries.items():
                if key in {"api_key", "client_secret", "password", "bot_token"}:
                    assert spec.get("secret"), f"{section}.{key} should be secret"


class TestPrepareSectionValues:
    def test_new_secret_is_encrypted(self):
        out = prepare_section_values("ai", {"api_key": SECRET, "temperature": 0.5})
        assert out["temperature"] == 0.5
        assert decrypt_secret(out["api_key"]) == SECRET
        assert out["api_key"].startswith("gAAAA")

    def test_mask_means_leave_unchanged(self):
        out = prepare_section_values("ai", {"api_key": SECRET_MASK})
        assert "api_key" not in out

    def test_empty_secret_means_leave_unchanged(self):
        out = prepare_section_values("ai", {"api_key": ""})
        assert "api_key" not in out

    def test_none_secret_means_leave_unchanged(self):
        out = prepare_section_values("ai", {"api_key": None})
        assert "api_key" not in out

    def test_unknown_key_rejected(self):
        with pytest.raises(HTTPException) as exc:
            prepare_section_values("ai", {"bogus": 1})
        assert exc.value.status_code == 422

    def test_mask_section_masks_configured_secrets(self):
        masked = _mask_section("ai", {"api_key": encrypt_secret(SECRET), "base_url": "https://x"})
        assert masked["api_key"] == SECRET_MASK
        assert masked["base_url"] == "https://x"

    def test_mask_section_leaves_unset_secret_empty(self):
        assert _mask_section("ai", {"api_key": "", "model": "m"})["api_key"] == ""
        assert _mask_section("ai", {"model": "m"}).get("api_key", "") == ""


class TestGetTransport:
    def _settings(self, **updates):
        return get_settings().model_copy(update=updates)

    def test_explicit_smtp(self):
        transport = get_transport("smtp", self._settings())
        assert isinstance(transport, SmtpTransport)

    def test_explicit_fake(self):
        assert isinstance(get_transport("fake", self._settings()), FakeTransport)

    def test_auto_prefers_smtp_when_host_configured(self):
        transport = get_transport("", self._settings(GMAIL_TRANSPORT="auto", SMTP_HOST="smtp.example.com"))
        assert isinstance(transport, SmtpTransport)

    def test_auto_falls_back_to_fake_without_credentials(self):
        transport = get_transport("", self._settings(GMAIL_TRANSPORT="auto"))
        assert isinstance(transport, FakeTransport)

    def test_token_json_selects_real_gmail(self):
        transport = get_transport("auto", self._settings(GMAIL_TOKEN_JSON='{"token": "x"}'))
        assert isinstance(transport, RealGmailTransport)

    def test_panel_smtp_creds_drive_auto_transport(self):
        # End-to-end chain without the network: credentials stored (encrypted) in
        # the settings table model -> merge_settings -> get_transport.
        merged = merge_settings(
            {
                "smtp": {
                    "host": "smtp.office365.com",
                    "port": 587,
                    "username": "m@x.com",
                    "password": encrypt_secret("pw"),
                    "from_email": "m@x.com",
                    "from_name": "Outreach",
                    "use_tls": True,
                }
            }
        )
        assert merged.SMTP_PASSWORD == "pw"
        transport = get_transport("", merged)
        assert isinstance(transport, SmtpTransport)
        assert transport.settings.SMTP_HOST == "smtp.office365.com"


class FakeSMTP:
    """Recording stand-in for smtplib.SMTP."""

    instances: list["FakeSMTP"] = []

    def __init__(self, host: str, port: int, timeout: int | None = None) -> None:
        self.host = host
        self.port = port
        self.calls: list[object] = []
        type(self).instances.append(self)

    def __enter__(self) -> "FakeSMTP":
        return self

    def __exit__(self, *exc: object) -> bool:
        return False

    def starttls(self) -> None:
        self.calls.append("starttls")

    def login(self, user: str, password: str) -> None:
        self.calls.append(("login", user, password))

    def send_message(self, msg: object, from_addr: str | None = None) -> None:
        self.calls.append(("send_message", msg, from_addr))


class TestSmtpTransport:
    def _settings(self, **updates):
        return get_settings().model_copy(
            update={
                "SMTP_HOST": "smtp.example.com",
                "SMTP_PORT": 587,
                "SMTP_USERNAME": "user@example.com",
                "SMTP_PASSWORD": "pw",
                "SMTP_FROM_EMAIL": "from@example.com",
                "SMTP_USE_TLS": True,
                **updates,
            }
        )

    async def test_send_email_uses_starttls_login_and_from_addr(self, monkeypatch):
        monkeypatch.setattr("smtplib.SMTP", FakeSMTP)
        FakeSMTP.instances = []
        transport = SmtpTransport(self._settings())
        result = await transport.send_email(to="a@b.com", subject="Hello", body="Body")
        assert result["ok"] is True
        assert result["detail"] == "sent via SMTP"
        session = FakeSMTP.instances[-1]
        assert session.host == "smtp.example.com"
        assert session.port == 587
        assert session.calls[0] == "starttls"
        assert ("login", "user@example.com", "pw") in session.calls
        send = session.calls[-1]
        assert send[0] == "send_message"
        assert send[2] == "from@example.com"

    async def test_send_email_reports_smtp_failures(self, monkeypatch):
        class BoomSMTP(FakeSMTP):
            def starttls(self) -> None:
                raise RuntimeError("boom")

        monkeypatch.setattr("smtplib.SMTP", BoomSMTP)
        result = await SmtpTransport(self._settings()).send_email(
            to="a@b.com", subject="S", body="B"
        )
        assert result["ok"] is False
        assert "SMTP error" in result["detail"]

    def test_sender_fallback_chain_in_message(self):
        settings = self._settings(
            GMAIL_SENDER_EMAIL="", GMAIL_SENDER_NAME="",
            SMTP_FROM_EMAIL="fallback@example.com", SMTP_FROM_NAME="Fallback Sender",
        )
        msg = _build_message(
            to="a@b.com", subject="S", body="B", reply_to=None, thread_id=None,
            settings=settings,
        )
        assert "Fallback Sender <fallback@example.com>" == msg["From"]

    def test_sender_falls_back_to_smtp_username(self):
        settings = self._settings(
            GMAIL_SENDER_EMAIL="", GMAIL_SENDER_NAME="",
            SMTP_FROM_EMAIL="", SMTP_FROM_NAME="", SMTP_USERNAME="user@example.com",
        )
        msg = _build_message(
            to="a@b.com", subject="S", body="B", reply_to=None, thread_id=None,
            settings=settings,
        )
        assert "user@example.com" in msg["From"]