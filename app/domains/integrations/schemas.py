"""Pydantic schemas for Integrations & Connected Applications domain."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID
from pydantic import BaseModel, Field


class IntegrationItem(BaseModel):
    """Catalog and active state representation for an integration."""
    slug: str = Field(..., description="Unique slug for the integration (e.g. whatsapp, messenger, shopify)")
    name: str = Field(..., description="Display name of the application")
    category: str = Field(..., description="Category: messaging, calendar, meeting, ecommerce, productivity")
    category_label: str = Field(..., description="User-friendly category title")
    description: str = Field(..., description="Brief summary of integration capabilities")
    icon: str = Field(..., description="Lucide icon identifier or logo indicator")
    badge_label: str = Field("third-party", description="Tag/badge indicator")
    is_channel: bool = Field(False, description="True if this is a communication channel stored in channel_accounts")
    is_connected: bool = Field(False, description="Whether currently connected for the organization")
    account_identifier: Optional[str] = Field(None, description="Masked or displayed identifier (e.g. Phone number, Page ID, Store domain)")
    updated_at: Optional[datetime] = None


class IntegrationListResponse(BaseModel):
    """Response containing catalog items, active connections, and category counts."""
    integrations: List[IntegrationItem]
    total_count: int
    category_counts: Dict[str, int]
    connected_count: int


class ConnectIntegrationRequest(BaseModel):
    """Payload to connect or update an integration."""
    app_slug: str = Field(..., description="App slug to connect (e.g. messenger, whatsapp, shopify)")
    api_key_or_token: str = Field(..., min_length=1, description="Primary API key, access token, or bot token")
    endpoint_or_secret: Optional[str] = Field(None, description="Webhook secret, Page ID, Store domain, or Phone Number ID")
    account_name: Optional[str] = Field(None, description="Optional custom label for the connected account")
    additional_config: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Additional metadata")


class ConnectIntegrationResponse(BaseModel):
    """Response returned upon connecting an application."""
    success: bool
    app_slug: str
    name: str
    status: str
    message: str
    connected_at: datetime


class DisconnectIntegrationRequest(BaseModel):
    """Request payload to disconnect an application."""
    app_slug: str


class RequestIntegrationSubmission(BaseModel):
    """Request payload when user requests a new integration not currently supported."""
    name: str = Field(..., min_length=2)
    category: str
    use_case: Optional[str] = None
    contact_email: Optional[str] = None
