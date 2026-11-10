"""Store the first local-only, prompt-only Skills catalog."""

import json

from alembic import op
import sqlalchemy as sa


revision = "0003_local_skills"
down_revision = "0002_history_cursor"
branch_labels = None
depends_on = None


_SKILLS = (
    {
        "id": "ba0d927c-67e7-4de0-b52d-79b816ea6210",
        "skill_key": "risk_review",
        "name": "风险审查",
        "description": "基于当前请求识别风险、影响和缓解办法。",
        "prompt": "对用户提供的项目或计划做风险审查。逐项说明风险、可能性、影响和可行的缓解办法；区分已有证据与假设，不补造事实。",
    },
    {
        "id": "62e5819d-4314-4cc7-a09f-2cc0d23d9858",
        "skill_key": "decision_brief",
        "name": "决策简报",
        "description": "整理已定事项、依据、备选项和待确认问题。",
        "prompt": "根据用户本轮提供的信息整理决策简报，包含事项、已确认决定、依据、备选方案和待确认问题。只复述有来源的信息；缺失项写明未知，不替用户做未授权决定。",
    },
    {
        "id": "8d017659-f423-47a5-9e71-6b84794a198a",
        "skill_key": "action_items",
        "name": "行动项整理",
        "description": "从用户提供的记录提取任务、负责人和期限。",
        "prompt": "只从用户提供的文本中提取行动项，列出任务、负责人、期限和原文依据。未明确的负责人或期限标为未知；不要声称已创建或更新任务。",
    },
)


def upgrade() -> None:
    op.create_table(
        "skills",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("skill_key", sa.String(64), nullable=False, unique=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("description", sa.String(512), nullable=False),
        sa.Column("version", sa.String(32), nullable=False),
        sa.Column("definition_json", sa.Text(), nullable=False),
        sa.Column("permission_manifest_json", sa.Text(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="ACTIVE"),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.Column("updated_at", sa.String(32), nullable=False),
        sa.CheckConstraint("status IN ('ACTIVE','PAUSED','ARCHIVED')"),
    )
    created_at = "2026-11-10T00:00:00+00:00"
    op.bulk_insert(
        sa.table(
            "skills",
            sa.column("id", sa.String),
            sa.column("skill_key", sa.String),
            sa.column("name", sa.String),
            sa.column("description", sa.String),
            sa.column("version", sa.String),
            sa.column("definition_json", sa.String),
            sa.column("permission_manifest_json", sa.String),
            sa.column("status", sa.String),
            sa.column("created_at", sa.String),
            sa.column("updated_at", sa.String),
        ),
        [
            {
                **{key: skill[key] for key in ("id", "skill_key", "name", "description")},
                "version": "1",
                "definition_json": json.dumps({"prompt": skill["prompt"]}, ensure_ascii=False),
                "permission_manifest_json": '{"tools":[],"external_write":false}',
                "status": "ACTIVE",
                "created_at": created_at,
                "updated_at": created_at,
            }
            for skill in _SKILLS
        ],
    )


def downgrade() -> None:
    op.drop_table("skills")
