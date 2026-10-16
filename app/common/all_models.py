"""Central registry importing all SQLAlchemy models across all domains.

Ensures Base.metadata contains complete DDL definitions for Alembic and tests.
"""

from app.common.models import Base

# Domain 1: Identity & Access Management
from app.domains.identity.models import (
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
)

# Domain 3: Channels
from app.domains.channels.models import (
    Channel,
    ChannelAccount,
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
    CannedResponse,
    Conversation,
    Message,
    MessageAttachment,
    SatisfactionRating,
    SLAPolicy,
    Team,
)

# Domain 6: Tools
from app.domains.tools.models import Tool

# Domain 7: AI Agents & Execution
from app.domains.agents.models import (
    AgentConfig,
    AgentKnowledgeBase,
    AgentRun,
    AgentTool,
    AgentVersion,
)

# Domain 8: RAG & Knowledge Bases
from app.domains.rag.models import (
    Document,
    DocumentChunk,
    DocumentVersion,
    KnowledgeBase,
)

# Domain 9: Campaigns & Broadcasts
from app.domains.campaigns.models import (
    Campaign,
    CampaignSegment,
    MessageTemplate,
)

# Domain 10: Integrations
from app.domains.integrations.models import Integration

# Domain 11: Billing & Plans
from app.domains.billing.models import (
    Plan,
    Subscription,
)

# Domain 12: Usage & Credit Ledger
from app.domains.usage.models import (
    CreditBalance,
    CreditLedger,
)

__all__ = ["Base"]
