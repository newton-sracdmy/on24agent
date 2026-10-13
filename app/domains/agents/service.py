"""Business logic service for AI Agent creation, version publishing, instruction building, and execution."""

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

import httpx
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.constants import AgentExecutionMode
from app.domains.agents.models import (
    AgentConfig,
    AgentKnowledgeBase,
    AgentRun,
    AgentTool,
    AgentVersion,
)
from app.domains.agents.schemas import (
    AgentConfigCreate,
    AgentConfigResponse,
    AgentVersionCreate,
    AgentVersionResponse,
    InstructionBuilderPayload,
    InstructionCompileResponse,
    InstructionDeployRequest,
    InstructionGenerateRequest,
    InstructionStudioResponse,
    InstructionTestRequest,
    InstructionTestResponse,
)
from app.domains.ai.gemini_service import GEMINI_MODELS, generate_gemini_response
from app.domains.ai.models import LLMModel
from app.domains.rag.models import KnowledgeBase
from app.exceptions import ResourceNotFoundError

logger = logging.getLogger("agent_service")

# ==============================================================================
# Production Preset Templates
# ==============================================================================

PRESET_TEMPLATES: Dict[str, Dict[str, Any]] = {
    "ecommerce": {
        "id": "ecommerce",
        "title": "E-Commerce Sales & Orders",
        "badge": "Sales & Retail",
        "icon": "shopping-bag",
        "description": "Closes product inquiries, suggests cross-sells, answers delivery FAQs, and handles order tracking.",
        "payload": {
            "agent_name": "Zara - E-Store Concierge",
            "role_title": "E-Commerce Sales & Order Tracking Specialist",
            "tone_of_voice": "Friendly, enthusiastic, and sales-focused",
            "language": "Bengali & English (Banglish friendly)",
            "primary_mission": "Guide online shoppers through product catalog, help them choose size/color variations, capture orders (Name, Phone, Address), and check delivery status.",
            "business_rules": [
                "Inside Dhaka delivery: 24-48 hours (BDT 70). Outside Dhaka: 3-5 days (BDT 130).",
                "Cash on Delivery (COD) and bKash / Nagad advance payments are supported.",
                "Always confirm customer phone number, full shipping address, and chosen size before confirming an order.",
                "Highlight active promotional discounts and mention 7-day hassle-free replacement warranty."
            ],
            "constraints_donts": [
                "NEVER promise custom discounts beyond officially advertised coupon codes.",
                "DO NOT argue with customers regarding defective items; immediately direct them to the replacement procedure.",
                "Never share internal wholesaler suppliers or employee personal contact information."
            ],
            "escalation_protocol": "If customer asks for order cancellation, refund, or reports defective parcel, ask for their Order ID and escalate to the human merchant support team immediately.",
            "greeting_message": "Hello! Welcome to our online shop. How can I help you find the perfect product today?"
        }
    },
    "support": {
        "id": "support",
        "title": "Customer Care & FAQ",
        "badge": "Support & Operations",
        "icon": "headphones",
        "description": "24/7 empathetic assistant for troubleshooting, refund policies, account management, and ticket escalation.",
        "payload": {
            "agent_name": "Alex - Care Concierge",
            "role_title": "24/7 Customer Success & Technical Support Specialist",
            "tone_of_voice": "Empathetic, polite, clear, and solution-driven",
            "language": "Bengali & English",
            "primary_mission": "Resolve user queries accurately, troubleshoot platform issues step-by-step, explain subscription tiers, and maintain high customer satisfaction.",
            "business_rules": [
                "Always ground responses in verified official Knowledge Base documents and documentation.",
                "Clarify the user's issue before proposing multi-step troubleshooting instructions.",
                "Provide clickable documentation links and verify if the issue was resolved before closing conversation."
            ],
            "constraints_donts": [
                "NEVER reveal internal server error tracebacks, API keys, or database IDs.",
                "DO NOT guess technical answers if not confirmed in the knowledge base.",
                "Never blame the user or use dismissive language."
            ],
            "escalation_protocol": "If the issue cannot be resolved in 2 turns or customer expresses frustration, promptly notify: 'I am routing your case to a Senior Human Support Engineer right now.'",
            "greeting_message": "Hello! I am your 24/7 Support Assistant. How can I assist you with your account or technical questions today?"
        }
    },
    "leads": {
        "id": "leads",
        "title": "Lead Gen & Sales Closer",
        "badge": "High Conversion",
        "icon": "target",
        "description": "Qualifies B2B and high-ticket B2C leads, answers capability questions, and books consultations.",
        "payload": {
            "agent_name": "Sam - Lead Closer",
            "role_title": "High-Converting B2B & Inbound Lead Qualification Specialist",
            "tone_of_voice": "Professional, consultative, persuasive, and proactive",
            "language": "English & Bengali",
            "primary_mission": "Discover prospect business needs, budget, and timeline (BANT framework), showcase solution ROI, and book executive demo calls.",
            "business_rules": [
                "Ask open-ended qualifying questions to identify the client's current pain points.",
                "Highlight key features, client testimonials, and measurable ROI statistics.",
                "Offer 2 concrete time slots (e.g. tomorrow 11 AM or 3 PM) when proposing a discovery call."
            ],
            "constraints_donts": [
                "DO NOT give speculative custom enterprise pricing without gathering requirements.",
                "DO NOT ask more than 2 questions in a single reply to avoid overwhelming the prospect.",
                "Never use aggressive high-pressure sales tactics."
            ],
            "escalation_protocol": "When prospect confirms high intent or provides budget criteria, collect their corporate email and direct phone, then assign immediately to Senior Sales Director.",
            "greeting_message": "Hi there! Thanks for reaching out. What key objectives or challenges is your team looking to tackle this quarter?"
        }
    },
    "community": {
        "id": "community",
        "title": "Community Concierge",
        "badge": "Community & VIP",
        "icon": "users",
        "description": "Greets club members, answers event schedules, bootcamp details, and enforces code of conduct.",
        "payload": {
            "agent_name": "TechVibe Community Guide",
            "role_title": "24/7 Community Operations Specialist for TechVibe Members Club",
            "tone_of_voice": "Energetic, warm, community-centric, with friendly emojis",
            "language": "Bengali & English",
            "primary_mission": "Assist TechVibe Members Club members with guidelines, VIP membership perks, upcoming event dates, workshops, and technical discussions.",
            "business_rules": [
                "Promote upcoming community workshops, hackathons, and networking sessions.",
                "Explain the benefits of VIP tier (priority access, mentor office hours, exclusive perks).",
                "Answer member technical and programming questions concisely with code snippets when needed."
            ],
            "constraints_donts": [
                "Zero tolerance for abusive language or harassment; warn violators respectfully.",
                "Do not promise event speakers or schedules that have not been officially published."
            ],
            "escalation_protocol": "For membership refund requests, sponsor partnerships, or disciplinary issues, direct members to the TechVibe Club Admin Team.",
            "greeting_message": "Welcome to TechVibe Members Club! 🚀 How can I help you make the most of our community today?"
        }
    }
}


