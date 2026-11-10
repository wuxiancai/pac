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
