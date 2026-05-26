from datetime import datetime
from typing import List, Literal, Optional
from pydantic import BaseModel


class CostLogRequest(BaseModel):
    agent_id: str
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    request_id: str


class CostLogResponse(BaseModel):
    cost_usd: float
    daily_remaining_usd: Optional[float]
    hard_stop: bool


class ModelBreakdown(BaseModel):
    model: str
    provider: str
    call_count: int
    total_input_tokens: int
    total_output_tokens: int
    total_cost_usd: float


class AgentBreakdown(BaseModel):
    agent_id: str
    call_count: int
    total_cost_usd: float
    budget_limit: Optional[float]
    daily_spent: Optional[float]
    hard_stop: bool


class CostSummaryResponse(BaseModel):
    agent_id: Optional[str]
    period: str
    total_cost_usd: float
    total_calls: int
    by_model: List[ModelBreakdown]
    by_agent: Optional[List[AgentBreakdown]]


class TimeseriesPoint(BaseModel):
    date: str
    cost_usd: float


class TimeseriesResponse(BaseModel):
    period: str
    points: List[TimeseriesPoint]


class RecentCostEntry(BaseModel):
    agent_id: str
    model: str
    cost_usd: float
    timestamp: datetime


class BudgetSetRequest(BaseModel):
    agent_id: str
    daily_limit_usd: Optional[float] = None
    monthly_limit_usd: Optional[float] = None
    is_hard_stop_enabled: bool = False


class BudgetSetResponse(BaseModel):
    agent_id: str
    daily_limit_usd: Optional[float]
    monthly_limit_usd: Optional[float]
    daily_spent_usd: float
    monthly_spent_usd: float
    is_hard_stop_enabled: bool


class BudgetCheckResponse(BaseModel):
    allowed: bool
    reason: Optional[str]
    daily_remaining_usd: Optional[float]
    warning: Optional[Literal["near_limit", "hard_stop"]] = None
