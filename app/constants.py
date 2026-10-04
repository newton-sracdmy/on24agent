"""Application constants and database enum types for Gabster AI.

All enum values correspond directly to PostgreSQL native ENUMs or strict text column constraints.
"""

from enum import Enum


# ==============================================================================
# Identity & RBAC
# ==============================================================================

class UserStatus(str, Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    PENDING_VERIFICATION = "pending_verification"
    DEACTIVATED = "deactivated"


class OrganizationStatus(str, Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    DELINQUENT = "delinquent"
    ARCHIVED = "archived"


class MembershipRole(str, Enum):
    OWNER = "owner"
    ADMIN = "admin"
    AGENT = "agent"
    SUPERVISOR = "supervisor"
    VIEWER = "viewer"


class AgentOnlineStatus(str, Enum):
    ONLINE = "online"
    BUSY = "busy"
    AWAY = "away"
    OFFLINE = "offline"


class InvitationStatus(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    EXPIRED = "expired"
    REVOKED = "revoked"


# ==============================================================================
# Channels & Communication
# ==============================================================================

class ChannelType(str, Enum):
    WHATSAPP = "whatsapp"
    INSTAGRAM = "instagram"
    TELEGRAM = "telegram"
    MESSENGER = "messenger"
    TIKTOK = "tiktok"
    EMAIL = "email"
    WEBCHAT = "webchat"
    VOICE = "voice"
    SMS = "sms"


class ChannelAccountStatus(str, Enum):
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    ERROR = "error"
    RATE_LIMITED = "rate_limited"
    PENDING_AUTH = "pending_auth"


class CapabilityType(str, Enum):
    RECEIVE_TEXT = "receive_text"
    SEND_TEXT = "send_text"
    RECEIVE_MEDIA = "receive_media"
    SEND_MEDIA = "send_media"
    TEMPLATES = "templates"
    INTERACTIVE_BUTTONS = "interactive_buttons"
    FLOWS = "flows"
    VOICE_CALLS = "voice_calls"
    READ_RECEIPTS = "read_receipts"


# ==============================================================================
# Contacts & CRM
# ==============================================================================

class ContactLifecycleStage(str, Enum):
    LEAD = "lead"
    MARKETING_QUALIFIED = "marketing_qualified"
    SALES_QUALIFIED = "sales_qualified"
    OPPORTUNITY = "opportunity"
    CUSTOMER = "customer"
    EVANGELIST = "evangelist"
    CHURNED = "churned"


class IdentityType(str, Enum):
    PHONE = "phone"
    EMAIL = "email"
    WHATSAPP_ID = "whatsapp_id"
    INSTAGRAM_SCOPED_ID = "instagram_scoped_id"
    TELEGRAM_USER_ID = "telegram_user_id"
    WEB_SESSION_ID = "web_session_id"
    EXTERNAL_SYSTEM_ID = "external_system_id"


class ContactEventType(str, Enum):
    CREATED = "created"
    CONVERSATION_STARTED = "conversation_started"
    CONVERSATION_RESOLVED = "conversation_resolved"
    NOTE_ADDED = "note_added"
    TAG_ADDED = "tag_added"
    TAG_REMOVED = "tag_removed"
    STAGE_CHANGED = "stage_changed"
    CAMPAIGN_SENT = "campaign_sent"
    CALL_COMPLETED = "call_completed"


# ==============================================================================
# Conversations & Messaging
# ==============================================================================

class ConversationStatus(str, Enum):
    OPEN = "open"
    WAITING_FOR_USER = "waiting_for_user"
    WAITING_FOR_AGENT = "waiting_for_agent"
    SNOOZED = "snoozed"
    RESOLVED = "resolved"
    CLOSED = "closed"


class ConversationPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class MessageSenderType(str, Enum):
    CONTACT = "contact"
    AGENT = "agent"
    AI_BOT = "ai_bot"
    SYSTEM = "system"
    WORKFLOW = "workflow"


class MessageContentType(str, Enum):
    TEXT = "text"
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    DOCUMENT = "document"
    LOCATION = "location"
    STICKER = "sticker"
    TEMPLATE = "template"
    INTERACTIVE = "interactive"
    VOICE_NOTE = "voice_note"


class MessageDeliveryStatus(str, Enum):
    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"
    FAILED = "failed"


class RoutingStrategy(str, Enum):
    ROUND_ROBIN = "round_robin"
    LEAST_BUSY = "least_busy"
    SKILL_BASED = "skill_based"
    AI_FIRST = "ai_first"
    MANUAL = "manual"


class SLAPriorityTier(str, Enum):
    URGENT = "urgent"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


class SLABreachStatus(str, Enum):
    WITHIN_SLA = "within_sla"
    AT_RISK = "at_risk"
    BREACHED = "breached"


# ==============================================================================
# AI & Agent Framework
# ==============================================================================

class AIProviderType(str, Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    GROQ = "groq"
    MISTRAL = "mistral"
    LOCAL_VLLM = "local_vllm"
    ELEVENLABS = "elevenlabs"
    DEEPGRAM = "deepgram"


class ModelModality(str, Enum):
    TEXT_ONLY = "text_only"
    MULTIMODAL_VISION = "multimodal_vision"
    AUDIO_SPEECH = "audio_speech"
    EMBEDDING = "embedding"


class AgentExecutionMode(str, Enum):
    AUTONOMOUS = "autonomous"
    COPILOT = "copilot"
    HUMAN_SUPERVISED = "human_supervised"
    OFFLINE = "offline"


class AgentRunStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    ESCALATED = "escalated"


class GuardrailAction(str, Enum):
    ALLOW = "allow"
    BLOCK = "block"
    REWRITE = "rewrite"
    ESCALATE_TO_HUMAN = "escalate_to_human"


# ==============================================================================
# RAG & Knowledge Base
# ==============================================================================

class DocumentSourceType(str, Enum):
    FILE_UPLOAD = "file_upload"
    WEBSITE_CRAWL = "website_crawl"
    NOTION_SYNC = "notion_sync"
    GOOGLE_DRIVE = "google_drive"
    MANUAL_ENTRY = "manual_entry"
    API_IMPORT = "api_import"


class IngestionJobStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    INDEXED = "indexed"
    FAILED = "failed"
    OUTDATED = "outdated"


class ChunkingStrategy(str, Enum):
    FIXED_SIZE = "fixed_size"
    PARAGRAPH_AWARE = "paragraph_aware"
    SEMANTIC = "semantic"
    MARKDOWN_HEADER = "markdown_header"


class VectorDistanceMetric(str, Enum):
    COSINE = "cosine"
    L2 = "l2"
    INNER_PRODUCT = "inner_product"


# ==============================================================================
# Campaigns & WhatsApp Templates
# ==============================================================================

class TemplateCategory(str, Enum):
    MARKETING = "marketing"
    UTILITY = "utility"
    AUTHENTICATION = "authentication"


class TemplateApprovalStatus(str, Enum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    APPROVED = "approved"
    REJECTED = "rejected"
    PAUSED = "paused"
    DISABLED = "disabled"


class CampaignStatus(str, Enum):
    DRAFT = "draft"
    SCHEDULED = "scheduled"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class CampaignRecipientStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"
    FAILED = "failed"
    REPLIED = "replied"


# ==============================================================================
# Workflows & Automations
# ==============================================================================

class WorkflowTriggerType(str, Enum):
    MESSAGE_RECEIVED = "message_received"
    CONVERSATION_OPENED = "conversation_opened"
    CONVERSATION_RESOLVED = "conversation_resolved"
    CONTACT_TAG_ADDED = "contact_tag_added"
    SLA_BREACHED = "sla_breached"
    WEBHOOK_RECEIVED = "webhook_received"
    SCHEDULED_CRON = "scheduled_cron"


class WorkflowNodeType(str, Enum):
    TRIGGER = "trigger"
    CONDITION = "condition"
    SEND_MESSAGE = "send_message"
    AI_GENERATE = "ai_generate"
    ASSIGN_AGENT = "assign_agent"
    UPDATE_CONTACT = "update_contact"
    HTTP_REQUEST = "http_request"
    WAIT_FOR_INPUT = "wait_for_input"
    DELAY = "delay"
    BRANCH = "branch"


class WorkflowExecutionStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED_WAITING_INPUT = "paused_waiting_input"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


# ==============================================================================
# Billing & Credits
# ==============================================================================

class PlanTier(str, Enum):
    FREE = "free"
    SOLO = "solo"
    STANDARD = "standard"
    BUSINESS = "business"
    ENTERPRISE = "enterprise"


class BillingInterval(str, Enum):
    MONTHLY = "monthly"
    ANNUAL = "annual"


class SubscriptionStatus(str, Enum):
    TRIALING = "trialing"
    ACTIVE = "active"
    PAST_DUE = "past_due"
    UNPAID = "unpaid"
    CANCELLED = "cancelled"
    INCOMPLETE = "incomplete"


class InvoiceStatus(str, Enum):
    DRAFT = "draft"
    OPEN = "open"
    PAID = "paid"
    VOID = "void"
    UNCOLLECTIBLE = "uncollectible"


class CreditTransactionType(str, Enum):
    SUBSCRIPTION_GRANT = "subscription_grant"
    ONE_TIME_PURCHASE = "one_time_purchase"
    DEDUCTION_LLM_TOKENS = "deduction_llm_tokens"
    DEDUCTION_VOICE_SECONDS = "deduction_voice_seconds"
    DEDUCTION_WHATSAPP_CONVERSATION = "deduction_whatsapp_conversation"
    DEDUCTION_RAG_EMBEDDING = "deduction_rag_embedding"
    REFUND_PROMO = "refund_promo"
    MANUAL_ADJUSTMENT = "manual_adjustment"


# ==============================================================================
# Audit & Outbox
# ==============================================================================

class AuditAction(str, Enum):
    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    LOGIN_SUCCESS = "login_success"
    LOGIN_FAILURE = "login_failure"
    ROLE_CHANGE = "role_change"
    API_KEY_ROTATED = "api_key_rotated"
    EXPORT_TRIGGERED = "export_triggered"


class SecurityEventType(str, Enum):
    BRUTE_FORCE_ATTEMPT = "brute_force_attempt"
    UNAUTHORIZED_ACCESS = "unauthorized_access"
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"
    PROMPT_INJECTION_DETECTED = "prompt_injection_detected"
    PII_LEAK_PREVENTED = "pii_leak_prevented"


class OutboxEventStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    PUBLISHED = "published"
    FAILED = "failed"
    DEAD_LETTER = "dead_letter"
