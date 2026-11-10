"""Encrypted local application storage for conversations, tasks, and approved memories."""

from __future__ import annotations

import os
import stat
from pathlib import Path

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
