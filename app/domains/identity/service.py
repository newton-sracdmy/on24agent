"""Business logic service for identity, registration, auth, and tenancy."""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.constants import AgentOnlineStatus, MembershipRole, OrganizationStatus, UserStatus
from app.domains.identity.models import (
    Membership,
    Organization,
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
from app.domains.identity.schemas import TokenResponse, UserLogin, UserRegister
from app.exceptions import AuthenticationError, ResourceConflictError, ResourceNotFoundError
from app.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_password_hash,
    verify_password,
)


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
        # Check if email is already taken
        existing_user = await self.user_repo.get_by_email(data.email)
        if existing_user:
            raise ResourceConflictError("A user with this email address already exists")

        # Create User
        password_hash = get_password_hash(data.password)
        user = await self.user_repo.create(
            email=data.email.lower(),
            password_hash=password_hash,
            full_name=data.full_name,
            status=UserStatus.ACTIVE.value,
        )

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

        # Create Session & Refresh Token
        session_expiry = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
        session_obj = await self.session_repo.create(
            user_id=user.id,
            organization_id=org.id,
            ip_address=ip_address,
            user_agent=user_agent,
            expires_at=session_expiry,
        )

        raw_refresh_token, refresh_expiry = create_refresh_token(user.id, session_obj.id)
        token_hash = hashlib.sha256(raw_refresh_token.encode("utf-8")).hexdigest()

        refresh_token_record = RefreshToken(
            session_id=session_obj.id,
            token_hash=token_hash,
            expires_at=refresh_expiry,
        )
        self.session.add(refresh_token_record)
        await self.session.flush()

        # Create Access Token
        access_token = create_access_token(
            user_id=user.id,
            email=user.email,
            organization_id=org.id,
            role=MembershipRole.OWNER.value,
            permissions=["*"],
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
        user = await self.user_repo.get_by_email(credentials.email)
        if not user or not verify_password(credentials.password, user.password_hash):
            raise AuthenticationError("Invalid email or password")

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

        raw_refresh_token, refresh_expiry = create_refresh_token(user.id, session_obj.id)
        token_hash = hashlib.sha256(raw_refresh_token.encode("utf-8")).hexdigest()

        refresh_token_record = RefreshToken(
            session_id=session_obj.id,
            token_hash=token_hash,
            expires_at=refresh_expiry,
        )
        self.session.add(refresh_token_record)
        await self.session.flush()

        access_token = create_access_token(
            user_id=user.id,
            email=user.email,
            organization_id=org_id,
            role=role_slug,
            permissions=["*"] if role_slug == MembershipRole.OWNER.value else ["conversations:read", "messages:write"],
        )

        return TokenResponse(
            access_token=access_token,
            refresh_token=raw_refresh_token,
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
