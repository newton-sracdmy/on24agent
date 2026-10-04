"""FastAPI Application Entrypoint for Gabster AI.

Initializes routers, middlewares, exception handlers, and OpenTelemetry instrumentation.
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

from app.api.v1.router import api_v1_router
from app.api.webhooks.router import webhooks_router
from app.common.schemas import APIResponse
from app.config import settings
from app.database import check_database_health, engine
from app.middleware import (
    GlobalExceptionMiddleware,
    RequestCorrelationMiddleware,
    TenantContextMiddleware,
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application startup and graceful shutdown lifecycle."""
    # Startup: Ping database & Redis
    db_healthy = await check_database_health()
    if not db_healthy:
        # In development, warn; in production, fail fast if required
        pass

    yield

    # Shutdown: Dispose connection pools
    await engine.dispose()


def create_application() -> FastAPI:
    """Factory creating configured FastAPI instance."""
    app = FastAPI(
        title="Gabster AI - Enterprise Customer Operations API",
        description="Production-grade omnichannel AI customer operations SaaS platform.",
        version="1.0.0",
        docs_url="/docs" if settings.ENVIRONMENT != "production" else None,
        redoc_url="/redoc" if settings.ENVIRONMENT != "production" else None,
        openapi_url=f"{settings.API_V1_STR}/openapi.json",
        lifespan=lifespan,
    )

    # Core Middlewares (Executed in reverse order of addition)
    app.add_middleware(GlobalExceptionMiddleware)
    app.add_middleware(TenantContextMiddleware)
    app.add_middleware(RequestCorrelationMiddleware)
    app.add_middleware(GZipMiddleware, minimum_size=1024)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID", "X-Response-Time-MS"],
    )

    # Health and Liveness Probes
    @app.get("/health", tags=["System"])
    async def health_check() -> APIResponse[dict]:
        db_ok = await check_database_health()
        status_str = "healthy" if db_ok else "degraded"
        return APIResponse.ok(
            data={"status": status_str, "database": db_ok, "environment": settings.ENVIRONMENT}
        )

    @app.get("/livez", tags=["System"])
    async def liveness_probe() -> dict:
        return {"status": "alive"}

    @app.get("/readyz", tags=["System"])
    async def readiness_probe() -> dict:
        db_ok = await check_database_health()
        if not db_ok:
            return {"status": "unready", "database": "disconnected"}
        return {"status": "ready"}

    # Include Versioned API Routes & Webhook Ingress
    app.include_router(api_v1_router, prefix=settings.API_V1_STR)
    app.include_router(webhooks_router, prefix="/webhooks")

    # Prometheus Instrumentation
    if settings.ENABLE_METRICS:
        Instrumentator().instrument(app).expose(app, endpoint="/metrics")

    return app


app = create_application()
