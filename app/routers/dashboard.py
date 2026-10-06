from datetime import datetime, timedelta
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import cast, Date, func, and_
from sqlalchemy.orm import Session

from app.auth import limiter, require_api_key
from app.database import get_db
from app.models import ApiKey, Budget, Cost
from app.schemas import (
    AgentBreakdown,
    CostSummaryResponse,
    DashboardStatsResponse,
    ModelBreakdown,
    RecentCostEntry,
    TimeseriesPoint,
    TimeseriesResponse,
)

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])


@router.get("/stats", response_model=DashboardStatsResponse)
@limiter.limit("100/minute")
def dashboard_stats(
    request: Request,
    period: Literal["daily", "monthly", "all"] = Query("daily"),
    days: int = Query(30, ge=1, le=365),
    recent_limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
    api_key: ApiKey = Depends(require_api_key),
):
    now = datetime.utcnow()

    # --- summary ---
    if period == "daily":
        since_summary: Optional[datetime] = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "monthly":
        since_summary = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    else:
        since_summary = None

    base = db.query(Cost).filter(Cost.user_id == api_key.user_id)
    if since_summary:
        base = base.filter(Cost.timestamp >= since_summary)

    totals = base.with_entities(
        func.coalesce(func.sum(Cost.cost_usd), 0).label("total_cost"),
        func.count(Cost.id).label("total_calls"),
    ).one()

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

    agent_rows = (
        base.outerjoin(
            Budget,
            and_(Budget.agent_id == Cost.agent_id, Budget.user_id == api_key.user_id),
        )
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
    by_agent: List[AgentBreakdown] = [
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

    summary = CostSummaryResponse(
        agent_id=None,
        period=period,
        total_cost_usd=float(totals.total_cost),
        total_calls=totals.total_calls,
        by_model=by_model,
        by_agent=by_agent,
    )

    # --- timeseries ---
    since_ts = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days - 1)
    ts_rows = (
        db.query(
            cast(Cost.timestamp, Date).label("day"),
            func.sum(Cost.cost_usd).label("total_cost"),
        )
        .filter(Cost.user_id == api_key.user_id, Cost.timestamp >= since_ts)
        .group_by("day")
        .order_by("day")
        .all()
    )
    costs_by_date = {str(r.day): float(r.total_cost) for r in ts_rows}
    today = now.date()
    points = [
        TimeseriesPoint(
            date=str(today - timedelta(days=i)),
            cost_usd=costs_by_date.get(str(today - timedelta(days=i)), 0.0),
        )
        for i in range(days - 1, -1, -1)
    ]
    timeseries = TimeseriesResponse(period="daily", points=points)

    # --- recent ---
    recent_rows = (
        db.query(Cost)
        .filter(Cost.user_id == api_key.user_id)
        .order_by(Cost.timestamp.desc())
        .limit(recent_limit)
        .all()
    )
    recent = [
        RecentCostEntry(
            agent_id=r.agent_id,
            model=r.model,
            cost_usd=float(r.cost_usd),
            timestamp=r.timestamp,
        )
        for r in recent_rows
    ]

    return DashboardStatsResponse(summary=summary, timeseries=timeseries, recent=recent)
