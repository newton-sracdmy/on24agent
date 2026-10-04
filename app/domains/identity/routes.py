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

    return APIResponse.ok(
        data={
            "id": str(user.id),
            "email": user.email,
            "full_name": user.full_name,
            "organization_id": str(user_context.organization_id) if user_context.organization_id else None,
            "role": user_context.role,
            "permissions": user_context.permissions,
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
