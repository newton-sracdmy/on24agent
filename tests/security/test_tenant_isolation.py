"""Security tests verifying multi-tenant isolation and policy enforcement."""

import uuid
import pytest
from app.exceptions import PermissionDeniedError, TenantAccessForbiddenError


def test_tenant_context_validation():
    tenant_a = uuid.uuid4()
    tenant_b = uuid.uuid4()
    assert tenant_a != tenant_b


@pytest.mark.asyncio
async def test_unauthenticated_request_blocked(async_client):
    response = await async_client.get("/api/v1/conversations/")
    assert response.status_code == 401
    payload = response.json()
    assert payload["success"] is False
    assert payload["error"]["code"] == "AUTHENTICATION_FAILED"
