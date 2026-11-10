"""Add metadata-only, expiring security audit events."""

from alembic import op
import sqlalchemy as sa


revision = "0005_security_audit"
down_revision = "0004_monthly_cloud_budget"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "security_audit_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("trace_id", sa.String(36), nullable=False),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("resource_id", sa.String(36), nullable=False),
        sa.Column("decision", sa.String(16), nullable=False),
        sa.Column("reason_code", sa.String(64), nullable=False),
        sa.Column("data_sensitivity", sa.String(2), nullable=False),
        sa.Column("provider_id", sa.String(32), nullable=False),
        sa.Column("model_id", sa.String(128), nullable=False),
        sa.Column("region", sa.String(32), nullable=False),
        sa.Column("purpose", sa.String(64), nullable=False),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.CheckConstraint(
            "decision IN ('ATTEMPTED','SUCCEEDED','FAILED','CANCELLED','DENIED')"
        ),
        sa.CheckConstraint("data_sensitivity IN ('L0','L1','L2')"),
    )
    op.create_index(
        "ix_security_audit_created_at",
        "security_audit_events",
        ["created_at"],
    )
    op.create_index(
        "ix_security_audit_trace_id",
        "security_audit_events",
        ["trace_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_security_audit_trace_id", table_name="security_audit_events")
    op.drop_index("ix_security_audit_created_at", table_name="security_audit_events")
    op.drop_table("security_audit_events")
