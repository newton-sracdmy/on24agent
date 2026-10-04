"""Central registry importing all SQLAlchemy models across all 16 domains.

Ensures Base.metadata contains complete DDL definitions for Alembic and tests.
"""

from app.common.models import Base

# Domain 1: Identity & Access Management
from app.domains.identity.models import (
    Invitation,
    Membership,
    Organization,
    Permission,
    RefreshToken,
    Role,
    RolePermission,
    Session,
    User,
)

# Domain 2: AI & LLM Providers
from app.domains.ai.models import (
    LLMModel,
    LLMProvider,
    ModelConfig,
    ProviderConfig,
)

# Domain 3: Channels
from app.domains.channels.models import (
    Channel,
    ChannelAccount,
    ChannelAccountCapability,
)

# Domain 4: Contacts & CRM
from app.domains.contacts.models import (
    Contact,
    ContactEvent,
    ContactIdentity,
    ContactNote,
    ContactTag,
    CustomField,
    Tag,
)

# Domain 5: Unified Inbox, SLAs, Teams, CSAT
from app.domains.conversations.models import (
    BusinessHours,
    CannedResponse,
    Conversation,
    Message,
    MessageAttachment,
    MessageReaction,
    Notification,
    RoutingRule,
    SatisfactionRating,
    SLAPolicy,
    Team,
    TeamMember,
)

# Domain 6: Tools
from app.domains.tools.models import Tool

# Domain 7: AI Agents & Execution
from app.domains.agents.models import (
    AgentConfig,
    AgentGuardrail,
    AgentKnowledgeBase,
    AgentRun,
    AgentTool,
    AgentVersion,
    LLMRequest,
    LLMRequestAttempt,
    ToolExecution,
)

# Domain 8: RAG & Knowledge Bases
from app.domains.rag.models import (
    Document,
    DocumentChunk,
    DocumentVersion,
    IngestionError,
    IngestionJob,
    KnowledgeBase,
)

# Domain 9: Campaigns & Broadcasts
from app.domains.campaigns.models import (
    Campaign,
    CampaignRecipient,
    CampaignSegment,
    MessageTemplate,
)

# Domain 10: Workflows & Automations
from app.domains.workflows.models import (
    ExecutionStep,
    Workflow,
    WorkflowEdge,
    WorkflowExecution,
    WorkflowNode,
    WorkflowTrigger,
    WorkflowVersion,
)

# Domain 11: Integrations
from app.domains.integrations.models import (
    Integration,
    IntegrationAction,
    IntegrationEvent,
)

# Domain 12: Webhooks
from app.domains.webhooks.models import (
    WebhookDelivery,
    WebhookEndpoint,
    WebhookEvent,
    WebhookEventType,
)

# Domain 13: Billing & Plans
from app.domains.billing.models import (
    Invoice,
    InvoiceItem,
    PaymentEvent,
    Plan,
    PlanFeature,
    Subscription,
)

# Domain 14: Usage & Credit Ledger
from app.domains.usage.models import (
    CreditBalance,
    CreditLedger,
    UsageAggregate,
    UsageRecord,
)

# Domain 15 & 16: Audit, Security & Outbox
from app.domains.audit.models import (
    APIKey,
    AuditLog,
    IdempotencyKey,
    LoginAttempt,
    OutboxEvent,
    SecurityEvent,
)

__all__ = ["Base"]
