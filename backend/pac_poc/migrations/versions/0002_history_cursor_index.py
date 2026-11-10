"""Index ordered, keyset-paginated conversation history."""

from alembic import op


revision = "0002_history_cursor"
down_revision = "0001_product_store"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("idx_messages_conversation_created", table_name="messages")
    op.create_index("idx_messages_conversation_created_id", "messages", ["conversation_id", "created_at", "id"])


def downgrade() -> None:
    op.drop_index("idx_messages_conversation_created_id", table_name="messages")
    op.create_index("idx_messages_conversation_created", "messages", ["conversation_id", "created_at"])
