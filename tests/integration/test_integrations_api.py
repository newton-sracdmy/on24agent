"""API tests for Integrations & Connected Applications against a real PostgreSQL database.

Run against a disposable, fully migrated database (never a real one):

    INTEGRATION_TEST_DB=1 \
    DATABASE_URL=postgresql+asyncpg://<app_role>:<pw>@localhost:5433/gabster_test \
    DATABASE_ADMIN_URL=postgresql+asyncpg://postgres:<pw>@localhost:5433/gabster_test \
    pytest tests/integration/test_integrations_api.py

Use a non-superuser role for DATABASE_URL so Row-Level Security is enforced as in production.
"""

import asyncio
import json
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.database import admin_session_factory
from app.main import app
from app.security import create_access_token, decrypt_secret

pytestmark = [
    pytest.mark.skipif(
        not os.getenv("INTEGRATION_TEST_DB"), reason="needs a disposable migrated database (INTEGRATION_TEST_DB=1)"
    ),
    pytest.mark.asyncio(loop_scope="module"),
]

BASE = "/api/v1/integrations"


async def _create_workspace(role: str = "owner") -> dict:
    """Insert an organization with one member of the given role and return auth headers for them."""
    org_id, user_id, role_id, session_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    suffix = uuid.uuid4().hex[:8]
    async with admin_session_factory() as s:
        await s.execute(
            text("INSERT INTO organizations (id, name, slug) VALUES (:id, :name, :slug)"),
            {"id": org_id, "name": f"Test Org {suffix}", "slug": f"test-org-{suffix}"},
        )
        await s.execute(
            text(
                "INSERT INTO users (id, email, password_hash, full_name) VALUES (:id, :email, 'x', 'Test User')"
            ),
            {"id": user_id, "email": f"user-{suffix}@example.com"},
        )
        await s.execute(
            text("INSERT INTO roles (id, organization_id, name, slug) VALUES (:id, :org, :name, :name)"),
            {"id": role_id, "org": org_id, "name": role},
        )
        await s.execute(
            text(
                "INSERT INTO memberships (id, organization_id, user_id, role_id, role) "
                "VALUES (gen_random_uuid(), :org, :user, :role_id, :role)"
            ),
            {"org": org_id, "user": user_id, "role_id": role_id, "role": role},
        )
        await s.execute(
            text(
                "INSERT INTO sessions (id, user_id, organization_id, expires_at) VALUES (:id, :user, :org, :exp)"
            ),
            {"id": session_id, "user": user_id, "org": org_id, "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
        )
        await s.commit()
    token = create_access_token(user_id, f"user-{suffix}@example.com", session_id, organization_id=org_id)
    return {"org_id": org_id, "headers": {"Authorization": f"Bearer {token}", "X-Organization-ID": str(org_id)}}


async def _channel_rows(org_id: uuid.UUID, identifier: str) -> list:
    async with admin_session_factory() as s:
        res = await s.execute(
            text(
                "SELECT account_identifier, encrypted_credentials, is_deleted, deleted_at, status "
                "FROM channel_accounts WHERE organization_id = :org AND account_identifier = :ident"
            ),
            {"org": org_id, "ident": identifier},
        )
        return list(res.mappings().all())


def _whatsapp(identifier: str) -> dict:
    return {"app_slug": "whatsapp", "api_key_or_token": "EAAG-test-token", "endpoint_or_secret": identifier}


@pytest_asyncio.fixture(loop_scope="module")
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def test_list_returns_full_catalog_for_new_workspace(client):
    ws = await _create_workspace()
    r = await client.get(f"{BASE}/", headers=ws["headers"])
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["total_count"] == 13
    assert data["connected_count"] == 0
    assert data["category_counts"]["messaging"] == 6
    assert not any(i["is_connected"] for i in data["integrations"])


async def test_connect_channel_stores_encrypted_canonical_credentials(client):
    ws = await _create_workspace()
    ident = f"pn-{uuid.uuid4().hex[:10]}"
    r = await client.post(f"{BASE}/connect", json=_whatsapp(f"  {ident}  "), headers=ws["headers"])
    assert r.status_code == 200, r.text

    rows = await _channel_rows(ws["org_id"], ident)
    assert len(rows) == 1, "identifier should be stored trimmed"
    creds = json.loads(decrypt_secret(rows[0]["encrypted_credentials"]))
    assert creds["access_token"] == "EAAG-test-token"
    assert creds["phone_number_id"] == ident

    listed = (await client.get(f"{BASE}/", headers=ws["headers"])).json()["data"]
    wa = next(i for i in listed["integrations"] if i["slug"] == "whatsapp")
    assert wa["is_connected"] and wa["account_identifier"] == ident


async def test_connect_saas_with_null_additional_config(client):
    ws = await _create_workspace()
    payload = {
        "app_slug": "shopify",
        "api_key_or_token": "shpat_x",
        "endpoint_or_secret": "store.myshopify.com",
        "additional_config": None,
    }
    r = await client.post(f"{BASE}/connect", json=payload, headers=ws["headers"])
    assert r.status_code == 200, r.text


async def test_additional_config_cannot_override_identifier_or_credentials(client):
    ws = await _create_workspace()
    payload = {
        "app_slug": "shopify",
        "api_key_or_token": "shpat_real",
        "endpoint_or_secret": "real.myshopify.com",
        "additional_config": {"identifier": "spoofed", "api_key_or_token": "spoofed"},
    }
    assert (await client.post(f"{BASE}/connect", json=payload, headers=ws["headers"])).status_code == 200
    async with admin_session_factory() as s:
        row = (
            await s.execute(
                text("SELECT config_json, encrypted_credentials FROM integrations WHERE organization_id = :org"),
                {"org": ws["org_id"]},
            )
        ).mappings().one()
    assert row["config_json"]["identifier"] == "real.myshopify.com"
    assert json.loads(decrypt_secret(row["encrypted_credentials"]))["api_key_or_token"] == "shpat_real"


async def test_overlong_account_name_is_rejected_not_500(client):
    ws = await _create_workspace()
    payload = {"app_slug": "shopify", "api_key_or_token": "shpat_x", "account_name": "x" * 101}
    r = await client.post(f"{BASE}/connect", json=payload, headers=ws["headers"])
    assert r.status_code == 422, r.text


async def test_unknown_app_slug_is_rejected(client):
    ws = await _create_workspace()
    r = await client.post(
        f"{BASE}/connect", json={"app_slug": "nope", "api_key_or_token": "x"}, headers=ws["headers"]
    )
    assert r.status_code == 400
    assert (await client.post(f"{BASE}/nope/disconnect", headers=ws["headers"])).status_code == 400


@pytest.mark.parametrize("role", ["agent", "supervisor", "viewer"])
async def test_non_admin_members_cannot_change_integrations(client, role):
    ws = await _create_workspace(role=role)
    assert (await client.get(f"{BASE}/", headers=ws["headers"])).status_code == 200
    r = await client.post(f"{BASE}/connect", json=_whatsapp(f"pn-{uuid.uuid4().hex[:10]}"), headers=ws["headers"])
    assert r.status_code == 403
    assert (await client.post(f"{BASE}/whatsapp/disconnect", headers=ws["headers"])).status_code == 403


async def test_admin_member_can_connect(client):
    ws = await _create_workspace(role="admin")
    r = await client.post(f"{BASE}/connect", json=_whatsapp(f"pn-{uuid.uuid4().hex[:10]}"), headers=ws["headers"])
    assert r.status_code == 200, r.text


async def test_same_channel_account_cannot_join_second_workspace(client):
    a, b = await _create_workspace(), await _create_workspace()
    ident = f"pn-{uuid.uuid4().hex[:10]}"
    assert (await client.post(f"{BASE}/connect", json=_whatsapp(ident), headers=a["headers"])).status_code == 200

    r = await client.post(f"{BASE}/connect", json=_whatsapp(ident), headers=b["headers"])
    assert r.status_code == 409, r.text
    assert r.json()["error"]["code"] == "RESOURCE_CONFLICT"
    assert await _channel_rows(b["org_id"], ident) == []


async def test_concurrent_connects_of_same_account_admit_only_one_workspace(client):
    a, b = await _create_workspace(), await _create_workspace()
    ident = f"pn-{uuid.uuid4().hex[:10]}"
    ra, rb = await asyncio.gather(
        client.post(f"{BASE}/connect", json=_whatsapp(ident), headers=a["headers"]),
        client.post(f"{BASE}/connect", json=_whatsapp(ident), headers=b["headers"]),
    )
    assert sorted([ra.status_code, rb.status_code]) == [200, 409], (ra.text, rb.text)
    active = [r for org in (a, b) for r in await _channel_rows(org["org_id"], ident) if not r["is_deleted"]]
    assert len(active) == 1


async def test_disconnect_releases_account_for_another_workspace(client):
    a, b = await _create_workspace(), await _create_workspace()
    ident = f"pn-{uuid.uuid4().hex[:10]}"
    await client.post(f"{BASE}/connect", json=_whatsapp(ident), headers=a["headers"])

    r = await client.post(f"{BASE}/whatsapp/disconnect", headers=a["headers"])
    assert r.status_code == 200, r.text
    [row] = await _channel_rows(a["org_id"], ident)
    assert row["is_deleted"] and row["status"] == "disconnected" and row["deleted_at"] is not None

    assert (await client.post(f"{BASE}/connect", json=_whatsapp(ident), headers=b["headers"])).status_code == 200


async def test_reconnect_in_same_workspace_updates_existing_account(client):
    ws = await _create_workspace()
    ident = f"pn-{uuid.uuid4().hex[:10]}"
    for _ in range(2):
        r = await client.post(f"{BASE}/connect", json=_whatsapp(ident), headers=ws["headers"])
        assert r.status_code == 200, r.text
    assert len(await _channel_rows(ws["org_id"], ident)) == 1


async def test_placeholder_identifiers_do_not_collide_across_workspaces(client):
    a, b = await _create_workspace(), await _create_workspace()
    payload = {"app_slug": "telegram", "api_key_or_token": "123:abc"}
    assert (await client.post(f"{BASE}/connect", json=payload, headers=a["headers"])).status_code == 200
    assert (await client.post(f"{BASE}/connect", json=payload, headers=b["headers"])).status_code == 200
