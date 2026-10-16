"""Business logic service for identity, registration, auth, and tenancy."""

import asyncio
import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.constants import AgentOnlineStatus, MembershipRole, OrganizationStatus, UserStatus
from app.domains.identity.models import (
    Membership,
    Organization,
    PasswordResetToken,
    RefreshToken,
    Role,
    Session,
    User,
)
from app.domains.identity.repository import (
    MembershipRepository,
    OrganizationRepository,
    RoleRepository,
    SessionRepository,
    UserRepository,
)
from app.domains.identity import rate_limit
from app.domains.identity.schemas import TokenResponse, UserLogin, UserRegister
from app.domains.usage.models import CreditBalance
from app.workers.tasks.email_tasks import send_password_changed_email, send_password_reset_email
from app.exceptions import AuthenticationError, ResourceConflictError, ResourceNotFoundError, ValidationError
from app.security import (
    burn_password_check,
    create_access_token,
    create_refresh_token,
    decode_token,
    get_password_hash,
    verify_password,
)

logger = logging.getLogger("identity_service")

INVALID_RESET_TOKEN_MESSAGE = "This password reset link is invalid or has expired. Please request a new one."


def permissions_for_role(role: Optional[str]) -> list[str]:
    """Permission set granted to a membership role."""
    if role == MembershipRole.OWNER.value:
        return ["*"]
    return ["conversations:read", "messages:write"]


def _hash_refresh_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def _hash_reset_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def build_password_reset_url(raw_token: str) -> str:
    # In the URL fragment, so the token never reaches server access logs or Referer headers
    return f"{settings.APP_BASE_URL.rstrip('/')}/#reset_token={raw_token}"


async def _enqueue_email(task, **kwargs) -> None:
    """Queue an email task without blocking the event loop or failing the request."""
    try:
        await asyncio.to_thread(task.delay, **kwargs)
    except Exception:
        logger.exception(f"Failed to enqueue {task.name}")


