"""Encrypted local application storage for conversations, tasks, and approved memories."""

from __future__ import annotations

import os
import stat
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import sqlcipher3.dbapi2 as sqlcipher
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine, URL


APP_DATA_DIRECTORY_NAME = "PersonalAI"
DATABASE_FILENAME = "personal-assistant.db"
DATABASE_KEY_BYTES = 32
DATABASE_BUSY_TIMEOUT_MS = 5_000


class PersistentStoreError(RuntimeError):
    """Safe persistence error; never includes paths, key material, or SQL values."""


def default_database_path(home: Path | None = None) -> Path:
    """Return the fixed macOS Application Support database location."""
    base = home if home is not None else Path.home()
    return base / "Library" / "Application Support" / APP_DATA_DIRECTORY_NAME / DATABASE_FILENAME


class EncryptedApplicationStore:
    """Own a SQLCipher engine and apply the packaged product migrations."""

    def __init__(self, *, path: Path, key: bytes) -> None:
        if not isinstance(key, bytes) or len(key) != DATABASE_KEY_BYTES:
            raise ValueError("database key must contain exactly 32 random bytes")
        if not isinstance(path, Path) or not path.is_absolute():
            raise ValueError("database path must be absolute")
        self._path = path
        self._key_hex = key.hex()
        self._engine: Engine | None = None

    @property
    def path(self) -> Path:
        return self._path

    def open(self) -> None:
        if self._engine is not None:
            raise PersistentStoreError("database is already open")
        try:
            self._prepare_private_file()
            url = URL.create(
                "sqlite+pysqlcipher",
                password=self._key_hex,
                database=str(self._path),
            )
            engine = create_engine(url, module=sqlcipher, echo=False, pool_pre_ping=True)
            event.listen(engine, "connect", self._configure_connection)
            with engine.connect() as connection:
                cipher_status = connection.execute(text("PRAGMA cipher_status")).scalar_one_or_none()
                if str(cipher_status) != "1":
                    raise PersistentStoreError("encrypted database verification failed")
                journal_mode = connection.execute(text("PRAGMA journal_mode = WAL")).scalar_one()
                if str(journal_mode).lower() != "wal":
                    raise PersistentStoreError("encrypted database WAL mode is unavailable")
                connection.commit()
                self._run_migrations(connection)
            self._engine = engine
        except PersistentStoreError:
            if "engine" in locals():
                engine.dispose()
            raise
        except Exception:
            if "engine" in locals():
                engine.dispose()
            raise PersistentStoreError("unable to open encrypted application database") from None

    def close(self) -> None:
        engine = self._engine
        self._engine = None
        if engine is not None:
            engine.dispose()

    def connection(self):
        """Return a SQLAlchemy connection; callers own and must close it."""
        if self._engine is None:
            raise PersistentStoreError("database is not open")
        return self._engine.connect()



    TASK_TRANSITIONS = {
        "PENDING": {"READY", "CANCELLED"},
        "READY": {"RUNNING", "PAUSED", "CANCELLED"},
        "RUNNING": {"WAITING", "PARTIAL", "COMPLETED", "FAILED", "CANCELLED"},
        "WAITING": {"READY", "RUNNING", "PAUSED", "CANCELLED"},
        "PAUSED": {"READY", "CANCELLED"},
        "PARTIAL": {"READY", "COMPLETED", "FAILED", "CANCELLED"},
        "FAILED": {"READY", "CANCELLED"},
        "COMPLETED": set(),
        "CANCELLED": set(),
    }
    TASK_STATUSES = frozenset(TASK_TRANSITIONS)

    def create_task(
        self,
        *,
        title: str,
        description: str = "",
        priority: int = 0,
        schedule_at: str | None = None,
        idempotency_key: str,
    ) -> dict[str, object]:
        if not title.strip() or len(title) > 512:
            raise ValueError("task title must contain 1 to 512 characters")
        if len(description) > 20_000:
            raise ValueError("task description is too long")
        if isinstance(priority, bool) or not 0 <= priority <= 5:
            raise ValueError("task priority must be between 0 and 5")
        if not idempotency_key or len(idempotency_key) > 128:
            raise ValueError("task idempotency key is invalid")
        engine = self._require_engine()
        now = _utc_timestamp()
        task_id = str(uuid4())
        with engine.begin() as connection:
            existing = connection.execute(text(
                "SELECT id FROM tasks WHERE idempotency_key=:key"
            ), {"key": idempotency_key}).scalar_one_or_none()
            if existing:
                return self.get_task(str(existing), connection=connection)
            connection.execute(text(
                "INSERT INTO tasks(id,title,description,status,priority,schedule_at,retry_count,"
                "idempotency_key,created_at,updated_at) VALUES(:id,:title,:description,'PENDING',"
                ":priority,:schedule,0,:key,:now,:now)"
            ), {
                "id": task_id, "title": title.strip(), "description": description,
                "priority": priority, "schedule": schedule_at, "key": idempotency_key, "now": now,
            })
            return self.get_task(task_id, connection=connection)

    def list_tasks(self, *, include_completed: bool = True, limit: int = 100) -> list[dict[str, object]]:
        if not 1 <= limit <= 500:
            raise ValueError("task limit is outside the supported range")
        engine = self._require_engine()
        where = "" if include_completed else "WHERE status NOT IN ('COMPLETED','CANCELLED')"
        with engine.connect() as connection:
            rows = connection.execute(text(
                f"SELECT * FROM tasks {where} ORDER BY "
                "CASE status WHEN 'RUNNING' THEN 0 WHEN 'READY' THEN 1 WHEN 'PENDING' THEN 2 ELSE 3 END, "
                "priority DESC, updated_at DESC LIMIT :limit"
            ), {"limit": limit}).mappings().all()
            return [_task_row(row) for row in rows]

    def get_task(self, task_id: str, *, connection=None) -> dict[str, object]:
        engine = self._require_engine()
        if connection is not None:
            row = connection.execute(text("SELECT * FROM tasks WHERE id=:id"), {"id": task_id}).mappings().first()
            if row is None:
                raise KeyError("task not found")
            return _task_row(row)
        with engine.connect() as own_connection:
            return self.get_task(task_id, connection=own_connection)

    def transition_task(self, task_id: str, status: str, *, error_code: str | None = None) -> dict[str, object]:
        if status not in self.TASK_STATUSES:
            raise ValueError("unknown task status")
        engine = self._require_engine()
        now = _utc_timestamp()
        with engine.begin() as connection:
            row = connection.execute(text("SELECT * FROM tasks WHERE id=:id"), {"id": task_id}).mappings().first()
            if row is None:
                raise KeyError("task not found")
            current = str(row["status"])
            if status != current and status not in self.TASK_TRANSITIONS[current]:
                raise ValueError("task status transition is not allowed")
            started_at = row["started_at"] or (now if status == "RUNNING" else None)
            completed_at = now if status == "COMPLETED" else None
            connection.execute(text(
                "UPDATE tasks SET status=:status, started_at=:started, completed_at=:completed, "
                "error_code=:error, updated_at=:now WHERE id=:id"
            ), {
                "id": task_id, "status": status, "started": started_at,
                "completed": completed_at, "error": error_code, "now": now,
            })
            return self.get_task(task_id, connection=connection)

    def delete_task(self, task_id: str) -> bool:
        engine = self._require_engine()
        with engine.begin() as connection:
            result = connection.execute(text("DELETE FROM tasks WHERE id=:id"), {"id": task_id})
            return result.rowcount > 0

    def purge_expired_completed_tasks(self, *, now: datetime | None = None) -> int:
        """Delete completed tasks after the user's selected 30-day retention."""
        cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=30)
        engine = self._require_engine()
        with engine.begin() as connection:
            result = connection.execute(text(
                "DELETE FROM tasks WHERE status='COMPLETED' AND completed_at IS NOT NULL "
                "AND completed_at <= :cutoff"
            ), {"cutoff": cutoff.isoformat()})
            return int(result.rowcount or 0)

    def get_or_create_default_conversation(self) -> dict[str, str]:
        """Return the single Beta chat, creating it on first use."""
        engine = self._require_engine()
        now = _utc_timestamp()
        with engine.begin() as connection:
            row = connection.execute(text(
                "SELECT id, title, created_at, updated_at FROM conversations "
                "WHERE status = 'ACTIVE' AND deleted_at IS NULL ORDER BY updated_at DESC LIMIT 1"
            )).mappings().first()
            if row is None:
                conversation_id = str(uuid4())
                connection.execute(text(
                    "INSERT INTO conversations(id, title, status, created_at, updated_at) "
                    "VALUES (:id, '新对话', 'ACTIVE', :now, :now)"
                ), {"id": conversation_id, "now": now})
                return {"id": conversation_id, "title": "新对话", "created_at": now, "updated_at": now}
            return {key: str(row[key]) for key in ("id", "title", "created_at", "updated_at")}

    def load_conversation(self, conversation_id: str | None = None) -> dict[str, object]:
        """Load the active conversation and ordered visible messages."""
        engine = self._require_engine()
        with engine.begin() as connection:
            if conversation_id is None:
                row = connection.execute(text(
                    "SELECT id, title, created_at, updated_at FROM conversations "
                    "WHERE status = 'ACTIVE' AND deleted_at IS NULL ORDER BY updated_at DESC LIMIT 1"
                )).mappings().first()
                if row is None:
                    new_id = str(uuid4())
                    now = _utc_timestamp()
                    connection.execute(text(
                        "INSERT INTO conversations(id, title, status, created_at, updated_at) "
                        "VALUES (:id, '新对话', 'ACTIVE', :now, :now)"
                    ), {"id": new_id, "now": now})
                    row = connection.execute(text(
                        "SELECT id, title, created_at, updated_at FROM conversations WHERE id=:id"
                    ), {"id": new_id}).mappings().one()
            else:
                row = connection.execute(text(
                    "SELECT id, title, created_at, updated_at FROM conversations "
                    "WHERE id=:id AND status='ACTIVE' AND deleted_at IS NULL"
                ), {"id": conversation_id}).mappings().first()
            if row is None:
                raise KeyError("conversation not found")
            messages = connection.execute(text(
                "SELECT role, content FROM messages WHERE conversation_id=:id "
                "AND deleted_at IS NULL ORDER BY created_at, id"
            ), {"id": row["id"]}).mappings().all()
            return {
                "id": str(row["id"]),
                "title": str(row["title"]),
                "created_at": str(row["created_at"]),
                "updated_at": str(row["updated_at"]),
                "messages": [
                    {"role": str(message["role"]).lower(), "content": str(message["content"])}
                    for message in messages
                ],
            }

    def append_chat_turn(
        self,
        *,
        conversation_id: str,
        run_id: str,
        user_content: str,
        assistant_content: str,
        provider: str,
        model: str,
        status: str,
    ) -> None:
        """Atomically persist the submitted user turn and any generated response."""
        if status not in {"COMPLETED", "FAILED", "CANCELLED"}:
            raise ValueError("unsupported persisted turn status")
        if not user_content:
            raise ValueError("a persisted chat turn requires a user message")
        engine = self._require_engine()
        now = _utc_timestamp()
        turn_id = str(uuid4())
        with engine.begin() as connection:
            conversation = connection.execute(text(
                "SELECT title FROM conversations WHERE id=:id AND status='ACTIVE' AND deleted_at IS NULL"
            ), {"id": conversation_id}).mappings().first()
            if conversation is None:
                raise KeyError("conversation not found")
            existing = connection.execute(text(
                "SELECT 1 FROM conversation_turns WHERE idempotency_key=:run_id"
            ), {"run_id": run_id}).first()
            if existing is not None:
                return
            sequence = int(connection.execute(text(
                "SELECT COALESCE(MAX(sequence_no), 0) + 1 FROM conversation_turns "
                "WHERE conversation_id=:id"
            ), {"id": conversation_id}).scalar_one())
            connection.execute(text(
                "INSERT INTO conversation_turns "
                "(id, conversation_id, sequence_no, status, trace_id, idempotency_key, "
                "model_provider_id, model_id, started_at, completed_at, created_at, updated_at) "
                "VALUES (:id, :conversation, :sequence, :status, :run_id, :run_id, :provider, :model, "
                ":now, :completed, :now, :now)"
            ), {
                "id": turn_id, "conversation": conversation_id, "sequence": sequence,
                "status": status, "run_id": run_id, "provider": provider,
                "model": model, "now": now, "completed": now if status == "COMPLETED" else None,
            })
            contents = [("USER", user_content, True)]
            if assistant_content:
                contents.append(("ASSISTANT", assistant_content, status == "COMPLETED"))
            for index, (role, content, is_final) in enumerate(contents):
                created_at = (datetime.now(timezone.utc) + timedelta(microseconds=index)).isoformat()
                connection.execute(text(
                    "INSERT INTO messages "
                    "(id, conversation_id, turn_id, role, content, is_final, sensitivity, created_at) "
                    "VALUES (:id, :conversation, :turn, :role, :content, :is_final, 'L1', :created)"
                ), {
                    "id": str(uuid4()), "conversation": conversation_id, "turn": turn_id,
                    "role": role, "content": content, "is_final": is_final, "created": created_at,
                })
            new_title = str(conversation["title"])
            if new_title == "新对话":
                new_title = user_content.strip().replace("\n", " ")[:256] or "新对话"
            connection.execute(text(
                "UPDATE conversations SET title=:title, updated_at=:now WHERE id=:id"
            ), {"title": new_title, "now": now, "id": conversation_id})

    def delete_conversation(self, conversation_id: str) -> bool:
        """Permanently delete a conversation and its dependent rows."""
        engine = self._require_engine()
        with engine.begin() as connection:
            result = connection.execute(text(
                "DELETE FROM conversations WHERE id=:id"
            ), {"id": conversation_id})
            return result.rowcount > 0

    def _require_engine(self) -> Engine:
        if self._engine is None:
            raise PersistentStoreError("database is not open")
        return self._engine

    def _prepare_private_file(self) -> None:
        parent = self._path.parent
        parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        parent_stat = parent.lstat()
        if stat.S_ISLNK(parent_stat.st_mode) or not stat.S_ISDIR(parent_stat.st_mode):
            raise PersistentStoreError("database directory must be a private directory")
        if parent_stat.st_uid != os.getuid():
            raise PersistentStoreError("database directory must be owned by the current user")
        os.chmod(parent, 0o700)

        try:
            descriptor = os.open(
                self._path,
                os.O_CREAT | os.O_EXCL | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0),
                0o600,
            )
        except FileExistsError:
            existing_stat = self._path.lstat()
            if (
                stat.S_ISLNK(existing_stat.st_mode)
                or not stat.S_ISREG(existing_stat.st_mode)
                or existing_stat.st_uid != os.getuid()
            ):
                raise PersistentStoreError("database file must be owned by the current user")
            os.chmod(self._path, 0o600)
        else:
            os.close(descriptor)

    @staticmethod
    def _configure_connection(connection, _record) -> None:
        """Set per-connection safety limits after SQLCipher's dialect applies the key."""
        cursor = connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys = ON")
            cursor.execute(f"PRAGMA busy_timeout = {DATABASE_BUSY_TIMEOUT_MS}")
        finally:
            cursor.close()

    @staticmethod
    def _run_migrations(connection) -> None:
        migration_directory = Path(__file__).parent / "migrations"
        config = Config()
        config.set_main_option("script_location", str(migration_directory))
        config.attributes["connection"] = connection
        command.upgrade(config, "head")


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _task_row(row) -> dict[str, object]:
    return {
        "id": str(row["id"]),
        "title": str(row["title"]),
        "description": str(row["description"]),
        "status": str(row["status"]),
        "priority": int(row["priority"]),
        "schedule_at": row["schedule_at"],
        "started_at": row["started_at"],
        "completed_at": row["completed_at"],
        "retry_count": int(row["retry_count"]),
        "error_code": row["error_code"],
        "created_at": str(row["created_at"]),
        "updated_at": str(row["updated_at"]),
    }
