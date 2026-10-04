"""Generic asynchronous repository pattern for SQLAlchemy 2.0 models.

Provides standardized CRUD, soft-deletion handling, and multi-tenant scoping.
"""

from typing import Any, Dict, Generic, List, Optional, Sequence, Type, TypeVar
from uuid import UUID

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.models import Base
from app.common.pagination import PaginationParams, paginate_query
from app.common.schemas import PaginationMeta

ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    """Base repository handling queries and mutations for a specific model."""

    def __init__(self, model: Type[ModelType], session: AsyncSession):
        self.model = model
        self.session = session

    async def get_by_id(
        self,
        record_id: UUID,
        organization_id: Optional[UUID] = None,
        include_deleted: bool = False,
    ) -> Optional[ModelType]:
        """Fetch a single record by primary key with optional tenant isolation."""
        query = select(self.model).where(self.model.id == record_id)

        if organization_id and hasattr(self.model, "organization_id"):
            query = query.where(self.model.organization_id == organization_id)

        if not include_deleted and hasattr(self.model, "is_deleted"):
            query = query.where(self.model.is_deleted == False)  # noqa: E712

        result = await self.session.execute(query)
        return result.scalars().first()

    async def list_paginated(
        self,
        params: PaginationParams,
        organization_id: Optional[UUID] = None,
        filters: Optional[List[Any]] = None,
        include_deleted: bool = False,
    ) -> tuple[Sequence[ModelType], PaginationMeta]:
        """List records with pagination, filtering, and optional tenant scoping."""
        query = select(self.model)

        if organization_id and hasattr(self.model, "organization_id"):
            query = query.where(self.model.organization_id == organization_id)

        if not include_deleted and hasattr(self.model, "is_deleted"):
            query = query.where(self.model.is_deleted == False)  # noqa: E712

        if filters:
            for condition in filters:
                query = query.where(condition)

        if hasattr(self.model, "created_at"):
            query = query.order_by(self.model.created_at.desc())

        return await paginate_query(self.session, query, params)

    async def create(self, **kwargs: Any) -> ModelType:
        """Instantiate, persist, and refresh a new model entity."""
        instance = self.model(**kwargs)
        self.session.add(instance)
        await self.session.flush()
        await self.session.refresh(instance)
        return instance

    async def update(
        self,
        instance: ModelType,
        update_data: Dict[str, Any],
    ) -> ModelType:
        """Update fields on an existing model entity."""
        for key, value in update_data.items():
            if hasattr(instance, key) and value is not None:
                setattr(instance, key, value)
        await self.session.flush()
        await self.session.refresh(instance)
        return instance

    async def soft_delete(self, instance: ModelType) -> None:
        """Mark record as soft-deleted if supported, or perform hard delete."""
        if hasattr(instance, "soft_delete"):
            instance.soft_delete()
            await self.session.flush()
        else:
            await self.session.delete(instance)
            await self.session.flush()

    async def hard_delete(self, instance: ModelType) -> None:
        """Permanently delete an entity from database."""
        await self.session.delete(instance)
        await self.session.flush()

    async def exists(
        self,
        organization_id: Optional[UUID] = None,
        filters: Optional[List[Any]] = None,
    ) -> bool:
        """Check if any matching record exists."""
        query = select(func.count(self.model.id))
        if organization_id and hasattr(self.model, "organization_id"):
            query = query.where(self.model.organization_id == organization_id)
        if filters:
            for condition in filters:
                query = query.where(condition)
        result = await self.session.execute(query)
        count = result.scalar() or 0
        return count > 0
