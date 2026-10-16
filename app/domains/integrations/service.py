"""Business logic service for Integrations & Connected Applications."""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.integrations.schemas import (
    ConnectIntegrationRequest,
    ConnectIntegrationResponse,
    IntegrationItem,
    IntegrationListResponse,
)
from app.exceptions import ResourceConflictError
from app.security import decrypt_secret, encrypt_secret

logger = logging.getLogger("integrations_service")

# Master Catalog of 13 supported integrations across 5 key categories
CATALOG_INTEGRATIONS: List[Dict[str, Any]] = [
    # 1. Messaging & Channels (6)
    {
        "slug": "whatsapp",
        "name": "WhatsApp Business Cloud",
        "category": "messaging",
        "category_label": "Messaging & Channels",
        "description": "Official Meta Cloud API for customer conversations and WhatsApp template broadcasts.",
        "icon": "message-circle",
        "badge_label": "messaging",
        "is_channel": True,
        "channel_type": "whatsapp",
        "primary_label": "Meta System User / Permanent Token",
        "secondary_label": "Phone Number ID",
        "secondary_placeholder": "e.g. 1402413542949034",
    },
    {
        "slug": "messenger",
        "name": "Facebook Messenger",
        "category": "messaging",
        "category_label": "Messaging & Channels",
        "description": "Page inbox synchronization and automatic lead conversion bot.",
        "icon": "facebook",
        "badge_label": "messaging",
        "is_channel": True,
        "channel_type": "messenger",
        "primary_label": "Page Access Token",
        "secondary_label": "Facebook Page ID",
        "secondary_placeholder": "e.g. 1463059650215713",
    },
    {
        "slug": "instagram",
        "name": "Instagram Direct",
        "category": "messaging",
        "category_label": "Messaging & Channels",
        "description": "Direct messaging API for Instagram Business & Creator accounts.",
        "icon": "instagram",
        "badge_label": "messaging",
        "is_channel": True,
        "channel_type": "instagram",
        "primary_label": "Instagram Access Token (User / Page)",
        "secondary_label": "Instagram Account ID / Username",
        "secondary_placeholder": "e.g. 29004906199152162",
    },
    {
        "slug": "telegram",
        "name": "Telegram Bot",
        "category": "messaging",
        "category_label": "Messaging & Channels",
        "description": "Instantaneous customer support and group broadcasts via Telegram Bot API.",
        "icon": "send",
        "badge_label": "messaging",
        "is_channel": True,
        "channel_type": "telegram",
        "primary_label": "Bot API Token",
        "secondary_label": "Bot Username",
        "secondary_placeholder": "e.g. @MySupportBot",
    },
    {
        "slug": "webchat",
        "name": "Live Web Widget",
        "category": "messaging",
        "category_label": "Messaging & Channels",
        "description": "Embeddable website chat widget with real-time WebSocket support.",
        "icon": "globe",
        "badge_label": "messaging",
        "is_channel": True,
        "channel_type": "webchat",
        "primary_label": "Public Widget Secret Key",
        "secondary_label": "Allowed Domain(s)",
        "secondary_placeholder": "e.g. https://example.com",
    },
    {
        "slug": "twilio",
        "name": "Twilio SMS",
        "category": "messaging",
        "category_label": "Messaging & Channels",
        "description": "Global SMS messaging channel for two-way customer conversations and SMS notifications.",
        "icon": "smartphone",
        "badge_label": "messaging",
        "is_channel": True,
        "channel_type": "voice",  # Or twilio channel
        "primary_label": "Twilio Auth Token",
        "secondary_label": "Account SID & Sender Phone Number",
        "secondary_placeholder": "e.g. AC... / +15551234567",
    },

    # 2. Calendars (3)
    {
        "slug": "google_calendar",
        "name": "Google Calendar",
        "category": "calendar",
        "category_label": "Calendars",
        "description": "Real-time meeting scheduling and calendar availability lookup for AI agents.",
        "icon": "calendar",
        "badge_label": "calendar",
        "is_channel": False,
        "primary_label": "OAuth Client Secret / Service Account JSON",
        "secondary_label": "Calendar ID",
        "secondary_placeholder": "e.g. primary or info@example.com",
    },
    {
        "slug": "cal_com",
        "name": "Cal.com",
        "category": "calendar",
        "category_label": "Calendars",
        "description": "Open-source scheduling platform integration with automatic booking links.",
        "icon": "calendar-days",
        "badge_label": "calendar",
        "is_channel": False,
        "primary_label": "Cal.com API Key",
        "secondary_label": "Event Type Slug / Username",
        "secondary_placeholder": "e.g. team/consultation",
    },
    {
        "slug": "calendly",
        "name": "Calendly",
        "category": "calendar",
        "category_label": "Calendars",
        "description": "Automated appointment scheduling and customer booking routing.",
        "icon": "clock",
        "badge_label": "calendar",
        "is_channel": False,
        "primary_label": "Personal Access Token",
        "secondary_label": "Organization URI / Event Slug",
        "secondary_placeholder": "e.g. https://calendly.com/user/event",
    },

    # 3. Meetings & Video (1)
    {
        "slug": "zoom",
        "name": "Zoom Meetings",
        "category": "meeting",
        "category_label": "Meetings & Video",
        "description": "Auto-generate video conference links and sync customer meeting appointments.",
        "icon": "video",
        "badge_label": "meeting",
        "is_channel": False,
        "primary_label": "Server-to-Server OAuth Client Secret",
        "secondary_label": "Account ID & Client ID",
        "secondary_placeholder": "e.g. acc_123 / cli_456",
    },

    # 4. E-Commerce Stores (2)
    {
        "slug": "shopify",
        "name": "Shopify",
        "category": "ecommerce",
        "category_label": "E-Commerce Stores",
        "description": "Store catalog sync, order tracking, and cart status retrieval for autonomous AI.",
        "icon": "shopping-bag",
        "badge_label": "ecommerce",
        "is_channel": False,
        "primary_label": "Admin API Access Token (shpat_...)",
        "secondary_label": "Store Domain (.myshopify.com)",
        "secondary_placeholder": "e.g. my-store.myshopify.com",
    },
    {
        "slug": "woocommerce",
        "name": "WooCommerce",
        "category": "ecommerce",
        "category_label": "E-Commerce Stores",
        "description": "WordPress e-commerce store connector for orders, products, and inventory lookup.",
        "icon": "store",
        "badge_label": "ecommerce",
        "is_channel": False,
        "primary_label": "Consumer Secret (cs_...)",
        "secondary_label": "Store URL & Consumer Key (ck_...)",
        "secondary_placeholder": "e.g. https://shop.com / ck_...",
    },

    # 5. Productivity & CRM (1)
    {
        "slug": "google_sheets",
        "name": "Google Sheets",
        "category": "productivity",
        "category_label": "Productivity",
        "description": "Automatic lead synchronization and spreadsheet logging from AI conversations.",
        "icon": "file-spreadsheet",
        "badge_label": "productivity",
        "is_channel": False,
        "primary_label": "Google Service Account Private Key JSON",
        "secondary_label": "Target Spreadsheet ID",
        "secondary_placeholder": "e.g. 1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms",
    },
]


