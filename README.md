# Gabster AI — Enterprise AI Customer Operations Platform

An enterprise-grade, omnichannel AI customer operations SaaS platform inspired by Gabster AI. Built for high-volume customer communications, WhatsApp Business automation, voice agents, unified multi-channel inboxes, RAG knowledge retrieval, workflows, SLA tracking, and credits-based AI billing.

## 🚀 Key Architectural Pillars

- **Enterprise Multi-Tenancy**: Tenant isolation using PostgreSQL Row-Level Security (RLS) with session variable `SET LOCAL app.current_org_id`, composite foreign keys `(organization_id, id)`, and strict non-bypass application roles.
- **Unified Omnichannel Inbox**: Real-time conversation orchestration across WhatsApp Cloud API, Instagram, Telegram, Web Chat, Email, and Voice.
- **Time-Ordered Primary Keys**: UUIDv7 across all transactional tables for optimal B-tree index locality and chronological sorting.
- **RAG Architecture**: pgvector with HNSW index algorithms, semantic chunking, multi-stage hybrid search, and citation tracking.
- **State Machine Workflow Engine**: Immutable versioning of workflows, DAG node graph execution with compensation/rollback handlers, and transactional outbox.
- **Credit & Financial Operations**: Double-entry style credit ledger, tiered subscription plans, per-second voice billing, per-token LLM accounting, and automated WhatsApp 24-hour service window tracking.

## 🛠️ Technology Stack

- **Core Backend**: Python 3.12, FastAPI, Pydantic v2
- **Persistence**: PostgreSQL 16, pgvector extension, SQLAlchemy 2.0 (async), asyncpg, Alembic
- **Caching & Messaging**: Redis 7, Celery 5.4, Flower
- **Security**: JWT (RS256/HS256), Fernet symmetric encryption for sensitive secrets, bcrypt hashing
- **Observability**: Structlog structured JSON logging, OpenTelemetry tracing, Prometheus metrics
- **Deployment**: Docker multi-stage builds, Docker Compose, Kubernetes manifests, GitHub Actions CI/CD

## 📂 Project Structure

```text
project/
├── alembic/                 # Database migrations (28 ordered stages)
│   ├── env.py
│   └── versions/
├── app/
│   ├── api/                 # API routers, dependency injection, middleware
│   │   ├── v1/              # Versioned API endpoints
│   │   └── webhooks/        # Channel and external webhook ingress
│   ├── common/              # Shared base models, schemas, repositories, pagination
│   ├── domains/             # 16 domain modules (modular monolith architecture)
│   │   ├── identity/        # Users, Orgs, Memberships, RBAC, Sessions
│   │   ├── ai/              # Providers, Models, Configuration
│   │   ├── channels/        # Channel Accounts, Capabilities
│   │   ├── contacts/        # Contacts, Identities, CRM Fields, Events
│   │   ├── conversations/   # Unified Inbox, Messages, SLAs, Routing, CSAT
│   │   ├── agents/          # AI Agents, Prompts, Versions, Guardrails
│   │   ├── rag/             # Knowledge Bases, Documents, Chunks, pgvector
│   │   ├── workflows/       # DAG Automation Builder, Nodes, Execution Engine
│   │   ├── tools/           # Custom Tool Execution & API Invocation
│   │   ├── campaigns/       # Broadcasts, Templates, Audience Segments
│   │   ├── integrations/    # External Apps & Actions
│   │   ├── webhooks/        # Outgoing Webhooks, Deliveries, Retries
│   │   ├── billing/         # Subscriptions, Invoices, Stripe Integration
│   │   ├── usage/           # Credit Ledger, Token Accounting, Balances
│   │   └── audit/           # Audit Logs, Security Events, API Keys
│   ├── workers/             # Celery background workers and periodic tasks
│   ├── config.py            # Environment-driven settings (pydantic-settings)
│   ├── constants.py         # Universal enums and system constants
│   ├── database.py          # Async engine, session factories, RLS helpers
│   ├── exceptions.py        # Domain & system exception hierarchy
│   ├── main.py              # FastAPI application bootstrap
│   └── security.py          # Auth, tokens, passwords, cryptography
├── docker/                  # Dockerfiles and compose definitions
├── docs/                    # Architectural specs, ERDs, database documentation
├── scripts/                 # Seed scripts, administrative utilities
└── tests/                   # Unit, integration, and tenant-security tests
```

## ⚡ Quickstart

### Prerequisites
- Python 3.12+
- Docker and Docker Compose
- Poetry

### Local Development Setup

1. **Clone repository and setup environment:**
   ```bash
   cp .env.example .env
   ```

2. **Start backing services (PostgreSQL 16 with pgvector & Redis):**
   ```bash
   make db-up
   ```

3. **Install dependencies:**
   ```bash
   make dev
   ```

4. **Run database migrations:**
   ```bash
   make migrate
   ```

5. **Seed initial system data:**
   ```bash
   make seed
   ```

6. **Start the API service:**
   ```bash
   make run
   ```
   The API will be available at `http://localhost:8000/api/v1` and interactive Swagger docs at `http://localhost:8000/docs`.

7. **Start Celery worker:**
   ```bash
   make worker
   ```

## 🧪 Testing

```bash
# Run all tests with coverage
make test

# Run tenant isolation security tests
make test-security
```
# on24agent
