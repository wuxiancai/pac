"""Persist only aggregate estimated cloud spend for the current budget period."""

from alembic import op
import sqlalchemy as sa


revision = "0004_monthly_cloud_budget"
down_revision = "0003_local_skills"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "monthly_cloud_budget",
        sa.Column("month_key", sa.String(7), primary_key=True),
        sa.Column("estimated_micros_cny", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("request_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("price_version", sa.String(32), nullable=False),
        sa.Column("updated_at", sa.String(32), nullable=False),
        sa.CheckConstraint("estimated_micros_cny >= 0"),
        sa.CheckConstraint("request_count >= 0"),
    )
    op.create_table(
        "monthly_cloud_budget_reservations",
        sa.Column("reservation_id", sa.String(36), primary_key=True),
        sa.Column("month_key", sa.String(7), nullable=False, index=True),
        sa.Column("reserved_micros_cny", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.String(32), nullable=False),
        sa.CheckConstraint("reserved_micros_cny >= 0"),
    )


def downgrade() -> None:
    op.drop_table("monthly_cloud_budget_reservations")
    op.drop_table("monthly_cloud_budget")
