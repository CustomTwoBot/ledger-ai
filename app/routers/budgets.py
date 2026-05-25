from datetime import datetime
from typing import Optional
import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Budget
from app.schemas import BudgetCheckResponse, BudgetSetRequest, BudgetSetResponse

router = APIRouter(prefix="/api/v1/budgets", tags=["budgets"])


@router.post("/set", response_model=BudgetSetResponse, status_code=status.HTTP_200_OK)
def set_budget(payload: BudgetSetRequest, db: Session = Depends(get_db)):
    budget = (
        db.query(Budget)
        .filter(Budget.agent_id == payload.agent_id)
        .with_for_update()
        .first()
    )
    if budget is None:
        budget = Budget(
            id=uuid.uuid4(),
            agent_id=payload.agent_id,
            daily_spent_usd=0,
            monthly_spent_usd=0,
            updated_at=datetime.utcnow(),
        )
        db.add(budget)

    budget.daily_limit_usd = payload.daily_limit_usd
    budget.monthly_limit_usd = payload.monthly_limit_usd
    budget.is_hard_stop_enabled = payload.is_hard_stop_enabled
    budget.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(budget)

    return BudgetSetResponse(
        agent_id=budget.agent_id,
        daily_limit_usd=float(budget.daily_limit_usd) if budget.daily_limit_usd is not None else None,
        monthly_limit_usd=float(budget.monthly_limit_usd) if budget.monthly_limit_usd is not None else None,
        daily_spent_usd=float(budget.daily_spent_usd),
        monthly_spent_usd=float(budget.monthly_spent_usd),
        is_hard_stop_enabled=budget.is_hard_stop_enabled,
    )


@router.get("/check", response_model=BudgetCheckResponse)
def check_budget(agent_id: str, db: Session = Depends(get_db)):
    budget = db.query(Budget).filter(Budget.agent_id == agent_id).first()

    # No budget configured → always allow
    if budget is None:
        return BudgetCheckResponse(allowed=True, reason=None, daily_remaining_usd=None)

    # Hard stop is disabled → report remaining but never block
    if not budget.is_hard_stop_enabled:
        daily_remaining = _daily_remaining(budget)
        return BudgetCheckResponse(allowed=True, reason=None, daily_remaining_usd=daily_remaining)

    now = datetime.utcnow()

    # Daily limit check
    if budget.daily_limit_usd is not None:
        daily_spent = float(budget.daily_spent_usd)
        daily_limit = float(budget.daily_limit_usd)
        # Spent resets at midnight; if the budget was last updated on a prior day it's already reset
        if budget.updated_at and budget.updated_at.date() < now.date():
            daily_spent = 0.0
        if daily_spent >= daily_limit:
            return BudgetCheckResponse(
                allowed=False,
                reason="Daily limit exceeded",
                daily_remaining_usd=0.0,
            )

    # Monthly limit check
    if budget.monthly_limit_usd is not None:
        monthly_spent = float(budget.monthly_spent_usd)
        monthly_limit = float(budget.monthly_limit_usd)
        if budget.updated_at and (
            budget.updated_at.year,
            budget.updated_at.month,
        ) < (now.year, now.month):
            monthly_spent = 0.0
        if monthly_spent >= monthly_limit:
            return BudgetCheckResponse(
                allowed=False,
                reason="Monthly limit exceeded",
                daily_remaining_usd=_daily_remaining(budget),
            )

    return BudgetCheckResponse(
        allowed=True,
        reason=None,
        daily_remaining_usd=_daily_remaining(budget),
    )


def _daily_remaining(budget: Budget) -> Optional[float]:
    if budget.daily_limit_usd is None:
        return None
    return max(0.0, float(budget.daily_limit_usd) - float(budget.daily_spent_usd))
