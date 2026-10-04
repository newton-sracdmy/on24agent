"""Common Pydantic v2 schemas and standard response envelopes.

All API responses follow a predictable JSON contract:
{
    "success": true,
    "data": { ... },
    "meta": { ... },
    "error": null
}
"""

from datetime import datetime
from typing import Any, Dict, Generic, List, Optional, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class BaseSchema(BaseModel):
    """Base schema enforcing standard configuration for all Pydantic models."""

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        use_enum_values=True,
        validate_assignment=True,
        arbitrary_types_allowed=True,
    )


class ErrorDetail(BaseSchema):
    """Standardized error structure in API responses."""

    code: str = Field(..., description="Machine-readable error code")
    message: str = Field(..., description="Human-readable error description")
    details: Optional[Dict[str, Any]] = Field(
        default=None, description="Granular context or field validation errors"
    )
    request_id: Optional[str] = Field(
        default=None, description="Correlation ID for tracing"
    )


class PaginationMeta(BaseSchema):
    """Metadata for offset-paginated collections."""

    total_count: int = Field(..., description="Total records matching criteria")
    page: int = Field(..., ge=1, description="Current page number")
    page_size: int = Field(..., ge=1, description="Number of items per page")
    total_pages: int = Field(..., ge=0, description="Total pages available")
    has_next: bool = Field(..., description="Whether a next page exists")
    has_previous: bool = Field(..., description="Whether a previous page exists")


class CursorPaginationMeta(BaseSchema):
    """Metadata for cursor-paginated collections (high-throughput feeds)."""

    has_more: bool = Field(..., description="Whether more items exist in current direction")
    next_cursor: Optional[str] = Field(
        default=None, description="Opaque cursor token for next page"
    )
    prev_cursor: Optional[str] = Field(
        default=None, description="Opaque cursor token for previous page"
    )
    count: int = Field(..., description="Number of items in current slice")


class APIResponse(BaseSchema, Generic[T]):
    """Universal API response envelope."""

    success: bool = Field(default=True, description="Indicates request outcome")
    data: Optional[T] = Field(default=None, description="Payload data")
    meta: Optional[Dict[str, Any]] = Field(
        default=None, description="Contextual metadata (e.g. pagination, execution timing)"
    )
    error: Optional[ErrorDetail] = Field(
        default=None, description="Error details when success is false"
    )

    @classmethod
    def ok(cls, data: T, meta: Optional[Dict[str, Any]] = None) -> "APIResponse[T]":
        return cls(success=True, data=data, meta=meta, error=None)

    @classmethod
    def fail(
        cls,
        code: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        request_id: Optional[str] = None,
        meta: Optional[Dict[str, Any]] = None,
    ) -> "APIResponse[None]":
        return cls(
            success=False,
            data=None,
            meta=meta,
            error=ErrorDetail(
                code=code,
                message=message,
                details=details,
                request_id=request_id,
            ),
        )


class PaginatedResponse(BaseSchema, Generic[T]):
    """Standard response envelope for offset-paginated lists."""

    items: List[T]
    pagination: PaginationMeta


class CursorPaginatedResponse(BaseSchema, Generic[T]):
    """Standard response envelope for cursor-paginated lists."""

    items: List[T]
    pagination: CursorPaginationMeta
