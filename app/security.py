"""Security, cryptography, JWT token operations, and password hashing.

Provides cryptographic helpers for:
- JWT Access & Refresh Token creation and decoding
- Fernet symmetric encryption for sensitive provider credentials
- Bcrypt password hashing
- Secure API key generation and SHA-256 verification
"""

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple
from uuid import UUID

import bcrypt
from cryptography.fernet import Fernet
from jose import JWTError, jwt

from app.config import settings
from app.exceptions import AuthenticationError

# Symmetric encryption cipher for sensitive keys at rest
_cipher: Optional[Fernet] = None


def get_cipher() -> Fernet:
    """Retrieve or initialize the Fernet cipher for symmetric encryption."""
    global _cipher
    if _cipher is None:
        key = settings.ENCRYPTION_KEY.encode()
        _cipher = Fernet(key)
    return _cipher


# ==============================================================================
# Password Hashing
# ==============================================================================

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a raw password against its bcrypt hash (truncated to 72 bytes)."""
    try:
        pwd_bytes = plain_password[:72].encode("utf-8")
        hash_bytes = hashed_password.encode("utf-8")
        return bcrypt.checkpw(pwd_bytes, hash_bytes)
    except Exception:
        return False


def get_password_hash(password: str) -> str:
    """Generate a bcrypt hash from a raw password (truncated to 72 bytes)."""
    pwd_bytes = password[:72].encode("utf-8")
    salt = bcrypt.gensalt(rounds=settings.BCRYPT_ROUNDS)
    return bcrypt.hashpw(pwd_bytes, salt).decode("utf-8")


# ==============================================================================
# Fernet Symmetric Encryption (Secrets at Rest)
# ==============================================================================

def encrypt_secret(plain_text: str) -> str:
    """Encrypt sensitive credentials (e.g. Meta API keys, OpenAI keys) before DB storage."""
    if not plain_text:
        return ""
    cipher = get_cipher()
    return cipher.encrypt(plain_text.encode("utf-8")).decode("utf-8")


def decrypt_secret(cipher_text: str) -> str:
    """Decrypt sensitive credentials retrieved from database."""
    if not cipher_text:
        return ""
    cipher = get_cipher()
    return cipher.decrypt(cipher_text.encode("utf-8")).decode("utf-8")


# ==============================================================================
# JWT Authentication Tokens
# ==============================================================================

def create_access_token(
    user_id: UUID,
    email: str,
    organization_id: Optional[UUID] = None,
    role: Optional[str] = None,
    permissions: Optional[list[str]] = None,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """Generate an RS256/HS256 signed JWT access token."""
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode: Dict[str, Any] = {
        "sub": str(user_id),
        "email": email,
        "type": "access",
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    if organization_id:
        to_encode["org_id"] = str(organization_id)
    if role:
        to_encode["role"] = role
    if permissions:
        to_encode["perms"] = permissions

    encoded_jwt = jwt.encode(
        to_encode, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM
    )
    return encoded_jwt


def create_refresh_token(user_id: UUID, session_id: UUID) -> Tuple[str, datetime]:
    """Generate a high-entropy refresh token and compute its expiration."""
    now = datetime.now(timezone.utc)
    expire = now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    payload = {
        "sub": str(user_id),
        "session_id": str(session_id),
        "type": "refresh",
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    encoded_token = jwt.encode(
        payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM
    )
    return encoded_token, expire


def decode_token(token: str) -> Dict[str, Any]:
    """Verify and decode a JWT token string. Raises AuthenticationError on failure."""
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )
        return payload
    except JWTError as e:
        raise AuthenticationError(
            message="Token signature is invalid or expired",
            details={"error": str(e)},
        )


# ==============================================================================
# API Key Management
# ==============================================================================

def generate_api_key(prefix: str = "gab_live_") -> Tuple[str, str, str]:
    """Generate a secure API key with prefix.

    Returns:
        raw_key: The full key shown only once to user
        key_hash: SHA-256 hash for database indexing & lookup
        key_prefix: First 8 characters for visual identification (e.g. 'gab_live_a1b2')
    """
    random_bytes = secrets.token_urlsafe(32)
    raw_key = f"{prefix}{random_bytes}"
    key_hash = hash_api_key(raw_key)
    key_prefix = raw_key[:16]
    return raw_key, key_hash, key_prefix


def hash_api_key(raw_key: str) -> str:
    """Compute SHA-256 hash of raw API key for secure storage."""
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def verify_api_key(raw_key: str, stored_hash: str) -> bool:
    """Constant-time verification of API key against stored SHA-256 hash."""
    computed_hash = hash_api_key(raw_key)
    return hmac.compare_digest(computed_hash, stored_hash)
