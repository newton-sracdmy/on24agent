"""Pagination utilities for offset-based and cursor-based queries.

Cursor pagination uses a base64-encoded tuple of (created_at_iso, record_uuid)
to guarantee stable deterministic sorting across high-velocity message streams.
"""

import base64
import json
from datetime import datetime, timezone
from typing import Any, Generic, List, Optional, Sequence, Tuple, TypeVar
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.schemas import CursorPaginationMeta, PaginationMeta

T = TypeVar("T")


class PaginationParams(BaseModel):
    """Query parameters for offset-based pagination."""

    page: int = Field(default=1, ge=1, description="Page number")
    page_size: int = Field(default=20, ge=1, le=100, description="Items per page")

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


class CursorParams(BaseModel):
    """Query parameters for cursor-based pagination."""

    cursor: Optional[str] = Field(default=None, description="Opaque pagination token")
    limit: int = Field(default=30, ge=1, le=100, description="Items to fetch")


def encode_cursor(timestamp: datetime, record_id: UUID) -> str:
    """Encodes a timestamp and record ID into an opaque base64 cursor token."""
    payload = {
        "ts": timestamp.isoformat(),
        "id": str(record_id),
    }
    raw_json = json.dumps(payload).encode("utf-8")
    return base64.urlsafe_b64encode(raw_json).decode("utf-8")


def decode_cursor(cursor_str: str) -> Tuple[datetime, UUID]:
    """Decodes a base64 cursor token back into (timestamp, UUID)."""
    raw_bytes = base64.urlsafe_b64decode(cursor_str.encode("utf-8"))
    payload = json.loads(raw_bytes.decode("utf-8"))
    dt = datetime.fromisoformat(payload["ts"])
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt, UUID(payload["id"])


async def paginate_query(
    session: AsyncSession,
    query: Select,
    params: PaginationParams,
) -> Tuple[Sequence[Any], PaginationMeta]:
    """Executes a query with count and offset pagination."""
    # Count total matching rows
    count_query = select(func.count()).select_from(query.subquery())
    total_count_result = await session.execute(count_query)
    total_count = total_count_result.scalar() or 0

    # Apply limit and offset
    paginated_query = query.limit(params.page_size).offset(params.offset)
    result = await session.execute(paginated_query)
    items = result.scalars().all()

    total_pages = (total_count + params.page_size - 1) // params.page_size if total_count > 0 else 0
    has_next = params.page < total_pages
    has_previous = params.page > 1

    meta = PaginationMeta(
        total_count=total_count,
        page=params.page,
        page_size=params.page_size,
        total_pages=total_pages,
        has_next=has_next,
        has_previous=has_previous,
    )
    return items, meta
