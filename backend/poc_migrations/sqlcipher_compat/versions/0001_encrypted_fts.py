"""Create temporary FTS5 objects to exercise the SQLCipher Alembic dialect."""

from alembic import op
import sqlalchemy as sa


revision = "0001_encrypted_fts"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "poc_records",
        sa.Column("record_id", sa.Integer(), primary_key=True),
        sa.Column("content", sa.Text(), nullable=False),
    )
    op.execute(
        "CREATE VIRTUAL TABLE poc_records_fts "
        "USING fts5(record_id UNINDEXED, content)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE poc_records_fts")
    op.drop_table("poc_records")
