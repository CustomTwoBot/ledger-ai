from datetime import datetime, timedelta
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.database import get_db
from app.models import Alert, AlertType, Budget, Cost
from app.pricing import compute_cost
from app.schemas import (
    AgentBreakdown,
    CostLogRequest,
    CostLogResponse,
    CostSummaryResponse,
    ModelBreakdown,
)
from app.config import settings

router = APIRouter(prefix="/api/v1/costs", tags=["costs"])


def _period_start(period: str) -> Optional[datetime]:
    now = datetime.utcnow()
    if period == "daily":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == "monthly":
        return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return None  # "all"


@router.get("/summary", response_model=CostSummaryResponse)
def cost_summary(
    agent_id: Optional[str] = Query(None),
    period: Literal["daily", "monthly", "all"] = Query("daily"),
    db: Session = Depends(get_db),
):
    since = _period_start(period)

    base = db.query(Cost)
    if agent_id:
        base = base.filter(Cost.agent_id == agent_id)
    if since:
        base = base.filter(Cost.timestamp >= since)

    # Overall totals
    totals = base.with_entities(
        func.coalesce(func.sum(Cost.cost_usd), 0).label("total_cost"),
        func.count(Cost.id).label("total_calls"),
    ).one()

    # Breakdown by model
    model_rows = (
        base.with_entities(
            Cost.model,
            Cost.provider,
            func.count(Cost.id).label("call_count"),
            func.sum(Cost.input_tokens).label("input_tokens"),
            func.sum(Cost.output_tokens).label("output_tokens"),
            func.sum(Cost.cost_usd).label("total_cost"),
        )
        .group_by(Cost.model, Cost.provider)
        .all()
    )

    by_model: List[ModelBreakdown] = [
        ModelBreakdown(
            model=r.model,
            provider=r.provider,
            call_count=r.call_count,
            total_input_tokens=r.input_tokens or 0,
            total_output_tokens=r.output_tokens or 0,
            total_cost_usd=float(r.total_cost),
        )
        for r in model_rows
    ]

    # Breakdown by agent (only when not filtered to a single agent)
    by_agent: Optional[List[AgentBreakdown]] = None
    if not agent_id:
        agent_rows = (
            base.with_entities(
                Cost.agent_id,
                func.count(Cost.id).label("call_count"),
                func.sum(Cost.cost_usd).label("total_cost"),
            )
            .group_by(Cost.agent_id)
            .order_by(func.sum(Cost.cost_usd).desc())
            .all()
        )
        by_agent = [
            AgentBreakdown(
                agent_id=r.agent_id,
                call_count=r.call_count,
                total_cost_usd=float(r.total_cost),
            )
            for r in agent_rows
        ]

    return CostSummaryResponse(
        agent_id=agent_id,
        period=period,
        total_cost_usd=float(totals.total_cost),
        total_calls=totals.total_calls,
        by_model=by_model,
        by_agent=by_agent,
    )


def _reset_periods_if_needed(budget: Budget, now: datetime) -> None:
    """Zero out daily/monthly spent when the calendar period rolls over."""
    if budget.updated_at is None:
        return
    if budget.updated_at.date() < now.date():
        budget.daily_spent_usd = 0
    if (budget.updated_at.year, budget.updated_at.month) < (now.year, now.month):
        budget.monthly_spent_usd = 0


