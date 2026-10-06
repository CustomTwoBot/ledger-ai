"""baseline

Revision ID: d2959c3019c0
Revises: a47c5aae3f16
Create Date: 2026-10-05 17:09:37.015775

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'd2959c3019c0'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    inspector = sa.inspect(op.get_bind())

    # Original tables, only created on a brand-new database
    if not inspector.has_table("api_keys"):
        op.create_table(
            "api_keys",
            sa.Column("key", sa.String, primary_key=True),
            sa.Column("user_id", sa.String, nullable=False),
            sa.Column("email", sa.String(255), nullable=True),
            sa.Column("created_at", sa.DateTime, nullable=False),
            sa.Column("is_active", sa.Boolean, nullable=False),
        )
        op.create_index("ix_api_keys_key", "api_keys", ["key"])
        op.create_index("ix_api_keys_user_id", "api_keys", ["user_id"])
        op.create_index("ix_api_keys_email", "api_keys", ["email"], unique=True)

    if not inspector.has_table("costs"):
        op.create_table(
            "costs",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("agent_id", sa.String, nullable=False),
            sa.Column("provider", sa.String, nullable=False),
            sa.Column("model", sa.String, nullable=False),
            sa.Column("input_tokens", sa.Integer, nullable=False),
            sa.Column("output_tokens", sa.Integer, nullable=False),
            sa.Column("cost_usd", sa.Numeric(10, 6), nullable=False),
            sa.Column("timestamp", sa.DateTime, nullable=False),
            sa.Column("request_id", sa.String, nullable=False),
            sa.Column("owner_key", sa.String, nullable=True),
        )
        op.create_index("ix_costs_agent_id", "costs", ["agent_id"])
        op.create_index("ix_costs_request_id", "costs", ["request_id"], unique=True)
        op.create_index("ix_costs_owner_key", "costs", ["owner_key"])

    if not inspector.has_table("budgets"):
        op.create_table(
            "budgets",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("agent_id", sa.String, nullable=False),
            sa.Column("owner_key", sa.String, nullable=True),
            sa.Column("daily_limit_usd", sa.Numeric(10, 2), nullable=True),
            sa.Column("monthly_limit_usd", sa.Numeric(10, 2), nullable=True),
            sa.Column("daily_spent_usd", sa.Numeric(10, 2), nullable=False),
            sa.Column("monthly_spent_usd", sa.Numeric(10, 2), nullable=False),
            sa.Column("is_hard_stop_enabled", sa.Boolean, nullable=False),
            sa.Column("updated_at", sa.DateTime, nullable=True),
            sa.UniqueConstraint("agent_id", "owner_key", name="uq_budget_agent_owner"),
        )
        op.create_index("ix_budgets_agent_id", "budgets", ["agent_id"])
        op.create_index("ix_budgets_owner_key", "budgets", ["owner_key"])

    if not inspector.has_table("alerts"):
        op.create_table(
            "alerts",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("agent_id", sa.String, nullable=False),
            sa.Column("owner_key", sa.String, nullable=True),
            sa.Column("alert_type", sa.Enum("approaching_limit", "hard_stop", "spike", name="alerttype"), nullable=False),
            sa.Column("threshold_pct", sa.Integer, nullable=True),
            sa.Column("message", sa.Text, nullable=True),
            sa.Column("sent_at", sa.DateTime, nullable=False),
        )
        op.create_index("ix_alerts_agent_id", "alerts", ["agent_id"])
        op.create_index("ix_alerts_owner_key", "alerts", ["owner_key"])


def downgrade() -> None:
    """Downgrade schema."""
    # Never delete these tables because it will delete original data
    pass