class IntegrationsService:
    """Service handling catalog listing, credential encryption, and app connection states."""

    @staticmethod
    async def list_integrations(session: AsyncSession, org_id: UUID) -> IntegrationListResponse:
        """Merge master catalog with tenant's active database connections."""
        # 1. Fetch connected messaging channel accounts for this tenant
        q_channels = await session.execute(
            text(
                """
                SELECT ch.type, ca.id, ca.name, ca.account_identifier, ca.status, ca.updated_at
                FROM channel_accounts ca
                JOIN channels ch ON ch.id = ca.channel_id
                WHERE ca.organization_id = :org_id AND ca.is_deleted = false AND ca.status = 'connected';
                """
            ),
            {"org_id": org_id},
        )
        active_channels_map = {}
        for row in q_channels.mappings().all():
            ch_type = row["type"]
            # Map channel type to slug
            slug_key = ch_type
            if ch_type == "messenger":
                slug_key = "messenger"
            elif ch_type == "voice":
                slug_key = "twilio"
            active_channels_map[slug_key] = row

        # 2. Fetch connected SaaS integrations from integrations table
        q_integrations = await session.execute(
            text(
                """
                SELECT app_slug, name, status, config_json, updated_at
                FROM integrations
                WHERE organization_id = :org_id AND status = 'connected';
                """
            ),
            {"org_id": org_id},
        )
        active_integrations_map = {row["app_slug"]: row for row in q_integrations.mappings().all()}

        # 3. Construct response items
        items: List[IntegrationItem] = []
        category_counts: Dict[str, int] = {
            "all": len(CATALOG_INTEGRATIONS),
            "messaging": 0,
            "calendar": 0,
            "meeting": 0,
            "ecommerce": 0,
            "productivity": 0,
        }
        connected_count = 0

        for cat_item in CATALOG_INTEGRATIONS:
            slug = cat_item["slug"]
            category = cat_item["category"]
            category_counts[category] = category_counts.get(category, 0) + 1

            is_connected = False
            identifier = None
            updated_at = None

            if cat_item["is_channel"]:
                if slug in active_channels_map:
                    ch_info = active_channels_map[slug]
                    is_connected = True
                    identifier = ch_info.get("account_identifier")
                    updated_at = ch_info.get("updated_at")
            else:
                if slug in active_integrations_map:
                    ig_info = active_integrations_map[slug]
                    is_connected = True
                    conf = ig_info.get("config_json") or {}
                    identifier = conf.get("identifier") or conf.get("domain") or ig_info.get("name")
                    updated_at = ig_info.get("updated_at")

            if is_connected:
                connected_count += 1

            items.append(
                IntegrationItem(
                    slug=slug,
                    name=cat_item["name"],
                    category=category,
                    category_label=cat_item["category_label"],
                    description=cat_item["description"],
                    icon=cat_item["icon"],
                    badge_label=cat_item["badge_label"],
                    is_channel=cat_item["is_channel"],
                    is_connected=is_connected,
                    account_identifier=identifier,
                    updated_at=updated_at,
                )
            )

        return IntegrationListResponse(
            integrations=items,
            total_count=len(items),
            category_counts=category_counts,
            connected_count=connected_count,
        )

    @staticmethod
    async def connect_integration(
        session: AsyncSession, org_id: UUID, data: ConnectIntegrationRequest
    ) -> ConnectIntegrationResponse:
        """Validate, encrypt, and store credentials for a channel or SaaS integration."""
        slug = data.app_slug.lower().strip()
        catalog_entry = next((item for item in CATALOG_INTEGRATIONS if item["slug"] == slug), None)
        if not catalog_entry:
            raise ValueError(f"Unknown integration app: '{data.app_slug}'")

        now = datetime.utcnow()
        display_name = data.account_name or catalog_entry["name"]
        identifier = data.endpoint_or_secret or f"{slug}_default"

        # Encrypt the credentials payload securely
        creds_payload = {
            "api_key_or_token": data.api_key_or_token,
            "endpoint_or_secret": data.endpoint_or_secret,
            "connected_at": now.isoformat(),
            **data.additional_config,
        }
        # Channel services read these canonical keys, not the generic form fields
        if slug == "whatsapp":
            creds_payload.update(access_token=data.api_key_or_token, phone_number_id=data.endpoint_or_secret)
        elif slug == "messenger":
            creds_payload.update(page_access_token=data.api_key_or_token, page_id=data.endpoint_or_secret)
        elif slug == "instagram":
            creds_payload.update(access_token=data.api_key_or_token, instagram_account_id=data.endpoint_or_secret)
        encrypted_blob = encrypt_secret(json.dumps(creds_payload))

        if catalog_entry["is_channel"]:
            channel_type = catalog_entry.get("channel_type", slug)
            # Find the channel ID from channels table
            q_ch = await session.execute(
                text("SELECT id FROM channels WHERE type = :type LIMIT 1;"),
                {"type": channel_type},
            )
            ch_row = q_ch.mappings().first()
            if not ch_row:
                # If channel type doesn't exist, register it
                q_ins = await session.execute(
                    text(
                        """
                        INSERT INTO channels (id, type, name, description, is_active, created_at, updated_at)
                        VALUES (gen_random_uuid(), :type, :name, :desc, true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                        RETURNING id;
                        """
                    ),
                    {"type": channel_type, "name": catalog_entry["name"], "desc": catalog_entry["description"]},
                )
                channel_id = q_ins.scalar_one()
            else:
                channel_id = ch_row["id"]

            # Inbound webhooks are routed by identifier, so one number/page/account can belong to one workspace
            if identifier != f"{slug}_default":
                q_taken = await session.execute(
                    text(
                        """
                        SELECT 1 FROM channel_accounts
                        WHERE channel_id = :channel_id AND account_identifier = :identifier
                          AND organization_id <> :org_id AND is_deleted = false
                        LIMIT 1;
                        """
                    ),
                    {"org_id": org_id, "channel_id": channel_id, "identifier": identifier},
                )
                if q_taken.first():
                    raise ResourceConflictError(
                        f"This {catalog_entry['name']} account is already connected to another workspace. "
                        "Disconnect it there first."
                    )

            # Upsert into channel_accounts for this organization
            # 1. First check if an account with the exact same identifier already exists (regardless of is_deleted)
            q_existing = await session.execute(
                text(
                    """
                    SELECT id FROM channel_accounts
                    WHERE organization_id = :org_id AND channel_id = :channel_id AND account_identifier = :identifier
                    LIMIT 1;
                    """
                ),
                {"org_id": org_id, "channel_id": channel_id, "identifier": identifier},
            )
            existing_ca = q_existing.mappings().first()

            if not existing_ca:
                # 2. Check if any account exists for this channel in this org
                q_existing_ch = await session.execute(
                    text(
                        """
                        SELECT id FROM channel_accounts
                        WHERE organization_id = :org_id AND channel_id = :channel_id
                        ORDER BY is_deleted ASC, created_at DESC
                        LIMIT 1;
                        """
                    ),
                    {"org_id": org_id, "channel_id": channel_id},
                )
                existing_ca = q_existing_ch.mappings().first()

            if existing_ca:
                await session.execute(
                    text(
                        """
                        UPDATE channel_accounts
                        SET name = :name,
                            account_identifier = :identifier,
                            encrypted_credentials = :enc,
                            settings = CAST(:settings AS jsonb),
                            status = 'connected',
                            is_deleted = false,
                            deleted_at = NULL,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = :id;
                        """
                    ),
                    {
                        "id": existing_ca["id"],
                        "name": display_name,
                        "identifier": identifier,
                        "enc": encrypted_blob,
                        "settings": json.dumps({"app_slug": slug}),
                    },
                )
            else:
                await session.execute(
                    text(
                        """
                        INSERT INTO channel_accounts (
                            id, organization_id, channel_id, name, account_identifier,
                            status, encrypted_credentials, settings, is_deleted, created_at, updated_at
                        )
                        VALUES (
                            gen_random_uuid(), :org_id, :channel_id, :name, :identifier,
                            'connected', :enc, CAST(:settings AS jsonb), false, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                        )
                        ON CONFLICT (organization_id, channel_id, account_identifier)
                        DO UPDATE SET
                            name = EXCLUDED.name,
                            status = 'connected',
                            encrypted_credentials = EXCLUDED.encrypted_credentials,
                            settings = EXCLUDED.settings,
                            is_deleted = false,
                            deleted_at = NULL,
                            updated_at = CURRENT_TIMESTAMP;
                        """
                    ),
                    {
                        "org_id": org_id,
                        "channel_id": channel_id,
                        "name": display_name,
                        "identifier": identifier,
                        "enc": encrypted_blob,
                        "settings": json.dumps({"app_slug": slug}),
                    },
                )
        else:
            # Upsert into integrations table for SaaS tools
            config_json = {
                "identifier": identifier,
                "display_name": display_name,
                **data.additional_config,
            }
            await session.execute(
                text(
                    """
                    INSERT INTO integrations (
                        id, organization_id, app_slug, name, status, encrypted_credentials, config_json, created_at, updated_at
                    )
                    VALUES (
                        gen_random_uuid(), :org_id, :app_slug, :name, 'connected', :enc, CAST(:config AS jsonb), CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                    )
                    ON CONFLICT (organization_id, app_slug)
                    DO UPDATE SET
                        name = EXCLUDED.name,
                        status = 'connected',
                        encrypted_credentials = EXCLUDED.encrypted_credentials,
                        config_json = EXCLUDED.config_json,
                        updated_at = CURRENT_TIMESTAMP;
                    """
                ),
                {
                    "org_id": org_id,
                    "app_slug": slug,
                    "name": display_name,
                    "enc": encrypted_blob,
                    "config": json.dumps(config_json),
                },
            )

        await session.commit()
        logger.info(f"Successfully connected integration '{slug}' for organization {org_id}")

        return ConnectIntegrationResponse(
            success=True,
            app_slug=slug,
            name=catalog_entry["name"],
            status="connected",
            message=f"{catalog_entry['name']} was successfully connected and verified.",
            connected_at=now,
        )

    @staticmethod
    async def disconnect_integration(session: AsyncSession, org_id: UUID, app_slug: str) -> bool:
        """Disconnect an active channel or SaaS integration."""
        slug = app_slug.lower().strip()
        catalog_entry = next((item for item in CATALOG_INTEGRATIONS if item["slug"] == slug), None)
        if not catalog_entry:
            raise ValueError(f"Unknown integration app: '{app_slug}'")

        if catalog_entry["is_channel"]:
            channel_type = catalog_entry.get("channel_type", slug)
            await session.execute(
                text(
                    """
                    UPDATE channel_accounts ca
                    SET is_deleted = true, status = 'disconnected', updated_at = CURRENT_TIMESTAMP
                    FROM channels ch
                    WHERE ch.id = ca.channel_id
                      AND ch.type = :type
                      AND ca.organization_id = :org_id;
                    """
                ),
                {"type": channel_type, "org_id": org_id},
            )
        else:
            await session.execute(
                text(
                    """
                    UPDATE integrations
                    SET status = 'disconnected', updated_at = CURRENT_TIMESTAMP
                    WHERE organization_id = :org_id AND app_slug = :slug;
                    """
                ),
                {"slug": slug, "org_id": org_id},
            )

        await session.commit()
        logger.info(f"Successfully disconnected integration '{slug}' for organization {org_id}")
        return True
