"""Database engine, connection pooling, and multi-tenant RLS session management.

Provides async sessions configured for PostgreSQL Row-Level Security (RLS)
via `SET LOCAL app.current_org_id = :org_id`.
"""

import contextvars
from typing import AsyncGenerator, Optional
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import settings

# Context variable holding the active organization ID for the current async task
_current_tenant_id: contextvars.ContextVar[Optional[UUID]] = contextvars.ContextVar(
    "current_tenant_id", default=None
)


def get_current_tenant_id() -> Optional[UUID]:
    """Retrieve the current tenant organization ID from context."""
    return _current_tenant_id.get()


def set_current_tenant_id(org_id: Optional[UUID]) -> None:
    """Set the current tenant organization ID in context."""
    _current_tenant_id.set(org_id)


# Application Database Engine (Enforces RLS under standard app credentials)
engine: AsyncEngine = create_async_engine(
    settings.DATABASE_URL,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_timeout=settings.DB_POOL_TIMEOUT,
    echo=settings.DB_ECHO,
    pool_pre_ping=True,
)

# Admin Database Engine (Used exclusively for system-level migrations and seeding)
admin_engine: AsyncEngine = create_async_engine(
    settings.DATABASE_ADMIN_URL,
    pool_size=5,
    max_overflow=5,
    pool_timeout=15,
    echo=settings.DB_ECHO,
    pool_pre_ping=True,
)

# Session factory for normal application queries
async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

# Session factory for system admin tasks
admin_session_factory = async_sessionmaker(
    bind=admin_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding an async database session.

    If an organization context is active, executes `SET LOCAL app.current_org_id`
    within the transaction to enforce PostgreSQL Row-Level Security.
    """
    async with async_session_factory() as session:
        org_id = get_current_tenant_id()
        if org_id:
            # Set the tenant context within the current local transaction
            await session.execute(
                text("SELECT set_config('app.current_org_id', :org_id, true)"),
                {"org_id": str(org_id)},
            )
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_admin_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding an administrative session bypassing RLS."""
    async with admin_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def check_database_health() -> bool:
    """Verifies database connectivity with a lightweight ping."""
    try:
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT 1"))
            return result.scalar() == 1
    except Exception:
        return False
