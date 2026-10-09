"""API v1 master router aggregating all domain endpoints."""

from fastapi import APIRouter

from app.domains.agents.routes import router as agents_router
from app.domains.campaigns.routes import router as campaigns_router
from app.domains.contacts.routes import router as contacts_router
from app.domains.conversations.routes import router as conversations_router
from app.domains.identity.routes import router as identity_router
from app.domains.rag.routes import router as rag_router
from app.domains.usage.routes import router as usage_router

api_v1_router = APIRouter()

# Register core domain sub-routers
api_v1_router.include_router(identity_router, prefix="/auth", tags=["Identity & Auth"])
api_v1_router.include_router(contacts_router, prefix="/contacts", tags=["CRM Contacts"])
api_v1_router.include_router(conversations_router, prefix="/conversations", tags=["Unified Inbox & Messaging"])
api_v1_router.include_router(agents_router, prefix="/agents", tags=["AI Agents"])
api_v1_router.include_router(rag_router, prefix="/knowledge-bases", tags=["RAG & Knowledge Bases"])
api_v1_router.include_router(rag_router, prefix="/rag", tags=["RAG & Knowledge Bases"])
api_v1_router.include_router(campaigns_router, prefix="/campaigns", tags=["WhatsApp Campaigns & Broadcasts"])
api_v1_router.include_router(usage_router, prefix="/credits", tags=["Credits & Billing"])
