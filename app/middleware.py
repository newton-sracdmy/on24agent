"""FastAPI middlewares for correlation tracking, multi-tenant resolution, and error handling.

Ensures every incoming HTTP request receives a unique X-Request-ID and tracks latency.
"""

import time
import uuid
from typing import Callable
from uuid import UUID

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.common.schemas import APIResponse
from app.database import set_current_tenant_id
from app.exceptions import GabsterException


class RequestCorrelationMiddleware(BaseHTTPMiddleware):
    """Assigns or propagates X-Request-ID and measures total request execution time."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Extract or generate correlation ID
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id

        # Record start timestamp
        start_time = time.perf_counter()

        response = await call_next(request)

        # Calculate latency in milliseconds
        process_time_ms = round((time.perf_counter() - start_time) * 1000, 2)

        # Attach standard observability headers
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time-MS"] = str(process_time_ms)
        return response


class TenantContextMiddleware(BaseHTTPMiddleware):
    """Extracts tenant organization ID from header or request state and populates contextvar."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        org_id_str = request.headers.get("X-Organization-ID")
        if org_id_str:
            try:
                org_uuid = UUID(org_id_str)
                set_current_tenant_id(org_uuid)
                request.state.organization_id = org_uuid
            except ValueError:
                set_current_tenant_id(None)
                request.state.organization_id = None
        else:
            set_current_tenant_id(None)
            request.state.organization_id = None

        try:
            return await call_next(request)
        finally:
            # Always reset tenant context after request execution finishes
            set_current_tenant_id(None)


class GlobalExceptionMiddleware(BaseHTTPMiddleware):
    """Catches unhandled exceptions and formats standard APIResponse.fail JSON."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        try:
            return await call_next(request)
        except GabsterException as exc:
            request_id = getattr(request.state, "request_id", None)
            payload = APIResponse.fail(
                code=exc.code,
                message=exc.message,
                details=exc.details,
                request_id=request_id,
            ).model_dump(by_alias=True)
            return JSONResponse(status_code=exc.status_code, content=payload)
        except Exception as exc:
            request_id = getattr(request.state, "request_id", None)
            payload = APIResponse.fail(
                code="INTERNAL_SERVER_ERROR",
                message="An unexpected internal server error occurred",
                details={"error": str(exc)} if request.app.debug else None,
                request_id=request_id,
            ).model_dump(by_alias=True)
            return JSONResponse(status_code=500, content=payload)
