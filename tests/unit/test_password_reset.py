"""Unit tests for the forgot/reset password flow, email rendering and SMTP fallback."""

import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError as PydanticValidationError

from app.common import email as email_module
from app.config import settings
from app.domains.identity import service as identity_service
from app.domains.identity.models import PasswordResetToken
from app.domains.identity.schemas import ResetPasswordRequest
from app.domains.identity.service import IdentityService, build_password_reset_url
from app.exceptions import ValidationError
from app.security import verify_password
from app.workers.tasks.email_tasks import render_password_changed_email, render_password_reset_email


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _result(obj):
    """A mock of session.execute(...) whose .scalars().first() returns obj."""
    res = MagicMock()
    res.scalars.return_value.first.return_value = obj
    return res


def _user(**overrides):
    data = dict(
        id=uuid.uuid4(), email="owner@example.com", full_name="Salman Khan",
        status="active", is_deleted=False, password_hash="old-hash",
    )
    data.update(overrides)
    return SimpleNamespace(**data)


@pytest.fixture
def db():
    session = MagicMock()
    session.execute = AsyncMock(return_value=MagicMock())
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    return session


@pytest.fixture
def enqueued(monkeypatch):
    calls = []

    async def fake_enqueue(task, **kwargs):
        calls.append((task.name, kwargs))

    monkeypatch.setattr(identity_service, "_enqueue_email", fake_enqueue)
    return calls


@pytest.fixture(autouse=True)
def no_redis(monkeypatch):
    rl = identity_service.rate_limit
    monkeypatch.setattr(rl, "ensure_password_reset_request_allowed", AsyncMock(return_value=True))
    monkeypatch.setattr(rl, "ensure_password_reset_attempt_allowed", AsyncMock())
    monkeypatch.setattr(rl, "clear_login_failures", AsyncMock())


# ------------------------------------------------------------------------------
# Request a reset link
# ------------------------------------------------------------------------------

async def test_request_reset_for_unknown_email_sends_nothing(db, enqueued):
    service = IdentityService(db)
    service.user_repo.get_by_email = AsyncMock(return_value=None)

    await service.request_password_reset("nobody@example.com", "1.2.3.4")

    db.add.assert_not_called()
    db.commit.assert_not_awaited()
    assert enqueued == []


async def test_request_reset_for_inactive_user_sends_nothing(db, enqueued):
    service = IdentityService(db)
    service.user_repo.get_by_email = AsyncMock(return_value=_user(status="suspended"))

    await service.request_password_reset("owner@example.com")

    db.add.assert_not_called()
    assert enqueued == []


async def test_request_reset_over_email_limit_sends_nothing(db, enqueued, monkeypatch):
    monkeypatch.setattr(
        identity_service.rate_limit, "ensure_password_reset_request_allowed", AsyncMock(return_value=False)
    )
    service = IdentityService(db)
    service.user_repo.get_by_email = AsyncMock(return_value=_user())

    await service.request_password_reset("owner@example.com")

    service.user_repo.get_by_email.assert_not_awaited()
    assert enqueued == []


async def test_request_reset_stores_only_hash_and_emails_link(db, enqueued):
    user = _user()
    service = IdentityService(db)
    service.user_repo.get_by_email = AsyncMock(return_value=user)

    await service.request_password_reset("Owner@Example.com", "1.2.3.4")

    token_row = db.add.call_args.args[0]
    assert isinstance(token_row, PasswordResetToken)
    assert token_row.user_id == user.id
    assert token_row.requested_ip == "1.2.3.4"
    expected_ttl = timedelta(minutes=settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES)
    assert abs((token_row.expires_at - datetime.now(timezone.utc)) - expected_ttl) < timedelta(seconds=5)
    # Earlier links are invalidated, and the row is committed before the email is queued
    assert db.execute.await_count == 1
    db.commit.assert_awaited_once()

    assert len(enqueued) == 1
    task_name, kwargs = enqueued[0]
    assert task_name.endswith("send_password_reset_email")
    assert kwargs["to_address"] == user.email
    raw_token = kwargs["reset_url"].split("#reset_token=", 1)[1]
    assert token_row.token_hash == _sha256(raw_token)
    assert raw_token not in token_row.token_hash
    assert len(raw_token) >= 40


def test_reset_url_keeps_token_in_fragment(monkeypatch):
    monkeypatch.setattr(settings, "APP_BASE_URL", "https://app.example.com/")
    assert build_password_reset_url("abc") == "https://app.example.com/#reset_token=abc"


# ------------------------------------------------------------------------------
# Reset the password
# ------------------------------------------------------------------------------

def _token_row(user_id, **overrides):
    data = dict(
        user_id=user_id, used_at=None,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
    )
    data.update(overrides)
    return SimpleNamespace(**data)


