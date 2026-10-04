"""Pydantic schemas for Credits, Balances, and Usage Accounting."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import Field

from app.common.schemas import BaseSchema
from app.constants import CreditTransactionType


class CreditBalanceResponse(BaseSchema):
    organization_id: UUID
    balance_credits: float
    lifetime_granted_credits: float
    lifetime_consumed_credits: float
    updated_at: datetime


class CreditLedgerEntryResponse(BaseSchema):
    id: UUID
    transaction_type: str
    amount: float
    balance_after: float
    description: str
    reference_id: Optional[UUID] = None
    reference_type: Optional[str] = None
    created_at: datetime


class CreditDeductionRequest(BaseSchema):
    transaction_type: CreditTransactionType
    amount: float = Field(..., gt=0)
    description: str
    reference_id: Optional[UUID] = None
    reference_type: Optional[str] = None
