"""Encrypted local application storage for conversations, tasks, and approved memories."""

from __future__ import annotations

import json
import os
import tempfile
import stat
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import sqlcipher3.dbapi2 as sqlcipher
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine, URL

from .backup import (
    EncryptedBackupError,
    derive_backup_key,
    extract_backup_payload,
    read_backup_header,
    write_backup_container,
)


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
        self._restore_in_progress = False

    @property
    def path(self) -> Path:
        return self._path

    def open(self) -> None:
        if self._engine is not None:
            raise PersistentStoreError("database is already open")
        try:
            if not self._restore_in_progress:
                self._recover_interrupted_restore()
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

    def export_encrypted_backup(
        self, target: Path, *, password: str, replace_existing: bool = False
    ) -> dict[str, int]:
        """Create and validate a password-encrypted snapshot of the live SQLCipher store."""
        engine = self._require_engine()
        if not isinstance(target, Path) or not target.is_absolute():
            raise ValueError("backup destination must be an absolute path")
        if target.resolve(strict=False) == self._path.resolve(strict=False):
            raise ValueError("backup destination must differ from the live database")
        if target.is_symlink():
            raise ValueError("backup destination must not be a symbolic link")
        if target.exists() and not replace_existing:
            raise FileExistsError("backup destination already exists")
        salt = os.urandom(16)
        backup_key = derive_backup_key(password, salt)
        temporary_database: Path | None = None
        destination_connection = None
        source_connection = None
        try:
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=".pac-backup-db-", suffix=".sqlite", dir=self._path.parent
            )
            os.fchmod(descriptor, 0o600)
            os.close(descriptor)
            temporary_database = Path(temporary_name)
            # SQLCipher's documented raw backup API creates a snapshot while writes
            # continue. The caller's target is untouched until the copy validates.
            destination_connection = self._open_password_database(temporary_database, backup_key.hex())
            source_connection = engine.raw_connection()
            source_driver = source_connection.driver_connection
            if source_driver is None:
                raise PersistentStoreError("SQLCipher backup source is unavailable")
            source_driver.backup(destination_connection)
            destination_connection.close()
            destination_connection = None
            self._verify_password_database(temporary_database, backup_key.hex())
            # Reuse the generated salt so the validated SQLCipher key and envelope
            # header derive from the same per-backup password profile.
            write_backup_container(
                temporary_database,
                target,
                password=password,
                database_key=self._database_key_bytes(),
                salt=salt,
                replace_existing=replace_existing,
            )
            return {"bytes_written": target.stat().st_size}
        except (EncryptedBackupError, PersistentStoreError):
            raise
        except Exception:
            raise PersistentStoreError("encrypted backup could not be created") from None
        finally:
            if source_connection is not None:
                source_connection.close()
            if destination_connection is not None:
                destination_connection.close()
            if temporary_database is not None:
                for suffix in ("", "-wal", "-shm", "-journal"):
                    Path(f"{temporary_database}{suffix}").unlink(missing_ok=True)

    def connection(self):
        """Return a SQLAlchemy connection; callers own and must close it."""
        if self._engine is None:
            raise PersistentStoreError("database is not open")
        return self._engine.connect()

    def _database_key_bytes(self) -> bytes:
        return bytes.fromhex(self._key_hex)

    def restore_encrypted_backup(self, source: Path, *, password: str) -> dict[str, str]:
        """Authenticate, prebackup, stage under the local key, then swap databases."""
        engine = self._require_engine()
        if not isinstance(source, Path) or not source.is_absolute() or source.is_symlink():
            raise ValueError("backup source must be an absolute regular file")
        if not source.is_file() or source.resolve() == self._path.resolve():
            raise ValueError("backup source is unavailable")
        header, backup_key = read_backup_header(
            source, password=password, database_key=self._database_key_bytes()
        )
        prebackup = self._path.parent / "pre-restore" / (
            f"pre-restore-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
            f"-{uuid4().hex[:8]}.sqlcipher"
        )
        prebackup.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(prebackup.parent, 0o700)
        prebackup_temp: Path | None = None
        payload_temp: Path | None = None
        restored_temp: Path | None = None
        rollback_path = self._path.with_name(f".{self._path.name}.{uuid4().hex}.rollback")
        swapped = False
        try:
            prebackup_temp = self._new_private_temp(self._path.parent, ".pac-pre-restore-", ".sqlite")
            live_copy = self._open_password_database(prebackup_temp, self._key_hex)
            source_connection = engine.raw_connection()
            try:
                live_driver = source_connection.driver_connection
                if live_driver is None:
                    raise PersistentStoreError("database prebackup source is unavailable")
                live_driver.backup(live_copy)
            finally:
                live_copy.close()
                source_connection.close()
            self._verify_password_database(prebackup_temp, self._key_hex)
            os.replace(prebackup_temp, prebackup)
            prebackup_temp = None
            self._fsync_parent(prebackup.parent)

            payload_temp = self._new_private_temp(self._path.parent, ".pac-restore-payload-", ".sqlite")
            extract_backup_payload(source, payload_temp, payload_offset=header.payload_offset)
            self._verify_password_database(payload_temp, backup_key.hex())
            restored_temp = self._new_private_temp(self._path.parent, ".pac-restore-local-", ".sqlite")
            restored_target = self._open_password_database(restored_temp, self._key_hex)
            restored_source = self._open_password_database(payload_temp, backup_key.hex())
            try:
                restored_source.backup(restored_target)
            finally:
                restored_source.close()
                restored_target.close()
            self._verify_password_database(restored_temp, self._key_hex)

            with engine.connect() as connection:
                connection.exec_driver_sql("PRAGMA wal_checkpoint(FULL)")
            engine.dispose()
            self._engine = None
            for suffix in ("-wal", "-shm", "-journal"):
                Path(f"{self._path}{suffix}").unlink(missing_ok=True)
            self._restore_in_progress = True
            os.replace(self._path, rollback_path)
            os.replace(restored_temp, self._path)
            restored_temp = None
            swapped = True
            self.open()
            self._fsync_parent(self._path.parent)
            rollback_path.unlink(missing_ok=True)
            return {"prebackup_path": str(prebackup)}
        except Exception as exc:
            if self._engine is not None:
                self.close()
            if swapped:
                self._path.unlink(missing_ok=True)
            if rollback_path.exists():
                os.replace(rollback_path, self._path)
                try:
                    self.open()
                except Exception:
                    raise PersistentStoreError("restore failed and rollback could not be reopened") from None
            elif self._engine is None and self._path.exists():
                try:
                    self.open()
                except Exception:
                    raise PersistentStoreError("restore failed and the current database could not be reopened") from None
            if isinstance(exc, (ValueError, EncryptedBackupError, PersistentStoreError)):
                raise
            raise PersistentStoreError("encrypted backup could not be restored") from None
        finally:
            self._restore_in_progress = False
            for temporary in (prebackup_temp, payload_temp, restored_temp):
                if temporary is not None:
                    for suffix in ("", "-wal", "-shm", "-journal"):
                        Path(f"{temporary}{suffix}").unlink(missing_ok=True)

    def _recover_interrupted_restore(self) -> None:
        candidates = sorted(self._path.parent.glob(f".{self._path.name}.*.rollback"))
        if not candidates:
            return
        if len(candidates) != 1 or candidates[0].is_symlink() or not candidates[0].is_file():
            raise PersistentStoreError("interrupted restore recovery is ambiguous")
        rollback = candidates[0]
        for suffix in ("-wal", "-shm", "-journal"):
            Path(f"{self._path}{suffix}").unlink(missing_ok=True)
        self._path.unlink(missing_ok=True)
        try:
            os.replace(rollback, self._path)
            self._fsync_parent(self._path.parent)
        except OSError:
            raise PersistentStoreError("interrupted restore rollback could not be recovered") from None

    @staticmethod
    def _new_private_temp(directory: Path, prefix: str, suffix: str) -> Path:
        descriptor, name = tempfile.mkstemp(prefix=prefix, suffix=suffix, dir=directory)
        os.fchmod(descriptor, 0o600)
        os.close(descriptor)
        return Path(name)

    @staticmethod
    def _fsync_parent(directory: Path) -> None:
        descriptor = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    @staticmethod
    def _open_password_database(path: Path, passphrase: str):
        connection = None
        try:
            connection = sqlcipher.connect(str(path))
            escaped_passphrase = passphrase.replace("'", "''")
            connection.execute(f"PRAGMA key = '{escaped_passphrase}'")
            cipher_version = connection.execute("PRAGMA cipher_version").fetchone()
            if not cipher_version or not cipher_version[0]:
                raise PersistentStoreError("SQLCipher is unavailable for backup operations")
            connection.execute("SELECT count(*) FROM sqlite_master").fetchone()
            return connection
        except PersistentStoreError:
            if connection is not None:
                connection.close()
            raise
        except Exception as exc:
            if connection is not None:
                connection.close()
            raise PersistentStoreError("encrypted backup database could not be opened") from exc

    @classmethod
    def _verify_password_database(cls, path: Path, passphrase: str) -> None:
        connection = cls._open_password_database(path, passphrase)
        try:
            result = connection.execute("PRAGMA integrity_check").fetchone()
            if result is None or str(result[0]).lower() != "ok":
                raise PersistentStoreError("encrypted backup database integrity check failed")
            version = connection.execute("SELECT version_num FROM alembic_version").fetchone()
            if version is None or not str(version[0]):
                raise PersistentStoreError("encrypted backup schema version is missing")
        except PersistentStoreError:
            raise
        except Exception as exc:
            raise PersistentStoreError("encrypted backup database validation failed") from exc
        finally:
            connection.close()




    MEMORY_CATEGORIES = frozenset({
        "fact", "preference", "goal", "event", "decision", "commitment", "relationship", "project"
    })

    def create_confirmed_memory(
        self,
        *,
        subject: str,
        content: str,
        category: str,
        source_message_id: str | None = None,
    ) -> dict[str, object]:
        if category not in self.MEMORY_CATEGORIES:
            raise ValueError("memory category is invalid")
        if not subject.strip() or len(subject) > 512:
            raise ValueError("memory subject must contain 1 to 512 characters")
        if not content.strip() or len(content) > 20_000:
            raise ValueError("memory content must contain 1 to 20000 characters")
        engine = self._require_engine()
        now = _utc_timestamp()
        memory_id = str(uuid4())
        snapshot = {
            "subject": subject.strip(),
            "content": content.strip(),
            "category": category,
            "claim_type": "user_confirmed_fact",
            "source_message_id": source_message_id,
            "confirmed_at": now,
        }
        with engine.begin() as connection:
            if source_message_id is not None:
                source_exists = connection.execute(text(
                    "SELECT 1 FROM messages WHERE id=:id AND deleted_at IS NULL"
                ), {"id": source_message_id}).first()
                if source_exists is None:
                    raise KeyError("source message not found")
            connection.execute(text(
                "INSERT INTO memory_items(id,category,subject,content,claim_type,status,"
                "source_message_id,confirmed_at,created_at,updated_at) VALUES(:id,:category,"
                ":subject,:content,'user_confirmed_fact','ACTIVE',:source,:now,:now,:now)"
            ), {
                "id": memory_id, "category": category, "subject": subject.strip(),
                "content": content.strip(), "source": source_message_id, "now": now,
            })
            connection.execute(text(
                "INSERT INTO memory_versions(id,memory_id,version_no,snapshot_json,change_reason,created_at) "
                "VALUES(:version_id,:memory_id,1,:snapshot,'user_confirmed_create',:now)"
            ), {
                "version_id": str(uuid4()), "memory_id": memory_id,
                "snapshot": json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")),
                "now": now,
            })
            return self.get_memory(memory_id, connection=connection)

    def list_memories(self, *, limit: int = 200) -> list[dict[str, object]]:
        if not 1 <= limit <= 500:
            raise ValueError("memory limit is outside the supported range")
        engine = self._require_engine()
        with engine.connect() as connection:
            rows = connection.execute(text(
                "SELECT * FROM memory_items WHERE status='ACTIVE' AND deleted_at IS NULL "
                "ORDER BY updated_at DESC LIMIT :limit"
            ), {"limit": limit}).mappings().all()
            return [_memory_row(row) for row in rows]

    def update_confirmed_memory(
        self,
        memory_id: str,
        *,
        subject: str,
        content: str,
        category: str,
    ) -> dict[str, object]:
        if category not in self.MEMORY_CATEGORIES:
            raise ValueError("memory category is invalid")
        if not subject.strip() or len(subject) > 512:
            raise ValueError("memory subject must contain 1 to 512 characters")
        if not content.strip() or len(content) > 20_000:
            raise ValueError("memory content must contain 1 to 20000 characters")
        engine = self._require_engine()
        now = _utc_timestamp()
        with engine.begin() as connection:
            row = connection.execute(text(
                "SELECT * FROM memory_items WHERE id=:id AND status='ACTIVE' AND deleted_at IS NULL"
            ), {"id": memory_id}).mappings().first()
            if row is None:
                raise KeyError("memory not found")
            version_no = int(connection.execute(text(
                "SELECT COALESCE(MAX(version_no), 0) + 1 FROM memory_versions WHERE memory_id=:id"
            ), {"id": memory_id}).scalar_one())
            snapshot = {
                "subject": subject.strip(),
                "content": content.strip(),
                "category": category,
                "claim_type": str(row["claim_type"]),
                "source_message_id": row["source_message_id"],
                "confirmed_at": now,
            }
            connection.execute(text(
                "UPDATE memory_items SET subject=:subject, content=:content, category=:category, "
                "confirmed_at=:now, updated_at=:now WHERE id=:id"
            ), {
                "subject": subject.strip(), "content": content.strip(), "category": category,
                "now": now, "id": memory_id,
            })
            connection.execute(text(
                "INSERT INTO memory_versions(id,memory_id,version_no,snapshot_json,change_reason,created_at) "
                "VALUES(:version_id,:memory_id,:version_no,:snapshot,'user_confirmed_edit',:now)"
            ), {
                "version_id": str(uuid4()), "memory_id": memory_id, "version_no": version_no,
                "snapshot": json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")),
                "now": now,
            })
            return self.get_memory(memory_id, connection=connection)

    def get_memory(self, memory_id: str, *, connection=None) -> dict[str, object]:
        engine = self._require_engine()
        if connection is not None:
            row = connection.execute(text(
                "SELECT * FROM memory_items WHERE id=:id"
            ), {"id": memory_id}).mappings().first()
            if row is None:
                raise KeyError("memory not found")
            return _memory_row(row)
        with engine.connect() as own_connection:
            return self.get_memory(memory_id, connection=own_connection)

    def list_memory_versions(self, memory_id: str, *, limit: int = 100) -> list[dict[str, object]]:
        if not 1 <= limit <= 200:
            raise ValueError("memory version limit is invalid")
        engine = self._require_engine()
        with engine.connect() as connection:
            rows = connection.execute(text(
                "SELECT id, version_no, snapshot_json, change_reason, created_at "
                "FROM memory_versions WHERE memory_id=:id ORDER BY version_no LIMIT :limit"
            ), {"id": memory_id, "limit": limit}).mappings().all()
            return [
                {
                    "id": str(row["id"]),
                    "version_no": int(row["version_no"]),
                    "snapshot": json.loads(str(row["snapshot_json"])),
                    "change_reason": str(row["change_reason"]),
                    "created_at": str(row["created_at"]),
                }
                for row in rows
            ]

    def get_memory_source(self, memory_id: str) -> dict[str, object] | None:
        engine = self._require_engine()
        with engine.connect() as connection:
            memory = connection.execute(text(
                "SELECT source_message_id FROM memory_items "
                "WHERE id=:id AND status='ACTIVE' AND deleted_at IS NULL"
            ), {"id": memory_id}).mappings().first()
            if memory is None:
                raise KeyError("memory not found")
            if memory["source_message_id"] is None:
                return None
            row = connection.execute(text(
                "SELECT m.id, m.role, m.content, m.created_at, c.id AS conversation_id, c.title "
                "FROM messages m JOIN conversations c ON c.id=m.conversation_id "
                "WHERE m.id=:id AND m.deleted_at IS NULL AND c.deleted_at IS NULL"
            ), {"id": memory["source_message_id"]}).mappings().first()
            if row is None:
                return None
            return {
                "message_id": str(row["id"]),
                "conversation_id": str(row["conversation_id"]),
                "conversation_title": str(row["title"]),
                "role": str(row["role"]).lower(),
                "content": str(row["content"]),
                "created_at": str(row["created_at"]),
            }

    def search_memories(self, query: str, *, limit: int = 50) -> list[dict[str, object]]:
        if not query.strip() or len(query) > 256 or not 1 <= limit <= 200:
            raise ValueError("memory search query is invalid")
        # FTS syntax is intentionally restricted to quoted tokens; raw MATCH
        # operators are never passed through from user input.
        tokens = [token for token in query.split() if token]
        match_query = " AND ".join('"' + token.replace('"', '""') + '"' for token in tokens)
        engine = self._require_engine()
        with engine.connect() as connection:
            rows = connection.execute(text(
                "SELECT m.* FROM memory_items_fts f JOIN memory_items m ON m.id=f.memory_id "
                "WHERE memory_items_fts MATCH :query AND m.status='ACTIVE' AND m.deleted_at IS NULL "
                "ORDER BY rank LIMIT :limit"
            ), {"query": match_query, "limit": limit}).mappings().all()
            return [_memory_row(row) for row in rows]

    def delete_memory(self, memory_id: str) -> bool:
        engine = self._require_engine()
        with engine.begin() as connection:
            result = connection.execute(text(
                "DELETE FROM memory_items WHERE id=:id"
            ), {"id": memory_id})
            return result.rowcount > 0

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
            if status == current:
                return self.get_task(task_id, connection=connection)
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


    def list_conversations(self, *, limit: int = 100) -> list[dict[str, object]]:
        if not 1 <= limit <= 500:
            raise ValueError("conversation limit is outside the supported range")
        engine = self._require_engine()
        with engine.connect() as connection:
            rows = connection.execute(text(
                "SELECT c.id,c.title,c.created_at,c.updated_at,COUNT(m.id) AS message_count "
                "FROM conversations c LEFT JOIN messages m ON m.conversation_id=c.id "
                "AND m.deleted_at IS NULL WHERE c.status='ACTIVE' AND c.deleted_at IS NULL "
                "GROUP BY c.id ORDER BY c.updated_at DESC LIMIT :limit"
            ), {"limit": limit}).mappings().all()
            return [{
                "id": str(row["id"]),
                "title": str(row["title"]),
                "created_at": str(row["created_at"]),
                "updated_at": str(row["updated_at"]),
                "message_count": int(row["message_count"]),
            } for row in rows]

    def create_conversation(self, *, title: str = "新对话") -> dict[str, object]:
        if not title.strip() or len(title) > 256:
            raise ValueError("conversation title is invalid")
        engine = self._require_engine()
        now = _utc_timestamp()
        conversation_id = str(uuid4())
        with engine.begin() as connection:
            connection.execute(text(
                "INSERT INTO conversations(id,title,status,created_at,updated_at) "
                "VALUES(:id,:title,'ACTIVE',:now,:now)"
            ), {"id": conversation_id, "title": title.strip(), "now": now})
            return {
                "id": conversation_id, "title": title.strip(),
                "created_at": now, "updated_at": now, "message_count": 0,
            }

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

    def load_conversation(
        self, conversation_id: str | None = None, *, limit: int = 100,
        before_message_id: str | None = None,
    ) -> dict[str, object]:
        """Load one bounded page, newest first by default or older than a stable cursor."""
        if not 1 <= limit <= 200:
            raise ValueError("conversation history limit is outside the supported range")
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
            parameters: dict[str, object] = {"id": row["id"], "limit": limit + 1}
            cursor_clause = ""
            if before_message_id is None:
                order = "created_at DESC, id DESC"
            else:
                cursor = connection.execute(text(
                    "SELECT created_at FROM messages WHERE id=:cursor_id "
                    "AND conversation_id=:id AND deleted_at IS NULL"
                ), {"cursor_id": before_message_id, "id": row["id"]}).mappings().first()
                if cursor is None:
                    raise KeyError("history cursor not found")
                cursor_clause = "AND (created_at < :cursor_created OR " \
                    "(created_at = :cursor_created AND id < :cursor_id))"
                parameters.update({"cursor_created": cursor["created_at"], "cursor_id": before_message_id})
                order = "created_at DESC, id DESC"
            messages = connection.execute(text(
                "SELECT id, role, content, created_at FROM messages WHERE conversation_id=:id "
                f"AND deleted_at IS NULL {cursor_clause} ORDER BY {order} LIMIT :limit"
            ), parameters).mappings().all()
            has_more = len(messages) > limit
            messages = list(reversed(messages[:limit]))
            return {
                "id": str(row["id"]),
                "title": str(row["title"]),
                "created_at": str(row["created_at"]),
                "updated_at": str(row["updated_at"]),
                "messages": [
                    {
                        "id": str(message["id"]),
                        "role": str(message["role"]).lower(),
                        "content": str(message["content"]),
                    }
                    for message in messages
                ],
                "has_more": has_more,
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

    def rename_conversation(self, conversation_id: str, title: str) -> dict[str, object]:
        if not title.strip() or len(title) > 256:
            raise ValueError("conversation title must contain 1 to 256 characters")
        engine = self._require_engine()
        with engine.begin() as connection:
            result = connection.execute(text(
                "UPDATE conversations SET title=:title, updated_at=:now "
                "WHERE id=:id AND status='ACTIVE' AND deleted_at IS NULL"
            ), {"id": conversation_id, "title": title.strip(), "now": _utc_timestamp()})
            if result.rowcount == 0:
                raise KeyError("conversation not found")
            row = connection.execute(text(
                "SELECT id, title, created_at, updated_at FROM conversations WHERE id=:id"
            ), {"id": conversation_id}).mappings().one()
            count = connection.execute(text(
                "SELECT count(*) FROM messages WHERE conversation_id=:id AND deleted_at IS NULL"
            ), {"id": conversation_id}).scalar_one()
            return {
                "id": str(row["id"]), "title": str(row["title"]),
                "created_at": str(row["created_at"]), "updated_at": str(row["updated_at"]),
                "message_count": int(count),
            }

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


def _memory_row(row) -> dict[str, object]:
    return {
        "id": str(row["id"]),
        "category": str(row["category"]),
        "subject": str(row["subject"]),
        "content": str(row["content"]),
        "claim_type": str(row["claim_type"]),
        "status": str(row["status"]),
        "source_message_id": row["source_message_id"],
        "confirmed_at": str(row["confirmed_at"]),
        "created_at": str(row["created_at"]),
        "updated_at": str(row["updated_at"]),
    }
