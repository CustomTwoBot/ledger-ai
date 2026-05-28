import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Enum, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base


class ApiKey(Base):
    __tablename__ = "api_keys"

    key = Column(String, primary_key=True, index=True)
    user_id = Column(String, nullable=False, index=True)
    email = Column(String(255), nullable=True, unique=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)


class AlertType(str, enum.Enum):
    approaching_limit = "approaching_limit"
    hard_stop = "hard_stop"
    spike = "spike"


class Cost(Base):
    __tablename__ = "costs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id = Column(String, nullable=False, index=True)
    provider = Column(String, nullable=False)
    model = Column(String, nullable=False)
    input_tokens = Column(Integer, nullable=False)
    output_tokens = Column(Integer, nullable=False)
    cost_usd = Column(Numeric(10, 6), nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    request_id = Column(String, unique=True, nullable=False, index=True)
    owner_key = Column(String, nullable=True, index=True)


class Budget(Base):
    __tablename__ = "budgets"
    __table_args__ = (UniqueConstraint("agent_id", "owner_key", name="uq_budget_agent_owner"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id = Column(String, nullable=False, index=True)
    owner_key = Column(String, nullable=True, index=True)
    daily_limit_usd = Column(Numeric(10, 2), nullable=True)
    monthly_limit_usd = Column(Numeric(10, 2), nullable=True)
    daily_spent_usd = Column(Numeric(10, 2), nullable=False, default=0)
    monthly_spent_usd = Column(Numeric(10, 2), nullable=False, default=0)
    is_hard_stop_enabled = Column(Boolean, nullable=False, default=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id = Column(String, nullable=False, index=True)
    owner_key = Column(String, nullable=True, index=True)
    alert_type = Column(Enum(AlertType), nullable=False)
    threshold_pct = Column(Integer, nullable=True)
    message = Column(Text, nullable=True)
    sent_at = Column(DateTime, default=datetime.utcnow, nullable=False)
