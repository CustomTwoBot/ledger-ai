from datetime import datetime, timedelta
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import cast, Date, func
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
    RecentCostEntry,
    TimeseriesPoint,
    TimeseriesResponse,
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


@router.get("/timeseries", response_model=TimeseriesResponse)
def cost_timeseries(
    period: Literal["daily"] = Query("daily"),
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
):
    since = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days - 1)

    rows = (
        db.query(
            cast(Cost.timestamp, Date).label("day"),
            func.sum(Cost.cost_usd).label("total_cost"),
        )
        .filter(Cost.timestamp >= since)
        .group_by("day")
        .order_by("day")
        .all()
    )

    costs_by_date = {str(r.day): float(r.total_cost) for r in rows}
    today = datetime.utcnow().date()
    points = [
        TimeseriesPoint(
            date=str(today - timedelta(days=i)),
            cost_usd=costs_by_date.get(str(today - timedelta(days=i)), 0.0),
        )
        for i in range(days - 1, -1, -1)
    ]

    return TimeseriesResponse(period=period, points=points)


@router.get("/recent", response_model=List[RecentCostEntry])
def recent_costs(
    limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(Cost)
        .order_by(Cost.timestamp.desc())
        .limit(limit)
        .all()
    )
    return [
        RecentCostEntry(
            agent_id=r.agent_id,
            model=r.model,
            cost_usd=float(r.cost_usd),
            timestamp=r.timestamp,
        )
        for r in rows
    ]


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
            base.outerjoin(Budget, Budget.agent_id == Cost.agent_id)
            .with_entities(
                Cost.agent_id,
                func.count(Cost.id).label("call_count"),
                func.sum(Cost.cost_usd).label("total_cost"),
                Budget.daily_limit_usd,
                Budget.monthly_limit_usd,
                Budget.daily_spent_usd,
                Budget.monthly_spent_usd,
                Budget.is_hard_stop_enabled,
            )
            .group_by(
                Cost.agent_id,
                Budget.daily_limit_usd,
                Budget.monthly_limit_usd,
                Budget.daily_spent_usd,
                Budget.monthly_spent_usd,
                Budget.is_hard_stop_enabled,
            )
            .order_by(func.sum(Cost.cost_usd).desc())
            .all()
        )
        by_agent = [
            AgentBreakdown(
                agent_id=r.agent_id,
                call_count=r.call_count,
                total_cost_usd=float(r.total_cost),
                budget_limit=float(
                    r.monthly_limit_usd if period == "monthly" else r.daily_limit_usd
                ) if (r.monthly_limit_usd if period == "monthly" else r.daily_limit_usd) is not None else None,
                daily_spent=float(r.daily_spent_usd) if r.daily_spent_usd is not None else None,
                hard_stop=bool(r.is_hard_stop_enabled) and (
                    (r.daily_limit_usd is not None and float(r.daily_spent_usd or 0) >= float(r.daily_limit_usd))
                    or
                    (r.monthly_limit_usd is not None and float(r.monthly_spent_usd or 0) >= float(r.monthly_limit_usd))
                ),
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