def _maybe_create_alert(
    db: Session,
    budget: Budget,
    agent_id: str,
    now: datetime,
) -> None:
    """Insert alert rows when thresholds are crossed, rate-limited to once per hour."""
    one_hour_ago = now - timedelta(hours=1)

    def already_alerted(alert_type: AlertType) -> bool:
        return (
            db.query(Alert)
            .filter(
                Alert.agent_id == agent_id,
                Alert.alert_type == alert_type,
                Alert.sent_at >= one_hour_ago,
            )
            .first()
            is not None
        )

    # Hard-stop alert
    daily_exceeded = (
        budget.daily_limit_usd is not None
        and float(budget.daily_spent_usd) >= float(budget.daily_limit_usd)
    )
    monthly_exceeded = (
        budget.monthly_limit_usd is not None
        and float(budget.monthly_spent_usd) >= float(budget.monthly_limit_usd)
    )

    if (daily_exceeded or monthly_exceeded) and not already_alerted(AlertType.hard_stop):
        period = "daily" if daily_exceeded else "monthly"
        db.add(Alert(
            agent_id=agent_id,
            alert_type=AlertType.hard_stop,
            threshold_pct=100,
            message=f"Agent {agent_id!r} has hit its {period} budget limit.",
            sent_at=now,
        ))
        return  # no need to also fire approaching_limit

    # Approaching-limit alert
    threshold = settings.alert_threshold_pct / 100
    daily_approaching = (
        budget.daily_limit_usd is not None
        and float(budget.daily_spent_usd) >= float(budget.daily_limit_usd) * threshold
    )
    monthly_approaching = (
        budget.monthly_limit_usd is not None
        and float(budget.monthly_spent_usd) >= float(budget.monthly_limit_usd) * threshold
    )

    if (daily_approaching or monthly_approaching) and not already_alerted(AlertType.approaching_limit):
        period = "daily" if daily_approaching else "monthly"
        db.add(Alert(
            agent_id=agent_id,
            alert_type=AlertType.approaching_limit,
            threshold_pct=settings.alert_threshold_pct,
            message=(
                f"Agent {agent_id!r} has used {settings.alert_threshold_pct}% "
                f"of its {period} budget."
            ),
            sent_at=now,
        ))


@router.post("/log", response_model=CostLogResponse, status_code=status.HTTP_201_CREATED)
def log_cost(payload: CostLogRequest, db: Session = Depends(get_db)):
    # Idempotency: return existing result if request_id already logged
    existing = db.query(Cost).filter(Cost.request_id == payload.request_id).first()
    if existing:
        budget = db.query(Budget).filter(Budget.agent_id == payload.agent_id).first()
        return _build_log_response(float(existing.cost_usd), budget)

    try:
        cost_usd = compute_cost(payload.model, payload.input_tokens, payload.output_tokens)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    now = datetime.utcnow()

    cost_row = Cost(
        agent_id=payload.agent_id,
        provider=payload.provider,
        model=payload.model,
        input_tokens=payload.input_tokens,
        output_tokens=payload.output_tokens,
        cost_usd=cost_usd,
        timestamp=now,
        request_id=payload.request_id,
    )
    db.add(cost_row)

    # Lock the budget row for atomic update
    budget = (
        db.query(Budget)
        .filter(Budget.agent_id == payload.agent_id)
        .with_for_update()
        .first()
    )

    if budget is not None:
        _reset_periods_if_needed(budget, now)
        budget.daily_spent_usd = float(budget.daily_spent_usd) + cost_usd
        budget.monthly_spent_usd = float(budget.monthly_spent_usd) + cost_usd
        budget.updated_at = now
        _maybe_create_alert(db, budget, payload.agent_id, now)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        # Race condition: another request won with the same request_id
        existing = db.query(Cost).filter(Cost.request_id == payload.request_id).first()
        budget = db.query(Budget).filter(Budget.agent_id == payload.agent_id).first()
        return _build_log_response(float(existing.cost_usd), budget)

    return _build_log_response(cost_usd, budget)


def _build_log_response(cost_usd: float, budget: Optional[Budget]) -> CostLogResponse:
    if budget is None:
        return CostLogResponse(cost_usd=cost_usd, daily_remaining_usd=None, hard_stop=False)

    daily_remaining: Optional[float] = None
    if budget.daily_limit_usd is not None:
        daily_remaining = max(0.0, float(budget.daily_limit_usd) - float(budget.daily_spent_usd))

    hard_stop = False
    if budget.is_hard_stop_enabled:
        daily_exceeded = (
            budget.daily_limit_usd is not None
            and float(budget.daily_spent_usd) >= float(budget.daily_limit_usd)
        )
        monthly_exceeded = (
            budget.monthly_limit_usd is not None
            and float(budget.monthly_spent_usd) >= float(budget.monthly_limit_usd)
        )
        hard_stop = daily_exceeded or monthly_exceeded

    return CostLogResponse(
        cost_usd=cost_usd,
        daily_remaining_usd=daily_remaining,
        hard_stop=hard_stop,
    )