@pytest.mark.parametrize(
    "row_overrides",
    [
        {"used_at": datetime.now(timezone.utc)},
        {"expires_at": datetime.now(timezone.utc) - timedelta(seconds=1)},
    ],
    ids=["already-used", "expired"],
)
async def test_reset_rejects_used_or_expired_token(db, enqueued, row_overrides):
    user = _user()
    db.execute = AsyncMock(return_value=_result(_token_row(user.id, **row_overrides)))
    service = IdentityService(db)

    with pytest.raises(ValidationError):
        await service.reset_password("x" * 43, "NewPassword123")

    db.commit.assert_not_awaited()
    assert enqueued == []


async def test_reset_rejects_unknown_token(db, enqueued):
    db.execute = AsyncMock(return_value=_result(None))
    service = IdentityService(db)

    with pytest.raises(ValidationError):
        await service.reset_password("x" * 43, "NewPassword123")
    db.commit.assert_not_awaited()


async def test_reset_rejects_inactive_user(db, enqueued):
    user = _user(status="suspended")
    db.execute = AsyncMock(return_value=_result(_token_row(user.id)))
    service = IdentityService(db)
    service.user_repo.get_by_id = AsyncMock(return_value=user)

    with pytest.raises(ValidationError):
        await service.reset_password("x" * 43, "NewPassword123")
    assert user.password_hash == "old-hash"


async def test_reset_sets_password_revokes_sessions_and_notifies(db, enqueued):
    user = _user()
    db.execute = AsyncMock(return_value=_result(_token_row(user.id)))
    service = IdentityService(db)
    service.user_repo.get_by_id = AsyncMock(return_value=user)
    service.terminate_session = AsyncMock()

    await service.reset_password("x" * 43, "NewPassword123", "1.2.3.4")

    assert verify_password("NewPassword123", user.password_hash)
    service.terminate_session.assert_awaited_once_with(user.id)
    db.commit.assert_awaited_once()
    identity_service.rate_limit.clear_login_failures.assert_awaited_once_with(user.email)
    assert [name.rsplit(".", 1)[1] for name, _ in enqueued] == ["send_password_changed_email"]

    lookup = db.execute.await_args_list[0].args[0]
    assert "FOR UPDATE" in str(lookup.compile())


def test_reset_request_enforces_password_strength():
    with pytest.raises(PydanticValidationError):
        ResetPasswordRequest(token="x" * 43, new_password="onlyletters")
    with pytest.raises(PydanticValidationError):
        ResetPasswordRequest(token="x" * 43, new_password="short1")
    assert ResetPasswordRequest(token="x" * 43, new_password="GoodPassword9").new_password == "GoodPassword9"


# ------------------------------------------------------------------------------
# Email rendering and delivery
# ------------------------------------------------------------------------------

def test_reset_email_escapes_html_and_contains_link():
    url = "https://app.example.com/#reset_token=abc_DEF-123"
    subject, text_body, html_body = render_password_reset_email('<script>x</script> Doe', url, 30)
    assert "Reset your" in subject
    assert url in text_body and "30 minutes" in text_body
    assert f'href="{url}"' in html_body
    assert "<script>" not in html_body


def test_changed_email_mentions_sign_out():
    _, text_body, _ = render_password_changed_email("Salman Khan")
    assert text_body.startswith("Hi Salman,")
    assert "signed out" in text_body


def test_send_email_without_smtp_logs_in_development(monkeypatch, caplog):
    monkeypatch.setattr(settings, "SMTP_HOST", None)
    monkeypatch.setattr(settings, "ENVIRONMENT", "development")
    smtp = MagicMock()
    monkeypatch.setattr(email_module.smtplib, "SMTP", smtp)

    email_module.send_email("a@example.com", "Subject", "link: https://x/#reset_token=t", "<p>x</p>")

    smtp.assert_not_called()
    assert "reset_token=t" in caplog.text


def test_send_email_without_smtp_fails_in_production(monkeypatch):
    monkeypatch.setattr(settings, "SMTP_HOST", None)
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    with pytest.raises(email_module.EmailNotConfiguredError):
        email_module.send_email("a@example.com", "Subject", "text", "<p>x</p>")


def test_send_email_uses_starttls_and_login(monkeypatch):
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.example.com")
    monkeypatch.setattr(settings, "SMTP_SECURITY", "starttls")
    monkeypatch.setattr(settings, "SMTP_USERNAME", "user")
    monkeypatch.setattr(settings, "SMTP_PASSWORD", "pass")
    server = MagicMock()
    monkeypatch.setattr(email_module.smtplib, "SMTP", MagicMock(return_value=server))

    email_module.send_email("a@example.com", "Subject", "text", "<p>x</p>")

    server.starttls.assert_called_once()
    server.login.assert_called_once_with("user", "pass")
    server.send_message.assert_called_once()
    sent = server.send_message.call_args.args[0]
    assert sent["To"] == "a@example.com" and sent.is_multipart()
