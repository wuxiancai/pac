from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
import pytest

pytest.importorskip("sqlcipher3")
pytest.importorskip("sqlalchemy")
pytest.importorskip("alembic")

from pac_poc.sqlcipher_poc import (
    SQLCipherFTSDatabase,
    SQLCipherPOCError,
    create_sqlalchemy_compat_engine,
)


@pytest.fixture
def database_paths():
    root = Path(".poc-data/sqlcipher-tests")
    root.mkdir(parents=True, exist_ok=True)
    identifier = uuid4().hex
    paths = (root / f"{identifier}.db", root / f"{identifier}-backup.db")
    yield paths
    for path in paths:
        path.unlink(missing_ok=True)
        Path(f"{path}-wal").unlink(missing_ok=True)
        Path(f"{path}-shm").unlink(missing_ok=True)


def test_sqlcipher_encrypts_fts_database_and_rejects_wrong_key(database_paths) -> None:
    path, backup = database_paths
    database = SQLCipherFTSDatabase(path=path, key="poc-key-one")
    try:
        database.add("secure memory recovery rehearsal")
        assert database.search("memory recovery") == ["secure memory recovery rehearsal"]
        assert database.cipher_version
    finally:
        database.close()

    assert path.read_bytes()[:16] != b"SQLite format 3\x00"
    with pytest.raises(SQLCipherPOCError, match="key or database"):
        SQLCipherFTSDatabase.open_existing(path=path, key="wrong-key")


def test_sqlcipher_backup_restores_fts_with_separate_key(database_paths) -> None:
    path, backup = database_paths
    database = SQLCipherFTSDatabase(path=path, key="poc-key-two")
    try:
        database.add("memory sources can be restored")
        database.backup_to(backup, backup_key="separate-backup-key")
    finally:
        database.close()

    assert backup.read_bytes()[:16] != b"SQLite format 3\x00"
    with pytest.raises(SQLCipherPOCError, match="key or database"):
        SQLCipherFTSDatabase.open_existing(path=backup, key="poc-key-two")
    restored = SQLCipherFTSDatabase.open_existing(path=backup, key="separate-backup-key")
    try:
        assert restored.search("sources restored") == ["memory sources can be restored"]
    finally:
        restored.close()
    assert backup.read_bytes()[:16] != b"SQLite format 3\x00"
    with pytest.raises(SQLCipherPOCError, match="key or database"):
        SQLCipherFTSDatabase.open_existing(path=backup, key="wrong-key")


def test_sqlalchemy_and_alembic_migration_work_on_encrypted_fts_database(database_paths) -> None:
    path, _ = database_paths
    engine = create_sqlalchemy_compat_engine(path=path, key="poc-alembic-key")
    migration_dir = Path(__file__).resolve().parents[1] / "poc_migrations" / "sqlcipher_compat"
    config = Config()
    config.set_main_option("script_location", str(migration_dir))
    assert "poc-alembic-key" not in str(engine.url)
    assert engine.echo is False

    try:
        with engine.connect() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
            connection.commit()
            connection.exec_driver_sql(
                "INSERT INTO poc_records(record_id, content) VALUES (1, 'encrypted memory')"
            )
            connection.exec_driver_sql(
                "INSERT INTO poc_records_fts(record_id, content) VALUES (1, 'encrypted memory')"
            )
            connection.commit()
            result = connection.exec_driver_sql(
                "SELECT content FROM poc_records_fts WHERE poc_records_fts MATCH 'encrypted'"
            ).scalar_one()
            assert result == "encrypted memory"

            command.downgrade(config, "base")
            connection.commit()
            remaining = connection.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE name = 'poc_records'"
            ).fetchall()
            assert remaining == []
    finally:
        engine.dispose()
    assert path.read_bytes()[:16] != b"SQLite format 3\x00"
