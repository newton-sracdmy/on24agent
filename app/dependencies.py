"""FastAPI dependencies for authentication, multi-tenant resolution, and RBAC authorization.
"""

from typing import Annotated, AsyncGenerator, Callable, List, Optional
from uuid import UUID

from fastapi import Depends, Header, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import MembershipRole, UserStatus
from app.database import get_admin_db_session, get_db_session, set_current_tenant_id
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
    x_org_header: Annotated[Optional[str], Header(alias="X-Organization-ID")] = None,
) -> AuthenticatedUserContext:
    """Validates JWT bearer token and sets organization context."""
    if not auth_header or not auth_header.credentials:
        raise AuthenticationError(message="Bearer token is required")

    payload = decode_token(auth_header.credentials)
    user_id_str = payload.get("sub")
    email = payload.get("email")

    if not user_id_str or not email:
        raise AuthenticationError(message="Token missing required claims")

    user_id = UUID(user_id_str)

    # Determine organization context (prefer header override if present)
    org_id: Optional[UUID] = None
    if x_org_header:
        try:
            org_id = UUID(x_org_header)
        except ValueError:
            pass
    elif payload.get("org_id"):
        try:
            org_id = UUID(payload["org_id"])
        except ValueError:
            pass

    # Populate thread/task context variable for RLS
    if org_id:
        set_current_tenant_id(org_id)

    return AuthenticatedUserContext(
        user_id=user_id,
        email=email,
        organization_id=org_id,
        role=payload.get("role"),
        permissions=payload.get("perms", []),
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
