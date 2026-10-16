"""FastAPI router for Identity, Auth, and Organization operations."""

from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.schemas import APIResponse
from app.constants import AgentOnlineStatus
from app.dependencies import (
    AuthenticatedUserContext,
    get_current_user,
    get_db,
    require_tenant,
)
from app.domains.identity.schemas import (
    MembershipResponse,
    RefreshTokenRequest,
    TokenResponse,
    UserLogin,
    UserRegister,
    UserResponse,
)
from app.domains.identity.service import IdentityService

router = APIRouter()


@router.post("/register", status_code=status.HTTP_201_CREATED, response_model=APIResponse[TokenResponse])
async def register(
    payload: UserRegister,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[TokenResponse]:
    """Register a new account, create initial workspace, and grant Owner credentials."""
    ip = request.client.host if request.client else None
    agent = request.headers.get("User-Agent")
    service = IdentityService(db)
    _, _, token_response = await service.register_user_and_workspace(
        payload, ip_address=ip, user_agent=agent
    )
    return APIResponse.ok(data=token_response)


@router.post("/login", response_model=APIResponse[TokenResponse])
async def login(
    payload: UserLogin,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[TokenResponse]:
    """Authenticate with email and password."""
    ip = request.client.host if request.client else None
    agent = request.headers.get("User-Agent")
    service = IdentityService(db)
    token_response = await service.authenticate_user(
        payload, ip_address=ip, user_agent=agent
    )
    return APIResponse.ok(data=token_response)


@router.post("/refresh", response_model=APIResponse[TokenResponse])
async def refresh(
    payload: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db),
) -> APIResponse[TokenResponse]:
    """Exchange a refresh token for a new access/refresh token pair (single use)."""
    service = IdentityService(db)
    token_response = await service.refresh_tokens(payload.refresh_token)
    return APIResponse.ok(data=token_response)


@router.post("/logout", response_model=APIResponse[dict])
async def logout(
    user_context: AuthenticatedUserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[dict]:
    """Terminate active user session and revoke authorization."""
    service = IdentityService(db)
    await service.terminate_session(user_context.user_id)
    return APIResponse.ok(data={"success": True, "message": "Successfully logged out"})


@router.get("/me", response_model=APIResponse[dict])
async def get_my_profile(
    user_context: AuthenticatedUserContext = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[dict]:
    """Fetch current user identity context and active workspace details."""
    service = IdentityService(db)
    user = await service.user_repo.get_by_id(user_context.user_id)
    if not user:
        return APIResponse.fail(code="USER_NOT_FOUND", message="User record not found")

    memberships = await service.membership_repo.list_user_memberships(user.id)
    orgs_list = []
    for m in memberships:
        if m.organization:
            orgs_list.append({
                "id": str(m.organization.id),
                "name": m.organization.name,
                "slug": m.organization.slug,
                "role": m.role,
            })

    return APIResponse.ok(
        data={
            "id": str(user.id),
            "email": user.email,
            "full_name": user.full_name,
            "organization_id": str(user_context.organization_id) if user_context.organization_id else (orgs_list[0]["id"] if orgs_list else None),
            "role": user_context.role,
            "permissions": user_context.permissions,
            "organizations": orgs_list,
        }
    )


@router.patch("/presence", response_model=APIResponse[dict])
async def update_presence(
    agent_status: AgentOnlineStatus,
    user_context: AuthenticatedUserContext = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[dict]:
    """Update agent's real-time routing availability (online, busy, away, offline)."""
    service = IdentityService(db)
    await service.update_agent_status(
        user_context.organization_id, user_context.user_id, agent_status
    )
    return APIResponse.ok(data={"status": agent_status.value})


@router.get("/members", response_model=APIResponse[List[MembershipResponse]])
async def list_members(
    user_context: AuthenticatedUserContext = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[List[MembershipResponse]]:
    """List all team members in the active workspace."""
    service = IdentityService(db)
    members = await service.membership_repo.list_org_members(user_context.organization_id)
    return APIResponse.ok(data=members)
