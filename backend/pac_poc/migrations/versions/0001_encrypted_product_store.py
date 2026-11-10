"""Create encrypted conversation, task, and user-approved memory storage."""

from alembic import op
import sqlalchemy as sa


revision = "0001_product_store"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "conversations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("title", sa.String(256), nullable=False, server_default="新对话"),
        sa.Column("status", sa.String(16), nullable=False, server_default="ACTIVE"),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.Column("updated_at", sa.String(32), nullable=False),
        sa.Column("deleted_at", sa.String(32)),
        sa.CheckConstraint("status IN ('ACTIVE','ARCHIVED','DELETING','DELETED')"),
    )
    op.create_index("idx_conversations_status_updated", "conversations", ["status", "updated_at"])

    op.create_table(
        "conversation_turns",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("conversation_id", sa.String(36), sa.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sequence_no", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("trace_id", sa.String(36), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False, unique=True),
        sa.Column("model_provider_id", sa.String(64)),
        sa.Column("model_id", sa.String(128)),
        sa.Column("error_code", sa.String(64)),
        sa.Column("error_message_safe", sa.String(512)),
        sa.Column("started_at", sa.String(32)),
        sa.Column("completed_at", sa.String(32)),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.Column("updated_at", sa.String(32), nullable=False),
        sa.CheckConstraint("sequence_no > 0"),
        sa.CheckConstraint("status IN ('RECEIVED','CONTEXT_BUILDING','GENERATING','TOOL_PENDING','SPEAKING','COMPLETED','FAILED','INTERRUPTED','CANCELLED')"),
        sa.UniqueConstraint("conversation_id", "sequence_no", name="uq_turn_conversation_sequence"),
    )
    op.create_index("idx_turns_conversation_created", "conversation_turns", ["conversation_id", "created_at"])
    op.create_index("idx_turns_status", "conversation_turns", ["status"])

    op.create_table(
        "messages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("conversation_id", sa.String(36), sa.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("turn_id", sa.String(36), sa.ForeignKey("conversation_turns.id", ondelete="SET NULL")),
        sa.Column("role", sa.String(12), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_format", sa.String(12), nullable=False, server_default="TEXT"),
        sa.Column("is_final", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sensitivity", sa.String(2), nullable=False, server_default="L1"),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.Column("deleted_at", sa.String(32)),
        sa.CheckConstraint("role IN ('SYSTEM','USER','ASSISTANT','TOOL')"),
        sa.CheckConstraint("content_format IN ('TEXT','MARKDOWN','JSON','TRANSCRIPT')"),
        sa.CheckConstraint("sensitivity IN ('L0','L1','L2','L3')"),
    )
    op.create_index("idx_messages_conversation_created", "messages", ["conversation_id", "created_at"])
    op.create_index("idx_messages_turn", "messages", ["turn_id"])
    op.execute("CREATE VIRTUAL TABLE messages_fts USING fts5(message_id UNINDEXED, content, tokenize='unicode61')")
    op.execute("""
        CREATE TRIGGER messages_fts_insert AFTER INSERT ON messages
        WHEN NEW.deleted_at IS NULL BEGIN
            INSERT INTO messages_fts(message_id, content) VALUES (NEW.id, NEW.content);
        END
    """)
    op.execute("""
        CREATE TRIGGER messages_fts_delete AFTER DELETE ON messages BEGIN
            DELETE FROM messages_fts WHERE message_id = OLD.id;
        END
    """)
    op.execute("""
        CREATE TRIGGER messages_fts_update AFTER UPDATE OF content, deleted_at ON messages BEGIN
            DELETE FROM messages_fts WHERE message_id = OLD.id;
            INSERT INTO messages_fts(message_id, content)
            SELECT NEW.id, NEW.content WHERE NEW.deleted_at IS NULL;
        END
    """)

    op.create_table(
        "tasks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(16), nullable=False, server_default="PENDING"),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("schedule_at", sa.String(32)),
        sa.Column("started_at", sa.String(32)),
        sa.Column("completed_at", sa.String(32)),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("idempotency_key", sa.String(128), nullable=False, unique=True),
        sa.Column("payload_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("result_json", sa.Text()),
        sa.Column("error_code", sa.String(64)),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.Column("updated_at", sa.String(32), nullable=False),
        sa.CheckConstraint("status IN ('PENDING','READY','RUNNING','WAITING','PAUSED','PARTIAL','COMPLETED','FAILED','CANCELLED')"),
        sa.CheckConstraint("priority BETWEEN 0 AND 5"),
        sa.CheckConstraint("retry_count >= 0"),
    )
    op.create_index("idx_tasks_status_updated", "tasks", ["status", "updated_at"])
    op.create_index("idx_tasks_completed_at", "tasks", ["completed_at"])

    op.create_table(
        "memory_items",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("category", sa.String(24), nullable=False),
        sa.Column("subject", sa.String(512), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("claim_type", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="ACTIVE"),
        sa.Column("source_message_id", sa.String(36), sa.ForeignKey("messages.id", ondelete="SET NULL")),
        sa.Column("confirmed_at", sa.String(32), nullable=False),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.Column("updated_at", sa.String(32), nullable=False),
        sa.Column("deleted_at", sa.String(32)),
        sa.CheckConstraint("category IN ('fact','preference','goal','event','decision','commitment','relationship','project')"),
        sa.CheckConstraint("claim_type IN ('user_confirmed_fact','user_preference','event_record')"),
        sa.CheckConstraint("status IN ('ACTIVE','SUPERSEDED','ARCHIVED','DELETED')"),
    )
    op.create_index("idx_memory_status_category", "memory_items", ["status", "category"])
    op.create_index("idx_memory_subject", "memory_items", ["subject"])
    op.execute("CREATE VIRTUAL TABLE memory_items_fts USING fts5(memory_id UNINDEXED, subject, content, tokenize='unicode61')")
    op.execute("""
        CREATE TRIGGER memory_fts_insert AFTER INSERT ON memory_items
        WHEN NEW.status = 'ACTIVE' AND NEW.deleted_at IS NULL BEGIN
            INSERT INTO memory_items_fts(memory_id, subject, content)
            VALUES (NEW.id, NEW.subject, NEW.content);
        END
    """)
    op.execute("""
        CREATE TRIGGER memory_fts_delete AFTER DELETE ON memory_items BEGIN
            DELETE FROM memory_items_fts WHERE memory_id = OLD.id;
        END
    """)
    op.execute("""
        CREATE TRIGGER memory_fts_update AFTER UPDATE OF subject, content, status, deleted_at ON memory_items BEGIN
            DELETE FROM memory_items_fts WHERE memory_id = OLD.id;
            INSERT INTO memory_items_fts(memory_id, subject, content)
            SELECT NEW.id, NEW.subject, NEW.content
            WHERE NEW.status = 'ACTIVE' AND NEW.deleted_at IS NULL;
        END
    """)
    op.create_table(
        "memory_versions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("memory_id", sa.String(36), sa.ForeignKey("memory_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("snapshot_json", sa.Text(), nullable=False),
        sa.Column("change_reason", sa.String(256), nullable=False),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.CheckConstraint("version_no > 0"),
        sa.UniqueConstraint("memory_id", "version_no", name="uq_memory_version"),
    )


def downgrade() -> None:
    op.drop_table("memory_versions")
    op.execute("DROP TRIGGER IF EXISTS memory_fts_update")
    op.execute("DROP TRIGGER IF EXISTS memory_fts_delete")
    op.execute("DROP TRIGGER IF EXISTS memory_fts_insert")
    op.execute("DROP TABLE IF EXISTS memory_items_fts")
    op.drop_index("idx_memory_subject", table_name="memory_items")
    op.drop_index("idx_memory_status_category", table_name="memory_items")
    op.drop_table("memory_items")
    op.drop_index("idx_tasks_completed_at", table_name="tasks")
    op.drop_index("idx_tasks_status_updated", table_name="tasks")
    op.drop_table("tasks")
    op.execute("DROP TRIGGER IF EXISTS messages_fts_update")
    op.execute("DROP TRIGGER IF EXISTS messages_fts_delete")
    op.execute("DROP TRIGGER IF EXISTS messages_fts_insert")
    op.execute("DROP TABLE IF EXISTS messages_fts")
    op.drop_index("idx_messages_turn", table_name="messages")
    op.drop_index("idx_messages_conversation_created", table_name="messages")
    op.drop_table("messages")
    op.drop_index("idx_turns_status", table_name="conversation_turns")
    op.drop_index("idx_turns_conversation_created", table_name="conversation_turns")
    op.drop_table("conversation_turns")
    op.drop_index("idx_conversations_status_updated", table_name="conversations")
    op.drop_table("conversations")
