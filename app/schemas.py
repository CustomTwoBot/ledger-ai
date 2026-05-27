from datetime import datetime
from typing import List, Literal, Optional
from pydantic import BaseModel, EmailStr, Field


class CostLogRequest(BaseModel):
    agent_id: str = Field(..., max_length=128)
    provider: str = Field(..., max_length=64)
    model: str = Field(..., max_length=128)
    input_tokens: int
    output_tokens: int
    request_id: str = Field(..., max_length=256)


class CostLogResponse(BaseModel):
    cost_usd: float
    daily_remaining_usd: Optional[float]
    hard_stop: bool


class ModelBreakdown(BaseModel):
    model: str = Field(..., max_length=128)
    provider: str = Field(..., max_length=64)
    call_count: int
    total_input_tokens: int
    total_output_tokens: int
    total_cost_usd: float


class AgentBreakdown(BaseModel):
    agent_id: str = Field(..., max_length=128)
    call_count: int
    total_cost_usd: float
    budget_limit: Optional[float]
    daily_spent: Optional[float]
    hard_stop: bool


class CostSummaryResponse(BaseModel):
    agent_id: Optional[str] = Field(None, max_length=128)
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
    agent_id: str = Field(..., max_length=128)
    model: str = Field(..., max_length=128)
    cost_usd: float
    timestamp: datetime


class BudgetSetRequest(BaseModel):
    agent_id: str = Field(..., max_length=128)
    daily_limit_usd: Optional[float] = None
    monthly_limit_usd: Optional[float] = None
    is_hard_stop_enabled: bool = False


class BudgetSetResponse(BaseModel):
    agent_id: str = Field(..., max_length=128)
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


class CreateKeyRequest(BaseModel):
    user_id: str = Field(..., max_length=128)


class CreateKeyResponse(BaseModel):
    key: str
    user_id: str = Field(..., max_length=128)
    created_at: datetime


class DashboardStatsResponse(BaseModel):
    summary: CostSummaryResponse
    timeseries: TimeseriesResponse
    recent: List[RecentCostEntry]


class SignupRequest(BaseModel):
    email: EmailStr


class SignupResponse(BaseModel):
    api_key: str
    email: str


class MeResponse(BaseModel):
    key: str
    email: Optional[str]
    user_id: str
    created_at: datetime
    is_active: bool
