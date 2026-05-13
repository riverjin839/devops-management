"""Symmetric encryption helpers for secrets stored at rest.

Uses ``cryptography.fernet`` with a key derived from ``settings.secret_key``
(SHA-256 → urlsafe base64). Rotating the secret invalidates every previously
encrypted value, which is the intended behavior — the JWT signing key is
treated as the single root-of-trust.

Currently used for:
- BatchJob.default_password_enc / default_private_key_enc

Future callers should reuse these helpers rather than rolling their own.
"""
from __future__ import annotations

import base64
import hashlib
import logging
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

from app.config import settings

logger = logging.getLogger(__name__)


def _fernet() -> Fernet:
    key = base64.urlsafe_b64encode(hashlib.sha256(settings.secret_key.encode()).digest())
    return Fernet(key)


def encrypt_secret(plain: Optional[str]) -> Optional[str]:
    """Return an opaque ciphertext string, or None if input is empty."""
    if not plain:
        return None
    return _fernet().encrypt(plain.encode("utf-8")).decode("ascii")


def decrypt_secret(enc: Optional[str]) -> Optional[str]:
    """Decrypt a string produced by ``encrypt_secret``. Returns None on
    failure so callers can treat it like a missing secret rather than
    crashing — but the failure is logged for visibility.
    """
    if not enc:
        return None
    try:
        return _fernet().decrypt(enc.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, TypeError) as exc:
        logger.warning("decrypt_secret failed: %s", exc)
        return None
