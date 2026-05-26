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

    if budget is None:
        return BudgetCheckResponse(allowed=True, reason=None, daily_remaining_usd=None)

    now = datetime.utcnow()

    # Compute effective spent values, zeroing out if the period has rolled over
    daily_spent = float(budget.daily_spent_usd)
    if budget.updated_at and budget.updated_at.date() < now.date():
        daily_spent = 0.0

    monthly_spent = float(budget.monthly_spent_usd)
    if budget.updated_at and (budget.updated_at.year, budget.updated_at.month) < (now.year, now.month):
        monthly_spent = 0.0

    daily_remaining = (
        max(0.0, float(budget.daily_limit_usd) - daily_spent)
        if budget.daily_limit_usd is not None else None
    )

    warning = _worst_warning(
        _spend_warning(daily_spent, budget.daily_limit_usd),
        _spend_warning(monthly_spent, budget.monthly_limit_usd),
    )

    if not budget.is_hard_stop_enabled:
        return BudgetCheckResponse(allowed=True, reason=None, daily_remaining_usd=daily_remaining, warning=warning)

    if budget.daily_limit_usd is not None and daily_spent >= float(budget.daily_limit_usd):
        return BudgetCheckResponse(
            allowed=False,
            reason="Daily limit exceeded",
            daily_remaining_usd=0.0,
            warning="hard_stop",
        )

    if budget.monthly_limit_usd is not None and monthly_spent >= float(budget.monthly_limit_usd):
        return BudgetCheckResponse(
            allowed=False,
            reason="Monthly limit exceeded",
            daily_remaining_usd=daily_remaining,
            warning="hard_stop",
        )

    return BudgetCheckResponse(allowed=True, reason=None, daily_remaining_usd=daily_remaining, warning=warning)


def _spend_warning(spent: float, limit: Optional[float]) -> Optional[str]:
    if limit is None or limit <= 0:
        return None
    ratio = spent / float(limit)
    if ratio >= 1.0:
        return "hard_stop"
    if ratio >= 0.8:
        return "near_limit"
    return None


_WARNING_RANK: dict[Optional[str], int] = {None: 0, "near_limit": 1, "hard_stop": 2}


def _worst_warning(*warnings: Optional[str]) -> Optional[str]:
    return max(warnings, key=lambda w: _WARNING_RANK.get(w, 0))
