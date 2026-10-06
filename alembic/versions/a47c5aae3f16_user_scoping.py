"""user scoping

Revision ID: a47c5aae3f16
Revises: 
Create Date: 2026-10-05 11:31:01.567494

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'a47c5aae3f16'
down_revision: Union[str, Sequence[str], None] = 'd2959c3019c0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # Users table may already exist, but if not create one
    if not inspector.has_table("users"):
        op.create_table(
            "users",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("email", sa.String(255), nullable=True),
            sa.Column("github_id", sa.BigInteger, nullable=True),
            sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_users_email", "users", ["email"], unique=True)
        op.create_index("ix_users_github_id", "users", ["github_id"], unique=True)

    # Create one user per distinct old user_id, remembering the old value
    op.add_column("users", sa.Column("legacy_user_id", sa.String, nullable=True))
    op.execute("""
        INSERT INTO users (id, email, legacy_user_id, created_at)
        SELECT gen_random_uuid(),
               COALESCE(MAX(k.email), CASE WHEN k.user_id LIKE '%@%' THEN k.user_id END),
               k.user_id,
               MIN(k.created_at)
        FROM api_keys k
        GROUP BY k.user_id
    """)

    # Point api_keys at the new users (email string -> user UUID)
    op.add_column("api_keys", sa.Column("user_uuid", postgresql.UUID(as_uuid=True), nullable=True))
    op.execute("""
        UPDATE api_keys k
        SET user_uuid = u.id
        FROM users u
        WHERE u.legacy_user_id = k.user_id
    """)
    op.drop_column("api_keys", "user_id")
    op.alter_column("api_keys", "user_uuid", new_column_name="user_id", nullable=False)
    op.create_index("ix_api_keys_user_id", "api_keys", ["user_id"])
    op.create_foreign_key("fk_api_keys_user_id", "api_keys", "users", ["user_id"], ["id"])

    # Give costs, budgets and alerts a user_id, copied from the key that owns them
    for table in ("costs", "budgets", "alerts"):
        op.add_column(table, sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True))
        op.execute(f"""
            UPDATE {table} t
            SET user_id = k.user_id
            FROM api_keys k
            WHERE t.owner_key = k.key
        """)

    # Safety check: stop if any row couldn't be matched to an owner
    for table in ("costs", "budgets", "alerts"):
        orphans = bind.execute(
            sa.text(f"SELECT COUNT(*) FROM {table} WHERE user_id IS NULL")
        ).scalar()
        if orphans:
            raise RuntimeError(f"{orphans} rows in {table} have no owner; fix them before migrating")

    # Every row has an owner now, so make user_id required and link it to users
    for table in ("costs", "budgets", "alerts"):
        op.alter_column(table, "user_id", nullable=False)
        op.create_foreign_key(f"fk_{table}_user_id", table, "users", ["user_id"], ["id"])

    # Safety check: one user can't end up with two budgets for the same agent
    dupes = bind.execute(sa.text("""
        SELECT COUNT(*) FROM (
            SELECT agent_id, user_id FROM budgets
            GROUP BY agent_id, user_id
            HAVING COUNT(*) > 1
        ) d
    """)).scalar()
    if dupes:
        raise RuntimeError(f"{dupes} agents have more than one budget for the same user; merge them first")

    # Budgets: one per agent per user (was one per agent per key)
    op.execute("ALTER TABLE budgets DROP CONSTRAINT IF EXISTS uq_budget_agent_owner")
    op.execute("DROP INDEX IF EXISTS uq_budget_agent_owner")
    op.create_unique_constraint("uq_budget_agent_user", "budgets", ["agent_id", "user_id"])

    # Indexes for fast per-user lookups
    op.create_index("ix_costs_user_id_timestamp", "costs", ["user_id", "timestamp"])
    op.create_index("ix_budgets_user_id", "budgets", ["user_id"])
    op.create_index("ix_alerts_user_id", "alerts", ["user_id"])

    # The old-to-new mapping isn't needed anymore
    op.drop_column("users", "legacy_user_id")

def downgrade() -> None:
    """Downgrade schema."""
    # Undo the indexes and switch budgets back to one per agent per key
    op.drop_index("ix_alerts_user_id", table_name="alerts")
    op.drop_index("ix_budgets_user_id", table_name="budgets")
    op.drop_index("ix_costs_user_id_timestamp", table_name="costs")
    op.drop_constraint("uq_budget_agent_user", "budgets", type_="unique")
    op.create_unique_constraint("uq_budget_agent_owner", "budgets", ["agent_id", "owner_key"])

    # Remove user_id from costs, budgets and alerts (owner_key still holds the old link)
    for table in ("costs", "budgets", "alerts"):
        op.drop_constraint(f"fk_{table}_user_id", table, type_="foreignkey")
        op.drop_column(table, "user_id")

    # Turn api_keys.user_id back into a string (the user's email, or their UUID as text)
    op.add_column("api_keys", sa.Column("user_id_old", sa.String, nullable=True))
    op.execute("""
        UPDATE api_keys k
        SET user_id_old = COALESCE(u.email, u.id::text)
        FROM users u
        WHERE u.id = k.user_id
    """)
    op.drop_constraint("fk_api_keys_user_id", "api_keys", type_="foreignkey")
    op.drop_index("ix_api_keys_user_id", table_name="api_keys")
    op.drop_column("api_keys", "user_id")
    op.alter_column("api_keys", "user_id_old", new_column_name="user_id", nullable=False)
    op.create_index("ix_api_keys_user_id", "api_keys", ["user_id"])

    # Finally remove the users table
    op.drop_table("users")