class AgentService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_agent(self, org_id: UUID, data: AgentConfigCreate) -> AgentConfig:
        agent = AgentConfig(
            organization_id=org_id,
            name=data.name,
            description=data.description,
            mode=data.mode.value,
        )
        self.session.add(agent)
        await self.session.flush()
        return agent

    async def create_version(
        self, org_id: UUID, agent_id: UUID, data: AgentVersionCreate
    ) -> AgentVersion:
        agent = await self.session.get(AgentConfig, agent_id)
        if not agent or agent.organization_id != org_id:
            raise ResourceNotFoundError("AgentConfig", agent_id)

        # Compute next version number
        query = select(AgentVersion.version_number).where(
            AgentVersion.agent_config_id == agent_id
        ).order_by(AgentVersion.version_number.desc())
        res = await self.session.execute(query)
        latest_version = res.scalar() or 0
        new_version_num = latest_version + 1

        version = AgentVersion(
            organization_id=org_id,
            agent_config_id=agent_id,
            version_number=new_version_num,
            system_prompt=data.system_prompt,
            model_id=data.model_id,
            temperature=data.temperature,
            max_tokens=data.max_tokens,
            is_published=False,
        )
        self.session.add(version)
        await self.session.flush()

        # Bind tools
        for tool_id in data.tool_ids:
            binding = AgentTool(
                organization_id=org_id,
                agent_config_id=agent_id,
                tool_id=tool_id,
            )
            self.session.add(binding)

        # Bind knowledge bases
        for kb_id in data.knowledge_base_ids:
            kb_binding = AgentKnowledgeBase(
                organization_id=org_id,
                agent_config_id=agent_id,
                knowledge_base_id=kb_id,
            )
            self.session.add(kb_binding)

        await self.session.flush()
        return version

    async def publish_version(
        self, org_id: UUID, agent_id: UUID, version_id: UUID
    ) -> AgentVersion:
        version = await self.session.get(AgentVersion, version_id)
        if not version or version.organization_id != org_id or version.agent_config_id != agent_id:
            raise ResourceNotFoundError("AgentVersion", version_id)

        now = datetime.now(timezone.utc)
        version.is_published = True
        version.published_at = now

        agent = await self.session.get(AgentConfig, agent_id)
        if agent:
            agent.current_version_id = version.id

        await self.session.flush()
        return version

    # ==========================================================================
    # Instruction Builder Studio Methods
    # ==========================================================================

    @staticmethod
    def compile_instruction_prompt(payload: InstructionBuilderPayload) -> InstructionCompileResponse:
        """Compile modular builder configuration into a robust structured markdown prompt."""
        rules_text = (
            "\n".join(f"- {r.strip()}" for r in payload.business_rules if r.strip())
            if payload.business_rules
            else "None explicitly configured. Follow standard best practices."
        )
        constraints_text = (
            "\n".join(f"- {d.strip()}" for d in payload.constraints_donts if d.strip())
            if payload.constraints_donts
            else "None explicitly specified. Maintain professional customer care ethics."
        )

        escalation_text = (
            payload.escalation_protocol.strip()
            if payload.escalation_protocol
            else "If customer requests human assistance or issue cannot be resolved, politely escalate to our support team."
        )

        greeting_text = (
            payload.greeting_message.strip()
            if payload.greeting_message
            else "Hello! How can I assist you today?"
        )

        compiled_prompt = f"""# ROLE & IDENTITY
You are {payload.agent_name.strip()}, the official {payload.role_title.strip()}.
Tone of Voice: {payload.tone_of_voice.strip()}
Language: {payload.language.strip()} (Always respond fluently in whichever language the user writes: Bengali or English).

# PRIMARY MISSION & OBJECTIVE
{payload.primary_mission.strip()}

# BUSINESS OPERATING RULES & PROCEDURES
{rules_text}

# GUARDRAILS & STRICT CONSTRAINTS (DO NOTs)
{constraints_text}

# ESCALATION & HUMAN HANDOFF PROTOCOL
{escalation_text}

# GREETING & INITIAL TOUCHPOINT
{greeting_text}"""

        word_count = len(compiled_prompt.split())
        estimated_token_count = int(word_count * 1.33) + 4

        return InstructionCompileResponse(
            compiled_prompt=compiled_prompt,
            estimated_token_count=estimated_token_count,
            word_count=word_count,
        )

    @classmethod
    async def get_active_system_prompt(cls, session: AsyncSession, org_id: UUID) -> str:
        """Retrieve the currently active and published system prompt for an organization.
        
        Falls back to a standard intelligent prompt if no agent has been published yet.
        """
        try:
            query = (
                select(AgentVersion.system_prompt)
                .join(AgentConfig, AgentConfig.current_version_id == AgentVersion.id)
                .where(
                    AgentConfig.organization_id == org_id,
                    AgentConfig.is_active.is_(True),
                    AgentVersion.is_published.is_(True),
                )
                .order_by(AgentVersion.published_at.desc().nullslast())
                .limit(1)
            )
            res = await session.execute(query)
            prompt = res.scalar()
            if prompt and prompt.strip():
                return prompt.strip()
        except Exception as e:
            logger.warning(f"Failed to query active system prompt for org {org_id}: {e}")

        # Fallback default prompt
        return (
            "You are the official 24/7 AI Customer Operations Specialist for TechVibe Members Club. "
            "Assist customers politely, concisely, and helpfully. "
            "Always ground your responses in verified knowledge base facts."
        )

    async def get_builder_state(self, org_id: UUID) -> InstructionStudioResponse:
        """Fetch the active agent instruction state or default preset for this organization."""
        query_agent = (
            select(AgentConfig)
            .where(AgentConfig.organization_id == org_id, AgentConfig.is_active.is_(True))
            .order_by(AgentConfig.created_at.desc())
            .limit(1)
        )
        res_agent = await self.session.execute(query_agent)
        agent = res_agent.scalar_one_or_none()

        version: Optional[AgentVersion] = None
        compiled_prompt = ""
        builder_payload: Optional[InstructionBuilderPayload] = None

        if agent and agent.current_version_id:
            version = await self.session.get(AgentVersion, agent.current_version_id)
            if version and version.system_prompt:
                compiled_prompt = version.system_prompt

        # Pick default preset (community preset if techvibe, else ecommerce)
        default_preset_key = "community" if (agent and "techvibe" in agent.name.lower()) else "ecommerce"
        preset_data = PRESET_TEMPLATES[default_preset_key]["payload"]

        if not compiled_prompt:
            builder_payload = InstructionBuilderPayload(
                agent_id=agent.id if agent else None,
                agent_name=agent.name if agent else preset_data["agent_name"],
                role_title=preset_data["role_title"],
                tone_of_voice=preset_data["tone_of_voice"],
                language=preset_data["language"],
                primary_mission=preset_data["primary_mission"],
                business_rules=preset_data["business_rules"],
                constraints_donts=preset_data["constraints_donts"],
                escalation_protocol=preset_data["escalation_protocol"],
                greeting_message=preset_data["greeting_message"],
            )
            compiled_res = self.compile_instruction_prompt(builder_payload)
            compiled_prompt = compiled_res.compiled_prompt
            token_count = compiled_res.estimated_token_count
            word_count = compiled_res.word_count
        else:
            # We have an existing compiled prompt
            builder_payload = InstructionBuilderPayload(
                agent_id=agent.id if agent else None,
                agent_name=agent.name if agent else preset_data["agent_name"],
                role_title=preset_data["role_title"],
                tone_of_voice=preset_data["tone_of_voice"],
                language=preset_data["language"],
                primary_mission=preset_data["primary_mission"],
                business_rules=preset_data["business_rules"],
                constraints_donts=preset_data["constraints_donts"],
                escalation_protocol=preset_data["escalation_protocol"],
                greeting_message=preset_data["greeting_message"],
            )
            word_count = len(compiled_prompt.split())
            token_count = int(word_count * 1.33) + 4

        return InstructionStudioResponse(
            active_agent=AgentConfigResponse.model_validate(agent) if agent else None,
            current_version=AgentVersionResponse.model_validate(version) if version else None,
            builder_payload=builder_payload,
            compiled_prompt=compiled_prompt,
            estimated_token_count=token_count,
            word_count=word_count,
            presets=PRESET_TEMPLATES,
        )

    @staticmethod
    async def generate_ai_instructions(request: InstructionGenerateRequest) -> InstructionBuilderPayload:
        """Auto-draft complete agent instructions using Google Gemini or intelligent domain heuristics."""
        api_key = settings.GOOGLE_API_KEY
        desc = request.business_description.strip()
        tone = request.tone_preference or "Friendly & Empathetic"
        channel = request.target_channel or "WhatsApp & Messenger"

        if api_key:
            prompt = (
                f"You are an expert AI Agent Architect. Based on the following business profile, "
                f"generate a complete, production-grade instruction set for an AI bot operating on {channel}.\n\n"
                f"BUSINESS PROFILE:\n{desc}\n"
                f"PREFERRED TONE:\n{tone}\n\n"
                f"Respond ONLY with valid JSON with this exact structure:\n"
                f"{{\n"
                f'  "agent_name": "Name of Agent",\n'
                f'  "role_title": "Professional Title / Role",\n'
                f'  "tone_of_voice": "{tone}",\n'
                f'  "language": "Bengali & English",\n'
                f'  "primary_mission": "Clear description of the core goal",\n'
                f'  "business_rules": ["Rule 1", "Rule 2", "Rule 3"],\n'
                f'  "constraints_donts": ["Constraint 1", "Constraint 2", "Constraint 3"],\n'
                f'  "escalation_protocol": "How and when to hand over to a human",\n'
                f'  "greeting_message": "Opening greeting text"\n'
                f"}}\n"
                f"No markdown backticks, no explanations, only raw JSON."
            )

            async with httpx.AsyncClient(timeout=14.0) as client:
                for model in GEMINI_MODELS:
                    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
                    try:
                        payload = {
                            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                            "generationConfig": {"temperature": 0.4, "maxOutputTokens": 800},
                        }
                        resp = await client.post(url, json=payload)
                        if resp.status_code == 200:
                            data = resp.json()
                            candidates = data.get("candidates", [])
                            if candidates:
                                text_content = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                                # Extract JSON from response
                                match = re.search(r"\{.*\}", text_content, re.DOTALL)
                                if match:
                                    parsed = json.loads(match.group(0))
                                    return InstructionBuilderPayload(
                                        agent_name=parsed.get("agent_name", "AI Assistant"),
                                        role_title=parsed.get("role_title", "Customer Operations Specialist"),
                                        tone_of_voice=parsed.get("tone_of_voice", tone),
                                        language=parsed.get("language", "Bengali & English"),
                                        primary_mission=parsed.get("primary_mission", f"Help customers with {desc}"),
                                        business_rules=parsed.get("business_rules", [
                                            "Provide accurate answers and verified facts.",
                                            "Confirm details before finalizing inquiries.",
                                        ]),
                                        constraints_donts=parsed.get("constraints_donts", [
                                            "Do not promise discounts without authorization.",
                                            "Do not guess unverified details.",
                                        ]),
                                        escalation_protocol=parsed.get("escalation_protocol", "Escalate to a human agent if unresolved."),
                                        greeting_message=parsed.get("greeting_message", "Hello! How can I help you today?"),
                                    )
                    except Exception as e:
                        logger.warning(f"Gemini instruction drafting failed for model {model}: {e}")

        # Heuristic Domain Fallback
        desc_lower = desc.lower()
        if any(w in desc_lower for w in ["shop", "ecommerce", "store", "product", "dress", "fashion", "order", "delivery"]):
            base = PRESET_TEMPLATES["ecommerce"]["payload"].copy()
            base["agent_name"] = f"{desc[:20].title()} Sales Concierge"
            base["primary_mission"] = f"Manage customer orders, size consultations, and delivery tracking for {desc}."
            return InstructionBuilderPayload(**base)
        elif any(w in desc_lower for w in ["lead", "real estate", "b2b", "agency", "consulting", "booking", "closer"]):
            base = PRESET_TEMPLATES["leads"]["payload"].copy()
            base["agent_name"] = f"{desc[:20].title()} Lead Specialist"
            base["primary_mission"] = f"Qualify prospects, discover requirements, and book appointments for {desc}."
            return InstructionBuilderPayload(**base)
        elif any(w in desc_lower for w in ["club", "community", "tech", "event", "member", "cohort"]):
            base = PRESET_TEMPLATES["community"]["payload"].copy()
            base["agent_name"] = f"{desc[:20].title()} Community Host"
            base["primary_mission"] = f"Assist members with schedules, rules, guidelines, and benefits for {desc}."
            return InstructionBuilderPayload(**base)
        else:
            base = PRESET_TEMPLATES["support"]["payload"].copy()
            base["agent_name"] = f"{desc[:20].title()} Support Specialist"
            base["primary_mission"] = f"Deliver exceptional 24/7 customer care and query resolution for {desc}."
            return InstructionBuilderPayload(**base)

    async def deploy_instructions(
        self, org_id: UUID, data: InstructionDeployRequest
    ) -> AgentVersion:
        """Publish the newly compiled instruction set to the live bot and update AgentConfig."""
        # 1. Fetch or create AgentConfig for this workspace
        agent_id = data.builder_payload.agent_id
        agent: Optional[AgentConfig] = None

        if agent_id:
            agent = await self.session.get(AgentConfig, agent_id)

        if not agent or agent.organization_id != org_id:
            query = (
                select(AgentConfig)
                .where(AgentConfig.organization_id == org_id, AgentConfig.is_active.is_(True))
                .order_by(AgentConfig.created_at.desc())
                .limit(1)
            )
            res = await self.session.execute(query)
            agent = res.scalar_one_or_none()

        if not agent:
            agent = AgentConfig(
                organization_id=org_id,
                name=data.agent_name,
                description="Deployed via Instruction Builder Studio",
                mode=AgentExecutionMode.AUTONOMOUS.value,
                is_active=True,
            )
            self.session.add(agent)
            await self.session.flush()
        else:
            agent.name = data.agent_name

        # 2. Find an active LLM Model
        query_model = (
            select(LLMModel.id)
            .where(LLMModel.is_active.is_(True))
            .order_by(LLMModel.created_at.desc())
            .limit(1)
        )
        res_model = await self.session.execute(query_model)
        model_id = res_model.scalar()

        if not model_id:
            res_any = await self.session.execute(select(LLMModel.id).limit(1))
            model_id = res_any.scalar()

        if not model_id:
            raise ResourceNotFoundError("LLMModel", "Default Model")

        # 3. Compute next version number
        query_ver = (
            select(AgentVersion.version_number)
            .where(AgentVersion.agent_config_id == agent.id)
            .order_by(AgentVersion.version_number.desc())
        )
        res_ver = await self.session.execute(query_ver)
        latest_ver_num = res_ver.scalar() or 0
        new_ver_num = latest_ver_num + 1

        # 4. Create and publish new AgentVersion
        now = datetime.now(timezone.utc)
        version = AgentVersion(
            organization_id=org_id,
            agent_config_id=agent.id,
            version_number=new_ver_num,
            system_prompt=data.compiled_prompt,
            model_id=model_id,
            temperature=0.7,
            max_tokens=1024,
            is_published=True,
            published_at=now,
        )
        self.session.add(version)
        await self.session.flush()

        agent.current_version_id = version.id
        agent.is_active = True

        # 5. Link any active knowledge bases for the organization
        query_kbs = select(KnowledgeBase.id).where(
            KnowledgeBase.organization_id == org_id,
            KnowledgeBase.is_active.is_(True),
        )
        kb_res = await self.session.execute(query_kbs)
        active_kb_ids = kb_res.scalars().all()
        for kb_id in active_kb_ids:
            check_bind = await self.session.execute(
                select(AgentKnowledgeBase).where(
                    AgentKnowledgeBase.agent_config_id == agent.id,
                    AgentKnowledgeBase.knowledge_base_id == kb_id,
                )
            )
            if not check_bind.scalar_one_or_none():
                self.session.add(
                    AgentKnowledgeBase(
                        organization_id=org_id,
                        agent_config_id=agent.id,
                        knowledge_base_id=kb_id,
                    )
                )

        await self.session.flush()
        return version

    async def simulate_test_response(
        self, org_id: UUID, request: InstructionTestRequest
    ) -> InstructionTestResponse:
        """Simulate how the agent responds in the sandbox with draft prompt and RAG grounding."""
        # Fetch knowledge chunks for this organization
        q_chunks = await self.session.execute(
            text(
                """
                SELECT dc.content_text, d.title
                FROM document_chunks dc
                JOIN documents d ON d.id = dc.document_id
                WHERE dc.organization_id = :org_id
                ORDER BY dc.created_at DESC
                LIMIT 6;
                """
            ),
            {"org_id": org_id},
        )
        chunk_rows = q_chunks.mappings().all()
        kb_context = "\n\n".join([f"[{r['title']}]: {r['content_text']}" for r in chunk_rows])

        ai_reply = await generate_gemini_response(
            user_query=request.test_message,
            system_prompt=request.draft_prompt,
            kb_context=kb_context,
        )

        if ai_reply and ai_reply.strip():
            return InstructionTestResponse(
                reply=ai_reply.strip(),
                source="gemini_llm",
                grounded_kb_chunks_count=len(chunk_rows),
            )

        # Fallback simulation if LLM is unavailable or quota limited
        lower_q = request.test_message.lower()
        if "pricing" in lower_q or "cost" in lower_q or "fee" in lower_q or "price" in lower_q or "দাম" in lower_q:
            simulated_text = (
                "Based on our active policy, here are our standard rates: "
                "Solo Plan is $39/mo, Standard Plan is $149/mo, and Business Plan is $529/mo with dedicated AI tokens. "
                "Let me know if you would like me to assist you with onboarding!"
            )
        elif "refund" in lower_q or "return" in lower_q or "ফেরত" in lower_q:
            simulated_text = (
                "Our policy includes a 7-day money-back guarantee for unused subscriptions, and a 7-day hassle-free "
                "replacement policy for physical parcels. Please provide your order or account ID to proceed."
            )
        elif "hi" in lower_q or "hello" in lower_q or "salam" in lower_q or "কেমন" in lower_q:
            simulated_text = (
                "Hello there! 👋 I am your AI assistant, ready to help you with product queries, order tracking, "
                "and membership support. How can I assist you right now?"
            )
        elif chunk_rows:
            # Extractive chunk match
            simulated_text = (
                f"Regarding your query: {chunk_rows[0]['content_text'][:280]}... "
                f"Please let me know if you would like more specific details!"
            )
        else:
            simulated_text = (
                f"Thank you for contacting us! I have processed your inquiry: '{request.test_message}'. "
                f"Following our active operating guidelines, I'm here to ensure you receive prompt, accurate assistance."
            )

        return InstructionTestResponse(
            reply=simulated_text,
            source="simulation_engine",
            grounded_kb_chunks_count=len(chunk_rows),
        )
