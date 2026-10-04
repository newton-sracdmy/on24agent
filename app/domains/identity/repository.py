"""Data access repositories for Identity and Multi-Tenancy models."""

from typing import List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.common.repository import BaseRepository
from app.domains.identity.models import (
    Membership,
    Organization,
    Permission,
    RefreshToken,
    Role,
    RolePermission,
    Session,
    User,
)


class UserRepository(BaseRepository[User]):
    def __init__(self, session: AsyncSession):
        super().__init__(User, session)

    async def get_by_email(self, email: str) -> Optional[User]:
        query = select(User).where(User.email == email.lower(), User.is_deleted == False)  # noqa: E712
        result = await self.session.execute(query)
        return result.scalars().first()


class OrganizationRepository(BaseRepository[Organization]):
    def __init__(self, session: AsyncSession):
        super().__init__(Organization, session)

    async def get_by_slug(self, slug: str) -> Optional[Organization]:
        query = select(Organization).where(Organization.slug == slug.lower(), Organization.is_deleted == False)  # noqa: E712
        result = await self.session.execute(query)
        return result.scalars().first()


class MembershipRepository(BaseRepository[Membership]):
    def __init__(self, session: AsyncSession):
        super().__init__(Membership, session)

    async def get_by_org_and_user(self, org_id: UUID, user_id: UUID) -> Optional[Membership]:
        query = (
            select(Membership)
            .where(
                Membership.organization_id == org_id,
                Membership.user_id == user_id,
                Membership.is_active == True,  # noqa: E712
            )
            .options(selectinload(Membership.user), selectinload(Membership.role_obj))
        )
        result = await self.session.execute(query)
        return result.scalars().first()

    async def list_org_members(self, org_id: UUID) -> List[Membership]:
        query = (
            select(Membership)
            .where(Membership.organization_id == org_id)
            .options(selectinload(Membership.user), selectinload(Membership.role_obj))
            .order_by(Membership.created_at.asc())
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())


class RoleRepository(BaseRepository[Role]):
    def __init__(self, session: AsyncSession):
        super().__init__(Role, session)

    async def get_by_slug_for_org(self, slug: str, org_id: Optional[UUID] = None) -> Optional[Role]:
        query = (
            select(Role)
            .where(
                Role.slug == slug,
                (Role.organization_id == org_id) | (Role.organization_id.is_(None)),
            )
            .options(selectinload(Role.role_permissions).selectinload(RolePermission.permission))
        )
        result = await self.session.execute(query)
        return result.scalars().first()


class SessionRepository(BaseRepository[Session]):
    def __init__(self, session: AsyncSession):
        super().__init__(Session, session)

    async def get_active_session(self, session_id: UUID) -> Optional[Session]:
        query = select(Session).where(
            Session.id == session_id,
            Session.is_revoked == False,  # noqa: E712
        )
        result = await self.session.execute(query)
        return result.scalars().first()
