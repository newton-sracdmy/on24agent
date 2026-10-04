"""Unit tests for security, cryptography, password hashing, and token operations."""

import uuid
from app.security import (
    create_access_token,
    decode_token,
    decrypt_secret,
    encrypt_secret,
    generate_api_key,
    get_password_hash,
    verify_api_key,
    verify_password,
)


def test_password_hashing():
    plain = "SuperSecretPassword123!"
    hashed = get_password_hash(plain)
    assert hashed != plain
    assert verify_password(plain, hashed) is True
    assert verify_password("WrongPassword!", hashed) is False


def test_fernet_secret_encryption():
    secret_token = "eaab_whatsapp_meta_token_123456789"
    encrypted = encrypt_secret(secret_token)
    assert encrypted != secret_token
    decrypted = decrypt_secret(encrypted)
    assert decrypted == secret_token


def test_jwt_access_token_creation_and_decoding():
    user_id = uuid.uuid4()
    org_id = uuid.uuid4()
    email = "test@gabster.ai"
    role = "admin"
    perms = ["conversations:read", "messages:write"]

    token = create_access_token(
        user_id=user_id,
        email=email,
        organization_id=org_id,
        role=role,
        permissions=perms,
    )

    payload = decode_token(token)
    assert payload["sub"] == str(user_id)
    assert payload["email"] == email
    assert payload["org_id"] == str(org_id)
    assert payload["role"] == role
    assert payload["perms"] == perms


def test_api_key_generation_and_verification():
    raw_key, key_hash, key_prefix = generate_api_key(prefix="gab_live_")
    assert raw_key.startswith("gab_live_")
    assert key_prefix.startswith("gab_live_")
    assert len(key_hash) == 64  # SHA-256 hex digest
    assert verify_api_key(raw_key, key_hash) is True
    assert verify_api_key("gab_live_invalid_key", key_hash) is False