class IdentityService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.user_repo = UserRepository(session)
        self.org_repo = OrganizationRepository(session)
        self.membership_repo = MembershipRepository(session)
        self.role_repo = RoleRepository(session)
        self.session_repo = SessionRepository(session)

    async def register_user_and_workspace(
        self, data: UserRegister, ip_address: Optional[str] = None, user_agent: Optional[str] = None
    ) -> Tuple[User, Organization, TokenResponse]:
        """Registers a new account, provisions an organization workspace, and assigns Owner role."""
        await rate_limit.ensure_registration_allowed(ip_address)

        # Check if email is already taken
        existing_user = await self.user_repo.get_by_email(data.email)
        if existing_user:
            raise ResourceConflictError("A user with this email address already exists")

        # Create User (the unique constraint catches a concurrent registration of the same email)
        password_hash = get_password_hash(data.password)
        try:
            async with self.session.begin_nested():
                user = await self.user_repo.create(
                    email=data.email.lower(),
                    password_hash=password_hash,
                    full_name=data.full_name,
                    status=UserStatus.ACTIVE.value,
                )
        except IntegrityError:
            raise ResourceConflictError("A user with this email address already exists")

        # Generate unique slug for organization
        base_slug = data.organization_name.lower().replace(" ", "-")[:40]
        slug = f"{base_slug}-{secrets.token_hex(3)}"

        # Create Organization
        org = await self.org_repo.create(
            name=data.organization_name,
            slug=slug,
            status=OrganizationStatus.ACTIVE.value,
        )

        # Retrieve or create Owner Role
        owner_role = await self.role_repo.get_by_slug_for_org("owner", org.id)
        if not owner_role:
            owner_role = await self.role_repo.create(
                organization_id=org.id,
                name="Owner",
                slug="owner",
                description="Workspace owner with full unrestricted access",
                is_system=True,
            )

        # Create Membership
        await self.membership_repo.create(
            organization_id=org.id,
            user_id=user.id,
            role_id=owner_role.id,
            role=MembershipRole.OWNER.value,
            agent_status=AgentOnlineStatus.ONLINE.value,
            is_active=True,
        )

        # Provision 10,000 free starter credits for the new workspace
        starter_balance = CreditBalance(
            organization_id=org.id,
            balance_credits=10000.0,
            lifetime_granted_credits=10000.0,
            lifetime_consumed_credits=0.0,
        )
        self.session.add(starter_balance)
        await self.session.flush()

        # Create Session & Refresh Token
        session_expiry = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
        session_obj = await self.session_repo.create(
            user_id=user.id,
            organization_id=org.id,
            ip_address=ip_address,
            user_agent=user_agent,
            expires_at=session_expiry,
        )

        raw_refresh_token = await self._issue_refresh_token(user.id, session_obj.id)

        # Create Access Token
        access_token = create_access_token(
            user_id=user.id,
            email=user.email,
            session_id=session_obj.id,
            organization_id=org.id,
            role=MembershipRole.OWNER.value,
            permissions=permissions_for_role(MembershipRole.OWNER.value),
        )

        token_response = TokenResponse(
            access_token=access_token,
            refresh_token=raw_refresh_token,
            expires_in_seconds=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            user_id=user.id,
            organization_id=org.id,
            role=MembershipRole.OWNER.value,
        )

        return user, org, token_response

    async def authenticate_user(
        self,
        credentials: UserLogin,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> TokenResponse:
        """Authenticates user credentials and returns tokens for the active organization."""
        await rate_limit.ensure_login_allowed(credentials.email, ip_address)

        user = await self.user_repo.get_by_email(credentials.email)
        if not user:
            burn_password_check(credentials.password)
        if not user or not verify_password(credentials.password, user.password_hash):
            await rate_limit.record_login_failure(credentials.email, ip_address)
            raise AuthenticationError("Invalid email or password")
        await rate_limit.clear_login_failures(credentials.email)

        if user.status != UserStatus.ACTIVE.value:
            raise AuthenticationError(f"Account is {user.status}")

        # Resolve organization
        org_id = credentials.organization_id
        role_slug = MembershipRole.AGENT.value
        perms = []

        if org_id:
            membership = await self.membership_repo.get_by_org_and_user(org_id, user.id)
            if not membership:
                raise AuthenticationError("User is not an active member of the requested organization")
            role_slug = membership.role
        else:
            # Pick first active membership
            memberships = await self.session.execute(
                Membership.__table__.select().where(
                    Membership.user_id == user.id, Membership.is_active == True  # noqa: E712
                )
            )
            first_m = memberships.first()
            if first_m:
                org_id = first_m.organization_id
                role_slug = first_m.role

        # Create Session
        session_expiry = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
        session_obj = await self.session_repo.create(
            user_id=user.id,
            organization_id=org_id,
            ip_address=ip_address,
            user_agent=user_agent,
            expires_at=session_expiry,
        )

        raw_refresh_token = await self._issue_refresh_token(user.id, session_obj.id)

        access_token = create_access_token(
            user_id=user.id,
            email=user.email,
            session_id=session_obj.id,
            organization_id=org_id,
            role=role_slug,
            permissions=permissions_for_role(role_slug),
        )

        return TokenResponse(
            access_token=access_token,
            refresh_token=raw_refresh_token,
            expires_in_seconds=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            user_id=user.id,
            organization_id=org_id,
            role=role_slug,
        )

    async def _issue_refresh_token(self, user_id: UUID, session_id: UUID) -> str:
        """Create a refresh token for the session and store only its hash."""
        raw_refresh_token, refresh_expiry = create_refresh_token(user_id, session_id)
        self.session.add(
            RefreshToken(
                session_id=session_id,
                token_hash=_hash_refresh_token(raw_refresh_token),
                expires_at=refresh_expiry,
            )
        )
        await self.session.flush()
        return raw_refresh_token

    async def _revoke_session(self, session_id: UUID) -> None:
        await self.session.execute(
            update(Session).where(Session.id == session_id).values(is_revoked=True)
        )
        await self.session.execute(
            update(RefreshToken).where(RefreshToken.session_id == session_id).values(is_revoked=True)
        )
        await self.session.flush()

    async def refresh_tokens(self, raw_refresh_token: str) -> TokenResponse:
        """Rotate a refresh token: revoke the presented one and issue a new access/refresh pair.

        Presenting an already-rotated token means it was stolen or replayed, so the whole
        session is revoked.
        """
        payload = decode_token(raw_refresh_token, expected_type="refresh")
        now = datetime.now(timezone.utc)

        record = (
            await self.session.execute(
                select(RefreshToken).where(RefreshToken.token_hash == _hash_refresh_token(raw_refresh_token))
            )
        ).scalars().first()
        if not record or str(record.session_id) != payload.get("session_id"):
            raise AuthenticationError("Invalid refresh token")
        if record.is_revoked:
            await self._revoke_session(record.session_id)
            # Commit the revocation even though this request fails
            await self.session.commit()
            raise AuthenticationError("Refresh token has already been used; session revoked")
        if record.expires_at <= now:
            raise AuthenticationError("Refresh token has expired")

        session_obj = await self.session_repo.get_active_session(record.session_id)
        if not session_obj or session_obj.expires_at <= now:
            raise AuthenticationError("Session has been revoked or expired")

        user = await self.user_repo.get_by_id(session_obj.user_id)
        if not user or user.is_deleted or user.status != UserStatus.ACTIVE.value:
            raise AuthenticationError("Account is not active")

        org_id = session_obj.organization_id
        role_slug = None
        if org_id:
            membership = await self.membership_repo.get_by_org_and_user(org_id, user.id)
            if not membership:
                await self._revoke_session(session_obj.id)
                await self.session.commit()
                raise AuthenticationError("User is no longer a member of this organization")
            role_slug = membership.role

        record.is_revoked = True
        session_obj.last_active_at = now
        new_refresh_token = await self._issue_refresh_token(user.id, session_obj.id)

        access_token = create_access_token(
            user_id=user.id,
            email=user.email,
            session_id=session_obj.id,
            organization_id=org_id,
            role=role_slug,
            permissions=permissions_for_role(role_slug),
        )
        return TokenResponse(
            access_token=access_token,
            refresh_token=new_refresh_token,
            expires_in_seconds=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            user_id=user.id,
            organization_id=org_id,
            role=role_slug,
        )

    async def update_agent_status(
        self, org_id: UUID, user_id: UUID, status_val: AgentOnlineStatus
    ) -> None:
        """Updates online presence and availability for skill-based routing."""
        membership = await self.membership_repo.get_by_org_and_user(org_id, user_id)
        if not membership:
            raise ResourceNotFoundError("Membership", f"{org_id}/{user_id}")
        membership.agent_status = status_val.value
        await self.session.flush()

    async def terminate_session(self, user_id: UUID) -> None:
        """Revokes all active sessions (and their refresh tokens) for the user upon logout."""
        await self.session_repo.revoke_user_sessions(user_id)
        await self.session.execute(
            update(RefreshToken)
            .where(RefreshToken.session_id.in_(select(Session.id).where(Session.user_id == user_id)))
            .values(is_revoked=True)
        )
        await self.session.flush()

    async def request_password_reset(self, email: str, ip_address: Optional[str] = None) -> None:
        """Email a single-use reset link if the address belongs to an active account.

        Returns the same way whether or not the account exists, so the endpoint cannot be used
        to discover registered emails. A new request invalidates any earlier unused link.
        """
        if not await rate_limit.ensure_password_reset_request_allowed(email, ip_address):
            logger.info("Password reset request dropped: per-email hourly limit reached")
            return

        user = await self.user_repo.get_by_email(email)
        if not user or user.status != UserStatus.ACTIVE.value:
            return

        now = datetime.now(timezone.utc)
        await self._invalidate_reset_tokens(user.id, now)
        raw_token = secrets.token_urlsafe(32)
        self.session.add(
            PasswordResetToken(
                user_id=user.id,
                token_hash=_hash_reset_token(raw_token),
                expires_at=now + timedelta(minutes=settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES),
                requested_ip=ip_address,
            )
        )
        # The link must be valid by the time the email can arrive
        await self.session.commit()

        await _enqueue_email(
            send_password_reset_email,
            to_address=user.email,
            full_name=user.full_name,
            reset_url=build_password_reset_url(raw_token),
            expires_minutes=settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES,
        )
        logger.info(f"Password reset link issued for user {user.id}")

    async def reset_password(self, raw_token: str, new_password: str, ip_address: Optional[str] = None) -> None:
        """Set a new password from a reset token, then sign the user out everywhere."""
        await rate_limit.ensure_password_reset_attempt_allowed(ip_address)

        now = datetime.now(timezone.utc)
        # Row lock so two concurrent submissions of the same token cannot both succeed
        record = (
            await self.session.execute(
                select(PasswordResetToken)
                .where(PasswordResetToken.token_hash == _hash_reset_token(raw_token))
                .with_for_update()
            )
        ).scalars().first()
        if not record or record.used_at is not None or record.expires_at <= now:
            raise ValidationError(INVALID_RESET_TOKEN_MESSAGE)

        user = await self.user_repo.get_by_id(record.user_id)
        if not user or user.is_deleted or user.status != UserStatus.ACTIVE.value:
            raise ValidationError(INVALID_RESET_TOKEN_MESSAGE)

        user.password_hash = get_password_hash(new_password)
        await self._invalidate_reset_tokens(user.id, now)
        # Whoever knew the old password must lose access, including live access tokens
        await self.terminate_session(user.id)
        await self.session.commit()

        await rate_limit.clear_login_failures(user.email)
        await _enqueue_email(send_password_changed_email, to_address=user.email, full_name=user.full_name)
        logger.info(f"Password reset completed for user {user.id}")

    async def _invalidate_reset_tokens(self, user_id: UUID, now: datetime) -> None:
        await self.session.execute(
            update(PasswordResetToken)
            .where(PasswordResetToken.user_id == user_id, PasswordResetToken.used_at.is_(None))
            .values(used_at=now, updated_at=now)
        )
