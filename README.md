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

## 🐳 Running with Docker

You can run the Gabster AI platform using Docker in two different ways:

---

### Option 1: Full-Stack Docker Deployment
Run the complete stack (FastAPI Backend, PostgreSQL with pgvector, Redis, and Celery Worker) together in Docker containers:

1. **Build and start all services in detached mode:**
   ```bash
   docker compose -f docker/docker-compose.yml up -d --build
   ```

2. **Apply database migrations:**
   ```bash
   docker compose -f docker/docker-compose.yml exec api alembic upgrade head
   ```

3. **Stream live logs:**
   ```bash
   docker compose -f docker/docker-compose.yml logs -f
   # Or stream logs for the API service only:
   docker compose -f docker/docker-compose.yml logs -f api
   ```

4. **Check status of running containers:**
   ```bash
   docker compose -f docker/docker-compose.yml ps
   ```

5. **Stop all services:**
   ```bash
   docker compose -f docker/docker-compose.yml down
   ```

---

### Option 2: Hybrid / Developer Mode (Databases in Docker + Server in Local Terminal)
Recommended for active development with instant hot-reloading on code edits:

1. **Start only PostgreSQL (pgvector) and Redis in Docker:**
   ```bash
   make db-up
   # Or manually:
   docker compose -f docker/docker-compose.dev.yml up -d
   ```

2. **Start the FastAPI server in your terminal with auto-reload:**
   ```bash
   .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   ```

3. **Stop background database containers when finished:**
   ```bash
   make db-down
   # Or manually:
   docker compose -f docker/docker-compose.dev.yml down
   ```

---

## 🌐 Live Meta WhatsApp, Facebook Messenger & Instagram Webhook Tunnel (Ngrok)

To receive real-time incoming webhooks from Meta Cloud API (WhatsApp), Facebook Messenger, and Instagram Direct on your local machine, keep an Ngrok tunnel active:

```bash
ngrok http --domain=salad-clapper-dowry.ngrok-free.dev 8000
```

> **Webhook URLs:**
> - WhatsApp Webhook: `https://salad-clapper-dowry.ngrok-free.dev/webhooks/whatsapp`
> - Messenger Webhook: `https://salad-clapper-dowry.ngrok-free.dev/webhooks/facebook`
> - Instagram Webhook: `https://salad-clapper-dowry.ngrok-free.dev/webhooks/instagram`

---

## 🖥️ Dashboard & Credentials

Once the server is running, open your browser and navigate to:
- **Local Application:** [http://localhost:8000](http://localhost:8000)
- **Public URL (via Ngrok):** `https://salad-clapper-dowry.ngrok-free.dev`
- **Interactive Swagger API Docs:** [http://localhost:8000/docs](http://localhost:8000/docs)

**Default Admin Credentials:**
- **Email:** `admin@gabster.ai`
- **Password:** `Password123!`

---

## 🧪 Testing

```bash
# Run all tests with coverage
make test

# Run tenant isolation security tests
make test-security
```
