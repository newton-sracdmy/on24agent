"""FastAPI dependencies for authentication, multi-tenant resolution, and RBAC authorization.
"""

from datetime import datetime, timezone
from typing import Annotated, AsyncGenerator, Callable, List, Optional
from uuid import UUID

from fastapi import Depends, Header, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import MembershipRole, UserStatus
from app.database import get_admin_db_session, get_db_session, set_current_tenant_id
from app.domains.identity.models import Membership, Session, User
from app.domains.identity.service import permissions_for_role
from app.exceptions import AuthenticationError, PermissionDeniedError
from app.security import decode_token

# Bearer token security scheme
security_scheme = HTTPBearer(auto_error=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Database session dependency enforcing RLS."""
    async for session in get_db_session():
        yield session


async def get_admin_db() -> AsyncGenerator[AsyncSession, None]:
    """Administrative database session dependency."""
    async for session in get_admin_db_session():
        yield session


class AuthenticatedUserContext:
    """Encapsulates authenticated caller context for dependency injection."""

    def __init__(
        self,
        user_id: UUID,
        email: str,
        organization_id: Optional[UUID] = None,
        role: Optional[str] = None,
        permissions: Optional[List[str]] = None,
    ):
        self.user_id = user_id
        self.email = email
        self.organization_id = organization_id
        self.role = role
        self.permissions = permissions or []

    def has_permission(self, permission: str) -> bool:
        if self.role in (MembershipRole.OWNER.value, "owner"):
            return True
        return permission in self.permissions


async def get_current_user(
    auth_header: Annotated[Optional[HTTPAuthorizationCredentials], Security(security_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
    x_org_header: Annotated[Optional[str], Header(alias="X-Organization-ID")] = None,
) -> AuthenticatedUserContext:
    """Validates the bearer token against the live session and resolves organization context.

    The token only identifies the caller. Session validity, account status, organization
    membership and role are all read from the database on every request, so logout,
    suspension and membership removal take effect immediately, and X-Organization-ID can
    only select an organization the caller actually belongs to.
    """
    if not auth_header or not auth_header.credentials:
        raise AuthenticationError(message="Bearer token is required")

    payload = decode_token(auth_header.credentials, expected_type="access")
    try:
        user_id = UUID(payload["sub"])
        session_id = UUID(payload["sid"])
    except (KeyError, TypeError, ValueError):
        raise AuthenticationError(message="Token missing required claims")

    now = datetime.now(timezone.utc)
    session_obj = (
        await db.execute(
            select(Session).where(
                Session.id == session_id,
                Session.user_id == user_id,
                Session.is_revoked == False,  # noqa: E712
                Session.expires_at > now,
            )
        )
    ).scalars().first()
    if not session_obj:
        raise AuthenticationError(message="Session has been revoked or expired")

    user = (
        await db.execute(
            select(User).where(
                User.id == user_id,
                User.is_deleted == False,  # noqa: E712
                User.status == UserStatus.ACTIVE.value,
            )
        )
    ).scalars().first()
    if not user:
        raise AuthenticationError(message="Account is not active")

    # Organization requested by header, else the one the session was opened for
    org_id: Optional[UUID] = None
    if x_org_header:
        try:
            org_id = UUID(x_org_header)
        except ValueError:
            raise PermissionDeniedError(message="X-Organization-ID is not a valid UUID")
    elif session_obj.organization_id:
        org_id = session_obj.organization_id

    role: Optional[str] = None
    if org_id:
        # Scope the transaction to the org before reading memberships (RLS-protected table);
        # the endpoint reuses this same session, so its queries stay scoped to the verified org.
        await db.execute(
            text("SELECT set_config('app.current_org_id', :org_id, true)"),
            {"org_id": str(org_id)},
        )
        membership = (
            await db.execute(
                select(Membership).where(
                    Membership.organization_id == org_id,
                    Membership.user_id == user_id,
                    Membership.is_active == True,  # noqa: E712
                )
            )
        ).scalars().first()
        if not membership:
            raise PermissionDeniedError(message="You are not a member of the requested organization")
        role = membership.role
        set_current_tenant_id(org_id)

    return AuthenticatedUserContext(
        user_id=user_id,
        email=user.email,
        organization_id=org_id,
        role=role,
        permissions=permissions_for_role(role) if role else [],
    )


def require_tenant(
    user_context: Annotated[AuthenticatedUserContext, Depends(get_current_user)]
) -> AuthenticatedUserContext:
    """Guarantees that an organization context is active for the operation."""
    if not user_context.organization_id:
        raise PermissionDeniedError(
            message="An organization context (X-Organization-ID) is required for this operation"
        )
    return user_context


def require_permission(permission: str) -> Callable:
    """Factory creating dependency that verifies caller has specific RBAC permission."""

    async def _permission_dependency(
        user_context: Annotated[AuthenticatedUserContext, Depends(require_tenant)]
    ) -> AuthenticatedUserContext:
        if not user_context.has_permission(permission):
            raise PermissionDeniedError(
                message=f"Caller lacks required permission: '{permission}'"
            )
        return user_context

    return _permission_dependency


def require_role(allowed_roles: List[MembershipRole]) -> Callable:
    """Factory creating dependency that verifies caller has one of the allowed roles."""
    role_values = [r.value for r in allowed_roles]

    async def _role_dependency(
        user_context: Annotated[AuthenticatedUserContext, Depends(require_tenant)]
    ) -> AuthenticatedUserContext:
        if user_context.role not in role_values and user_context.role != MembershipRole.OWNER.value:
            raise PermissionDeniedError(
                message=f"Caller role '{user_context.role}' does not satisfy requirement: {role_values}"
            )
        return user_context

    return _role_dependency
