"""Password hashing, JWT session tokens and secret-derived encryption keys."""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta

import jwt
from cryptography.fernet import Fernet

from app.config import get_settings

# ---------------------------------------------------------------------------
# Password hashing (PBKDF2-HMAC-SHA256, stdlib only, 256-bit salt)
# ---------------------------------------------------------------------------

_HASH_NAME = "sha256"
_SALT_BYTES = 32
_DK_LEN = 32


def hash_password(password: str, iterations: int | None = None) -> str:
    iterations = iterations or get_settings().PASSWORD_ITERATIONS
    salt = secrets.token_bytes(_SALT_BYTES)
    dk = hashlib.pbkdf2_hmac(_HASH_NAME, password.encode("utf-8"), salt, iterations, dklen=_DK_LEN)
    return f"pbkdf2${iterations}${base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iterations, salt_b64, dk_b64 = stored.split("$")
        if algo != "pbkdf2":
            return False
        iterations = int(iterations)
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(dk_b64)
    except (ValueError, TypeError, AttributeError):
        return False
    dk = hashlib.pbkdf2_hmac(_HASH_NAME, password.encode("utf-8"), salt, iterations, dklen=len(expected))
    return hmac.compare_digest(dk, expected)


# ---------------------------------------------------------------------------
# Session tokens (JWT HS256, stored in an HttpOnly cookie)
# ---------------------------------------------------------------------------

_JWT_ALGO = "HS256"


def _jwt_secret() -> str:
    secret = get_settings().SECRET_KEY
    # Derive a stable 32-byte key regardless of provided secret length
    return base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest()).decode()


def create_session_token(user_id: str, username: str, expire_minutes: int | None = None) -> str:
    settings = get_settings()
    minutes = expire_minutes or settings.SESSION_EXPIRE_MINUTES
    now = datetime.now(UTC)
    payload = {
        "sub": user_id,
        "username": username,
        "iat": now,
        "exp": now + timedelta(minutes=minutes),
        "type": "session",
    }
    return jwt.encode(payload, _jwt_secret(), algorithm=_JWT_ALGO)


def decode_session_token(token: str) -> dict | None:
    try:
        payload = jwt.decode(token, _jwt_secret(), algorithms=[_JWT_ALGO])
    except jwt.PyJWTError:
        return None
    if payload.get("type") != "session":
        return None
    return payload


# ---------------------------------------------------------------------------
# Fernet key derived from SECRET_KEY (for encrypting Gmail refresh tokens at rest)
# ---------------------------------------------------------------------------

_cached_fernet: Fernet | None = None


def _fernet() -> Fernet:
    global _cached_fernet
    if _cached_fernet is None:
        key = base64.urlsafe_b64encode(hashlib.sha256(_jwt_secret().encode()).digest())
        _cached_fernet = Fernet(key)
    return _cached_fernet


def encrypt_secret(plaintext: str) -> str:
    if not plaintext:
        return ""
    return _fernet().encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_secret(ciphertext: str) -> str:
    if not ciphertext:
        return ""
    try:
        return _fernet().decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except Exception:  # noqa: BLE001 - malformed ciphertext must not crash callers
        return ""


def generate_secure_token(length: int = 48) -> str:
    return secrets.token_urlsafe(length)