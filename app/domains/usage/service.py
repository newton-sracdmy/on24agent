"""Business logic service for Double-Entry Credit Ledger and Balances."""

from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import CreditTransactionType
from app.domains.usage.models import CreditBalance, CreditLedger
from app.domains.usage.schemas import CreditDeductionRequest
from app.exceptions import InsufficientCreditsError


class CreditService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_or_create_balance(self, org_id: UUID) -> CreditBalance:
        query = select(CreditBalance).where(CreditBalance.organization_id == org_id)
        res = await self.session.execute(query)
        balance = res.scalars().first()
        if not balance:
            balance = CreditBalance(
                organization_id=org_id,
                balance_credits=1000.0,  # Free starter grant
                lifetime_granted_credits=1000.0,
                lifetime_consumed_credits=0.0,
            )
            self.session.add(balance)
            await self.session.flush()
        return balance

    async def deduct_credits(
        self, org_id: UUID, req: CreditDeductionRequest
    ) -> CreditLedger:
        """Atomically deduct credits and write immutable double-entry ledger record."""
        # Row-lock the credit balance using SELECT FOR UPDATE
        query = (
            select(CreditBalance)
            .where(CreditBalance.organization_id == org_id)
            .with_for_update()
        )
        res = await self.session.execute(query)
        balance = res.scalars().first()
        if not balance:
            balance = await self.get_or_create_balance(org_id)

        if float(balance.balance_credits) < req.amount:
            raise InsufficientCreditsError(
                message=f"Action requires {req.amount} credits, but current balance is only {balance.balance_credits}",
                current_balance=float(balance.balance_credits),
                required_credits=req.amount,
            )

        balance.balance_credits = float(balance.balance_credits) - req.amount
        balance.lifetime_consumed_credits = float(balance.lifetime_consumed_credits) + req.amount

        ledger_entry = CreditLedger(
            organization_id=org_id,
            transaction_type=req.transaction_type.value,
            amount=-req.amount,
            balance_after=float(balance.balance_credits),
            description=req.description,
            reference_id=req.reference_id,
            reference_type=req.reference_type,
        )
        self.session.add(ledger_entry)
        await self.session.flush()
        return ledger_entry

    async def grant_credits(
        self,
        org_id: UUID,
        amount: float,
        description: str,
        transaction_type: CreditTransactionType = CreditTransactionType.ONE_TIME_PURCHASE,
    ) -> CreditLedger:
        query = (
            select(CreditBalance)
            .where(CreditBalance.organization_id == org_id)
            .with_for_update()
        )
        res = await self.session.execute(query)
        balance = res.scalars().first()
        if not balance:
            balance = await self.get_or_create_balance(org_id)

        balance.balance_credits = float(balance.balance_credits) + amount
        balance.lifetime_granted_credits = float(balance.lifetime_granted_credits) + amount

        ledger_entry = CreditLedger(
            organization_id=org_id,
            transaction_type=transaction_type.value,
            amount=amount,
            balance_after=float(balance.balance_credits),
            description=description,
        )
        self.session.add(ledger_entry)
        await self.session.flush()
        return ledger_entry
