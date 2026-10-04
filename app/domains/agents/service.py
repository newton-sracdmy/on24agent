"""Business logic service for AI Agent creation, version publishing, and execution."""

from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.agents.models import (
    AgentConfig,
    AgentKnowledgeBase,
    AgentRun,
    AgentTool,
    AgentVersion,
)
from app.domains.agents.schemas import AgentConfigCreate, AgentVersionCreate
from app.exceptions import ResourceNotFoundError


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
