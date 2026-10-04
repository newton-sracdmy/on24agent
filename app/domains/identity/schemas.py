"""Pydantic schemas for authentication, identity, and organization management."""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import EmailStr, Field

from app.common.schemas import BaseSchema
from app.constants import AgentOnlineStatus, MembershipRole, OrganizationStatus, UserStatus


# ==============================================================================
# Authentication Schemas
# ==============================================================================

class UserRegister(BaseSchema):
    email: EmailStr = Field(..., description="Corporate email address")
    password: str = Field(..., min_length=8, description="Strong password minimum 8 chars")
    full_name: str = Field(..., min_length=2, max_length=255, description="Full legal name")
    organization_name: str = Field(..., min_length=2, max_length=255, description="Initial workspace name")


class UserLogin(BaseSchema):
    email: EmailStr
    password: str
    organization_id: Optional[UUID] = None


class TokenResponse(BaseSchema):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in_seconds: int
    user_id: UUID
    organization_id: Optional[UUID]
    role: Optional[str]


class RefreshTokenRequest(BaseSchema):
    refresh_token: str


# ==============================================================================
# User Schemas
# ==============================================================================

class UserResponse(BaseSchema):
    id: UUID
    email: EmailStr
    full_name: str
    phone_number: Optional[str] = None
    status: UserStatus
    is_superuser: bool
    avatar_url: Optional[str] = None
    timezone: str
    locale: str
    created_at: datetime
    updated_at: datetime


class UserUpdate(BaseSchema):
    full_name: Optional[str] = Field(None, min_length=2, max_length=255)
    phone_number: Optional[str] = None
    avatar_url: Optional[str] = None
    timezone: Optional[str] = None
    locale: Optional[str] = None


# ==============================================================================
# Organization & Membership Schemas
# ==============================================================================

class OrganizationCreate(BaseSchema):
    name: str = Field(..., min_length=2, max_length=255)
    slug: Optional[str] = Field(None, min_length=2, max_length=100)
    default_locale: str = "en"
    timezone: str = "UTC"


class OrganizationResponse(BaseSchema):
    id: UUID
    name: str
    slug: str
    status: OrganizationStatus
    logo_url: Optional[str] = None
    default_locale: str
    timezone: str
    created_at: datetime


class OrganizationUpdate(BaseSchema):
    name: Optional[str] = Field(None, min_length=2, max_length=255)
    logo_url: Optional[str] = None
    default_locale: Optional[str] = None
    timezone: Optional[str] = None
    settings: Optional[dict] = None


class MembershipResponse(BaseSchema):
    id: UUID
    organization_id: UUID
    user_id: UUID
    role: str
    agent_status: AgentOnlineStatus
    max_concurrent_chats: int
    is_active: bool
    user: Optional[UserResponse] = None
    created_at: datetime


class MemberInvite(BaseSchema):
    email: EmailStr
    role_id: UUID


class MemberUpdate(BaseSchema):
    role_id: Optional[UUID] = None
    agent_status: Optional[AgentOnlineStatus] = None
    max_concurrent_chats: Optional[int] = Field(None, ge=1, le=50)
    is_active: Optional[bool] = None


# ==============================================================================
# Roles & Permissions Schemas
# ==============================================================================

class PermissionResponse(BaseSchema):
    id: UUID
    slug: str
    name: str
    module: str
    description: Optional[str] = None


class RoleResponse(BaseSchema):
    id: UUID
    organization_id: Optional[UUID] = None
    name: str
    slug: str
    description: Optional[str] = None
    is_system: bool
    permissions: List[PermissionResponse] = []


class RoleCreate(BaseSchema):
    name: str = Field(..., min_length=2, max_length=100)
    slug: str = Field(..., min_length=2, max_length=100)
    description: Optional[str] = None
    permission_ids: List[UUID] = Field(default_factory=list)
