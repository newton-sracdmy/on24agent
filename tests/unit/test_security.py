"""Unit tests for security, cryptography, password hashing, and token operations."""

import uuid

import pytest
from cryptography.fernet import Fernet, MultiFernet
from pydantic import ValidationError

from app.config import Settings
from app.domains.identity.schemas import UserRegister
from app.domains.identity.service import permissions_for_role
from app.exceptions import AuthenticationError
from app.security import (
    create_access_token,
    create_refresh_token,
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

    session_id = uuid.uuid4()
    token = create_access_token(
        user_id=user_id,
        email=email,
        session_id=session_id,
        organization_id=org_id,
        role=role,
        permissions=perms,
    )

    payload = decode_token(token)
    assert payload["sub"] == str(user_id)
    assert payload["email"] == email
    assert payload["sid"] == str(session_id)
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


def test_decode_token_rejects_wrong_token_type():
    refresh_token, _ = create_refresh_token(uuid.uuid4(), uuid.uuid4())
    with pytest.raises(AuthenticationError):
        decode_token(refresh_token)  # expects an access token
    assert decode_token(refresh_token, expected_type="refresh")["type"] == "refresh"


def test_decode_token_error_does_not_leak_details():
    with pytest.raises(AuthenticationError) as exc_info:
        decode_token("not-a-jwt")
    assert not exc_info.value.details


def test_refresh_tokens_are_unique_within_same_second():
    user_id, session_id = uuid.uuid4(), uuid.uuid4()
    assert create_refresh_token(user_id, session_id)[0] != create_refresh_token(user_id, session_id)[0]


def test_old_encryption_key_still_decrypts_during_rotation():
    old_key = Fernet.generate_key()
    old_cipher_text = Fernet(old_key).encrypt(b"meta-token").decode()
    rotating = MultiFernet([Fernet(Fernet.generate_key()), Fernet(old_key)])
    assert rotating.decrypt(old_cipher_text.encode()) == b"meta-token"


@pytest.mark.parametrize("environment", ["production", "staging"])
def test_default_secrets_rejected_outside_development(environment):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, ENVIRONMENT=environment)


def test_custom_secrets_accepted_in_production():
    Settings(
        _env_file=None,
        ENVIRONMENT="production",
        SECRET_KEY="a" * 64,
        ENCRYPTION_KEY=Fernet.generate_key().decode(),
    )


@pytest.mark.parametrize("password", ["short1a", "aaaaaaaaaa", "1234567890", "ab1ab1ab1ab1", "x" * 120 + "1" * 9])
def test_weak_registration_passwords_rejected(password):
    with pytest.raises(ValidationError):
        UserRegister(email="a@example.com", password=password, full_name="Test User", organization_name="Acme")


def test_strong_registration_password_accepted():
    UserRegister(email="a@example.com", password="Corr3ct-Horse-9", full_name="Test User", organization_name="Acme")


def test_only_owner_role_gets_wildcard_permission():
    assert permissions_for_role("owner") == ["*"]
    for role in ("admin", "agent", "viewer", None):
        assert "*" not in permissions_for_role(role)
