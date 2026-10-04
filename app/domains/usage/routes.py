"""FastAPI router endpoints for Credits, Balances, and Financial Ledger."""

from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.schemas import APIResponse
from app.dependencies import AuthenticatedUserContext, get_db, require_tenant
from app.domains.usage.models import CreditLedger
from app.domains.usage.schemas import (
    CreditBalanceResponse,
    CreditDeductionRequest,
    CreditLedgerEntryResponse,
)
from app.domains.usage.service import CreditService

router = APIRouter()


@router.get("/balance", response_model=APIResponse[CreditBalanceResponse])
async def get_balance(
    user_context: AuthenticatedUserContext = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[CreditBalanceResponse]:
    """Retrieve active organization AI operation credit balance."""
    service = CreditService(db)
    balance = await service.get_or_create_balance(user_context.organization_id)
    return APIResponse.ok(data=CreditBalanceResponse.model_validate(balance))


@router.get("/ledger", response_model=APIResponse[List[CreditLedgerEntryResponse]])
async def get_ledger(
    limit: int = Query(50, ge=1, le=100),
    user_context: AuthenticatedUserContext = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[List[CreditLedgerEntryResponse]]:
    """List double-entry audit history of credit grants and deductions."""
    query = (
        select(CreditLedger)
        .where(CreditLedger.organization_id == user_context.organization_id)
        .order_by(CreditLedger.created_at.desc())
        .limit(limit)
    )
    res = await db.execute(query)
    entries = res.scalars().all()
    return APIResponse.ok(data=[CreditLedgerEntryResponse.model_validate(e) for e in entries])


@router.post("/deduct", response_model=APIResponse[CreditLedgerEntryResponse])
async def deduct_credits(
    payload: CreditDeductionRequest,
    user_context: AuthenticatedUserContext = Depends(require_tenant),
    db: AsyncSession = Depends(get_db),
) -> APIResponse[CreditLedgerEntryResponse]:
    """Manually or programmatically deduct credits for an AI/telephony invocation."""
    service = CreditService(db)
    entry = await service.deduct_credits(user_context.organization_id, payload)
    return APIResponse.ok(data=CreditLedgerEntryResponse.model_validate(entry))
