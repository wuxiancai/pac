from __future__ import annotations

import select
import signal
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
import pytest
import sqlcipher3.dbapi2 as sqlcipher

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
        Path(f"{path}-journal").unlink(missing_ok=True)


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


def test_process_crash_mid_transaction_preserves_committed_data(database_paths) -> None:
    path, _ = database_paths
    database = SQLCipherFTSDatabase(path=path, key="crash-poc-key")
    database.add("committed baseline memory")
    database.close()

    backend = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "scripts/crash_sqlcipher_poc.py", str(path.resolve())],
        cwd=backend,
        input="crash-poc-key\n",
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )

    assert result.returncode == 73
    assert result.stdout == ""
    assert "crash-poc-key" not in result.stderr

    recovered = SQLCipherFTSDatabase.open_existing(path=path, key="crash-poc-key")
    try:
        assert recovered.search("baseline memory") == ["committed baseline memory"]
        assert recovered.search("uncommitted crash marker") == []
        assert recovered.integrity_check() == "ok"
    finally:
        recovered.close()


@pytest.mark.parametrize("journal_mode", ["delete", "wal"])
def test_sigkill_mid_transaction_recovers_committed_data(database_paths, journal_mode: str) -> None:
    path, _ = database_paths
    database = SQLCipherFTSDatabase(path=path, key="sigkill-poc-key")
    database.add("committed before forced termination")
    database.close()

    backend = Path(__file__).resolve().parents[1]
    process = subprocess.Popen(
        [
            sys.executable,
            "scripts/crash_sqlcipher_poc.py",
            str(path.resolve()),
            "--wait-for-kill",
            "--wal" if journal_mode == "wal" else "--delete-journal",
        ],
        cwd=backend,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert process.stdin is not None
        process.stdin.write("sigkill-poc-key\n")
        process.stdin.flush()
        assert process.stdout is not None
        ready, _, _ = select.select([process.stdout], [], [], 10)
        assert ready, "crash injector did not reach the uncommitted transaction"
        assert process.stdout.readline() == "READY\n"
        process.send_signal(signal.SIGKILL)
        stdout, stderr = process.communicate(timeout=10)
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate(timeout=10)

    assert process.returncode == -signal.SIGKILL
    assert "sigkill-poc-key" not in stdout + stderr

    recovered = SQLCipherFTSDatabase.open_existing(path=path, key="sigkill-poc-key")
    try:
        assert recovered.search("forced termination") == [
            "committed before forced termination"
        ]
        assert recovered.search("uncommitted crash marker") == []
        assert recovered.integrity_check() == "ok"
    finally:
        recovered.close()


def test_disk_full_rolls_back_new_memory_and_preserves_existing_fts(database_paths) -> None:
    path, _ = database_paths
    database = SQLCipherFTSDatabase(path=path, key="disk-full-poc-key")
    try:
        database.add("committed prior record")
        current_pages = database.page_count
        database.set_max_page_count_for_poc(current_pages + 1)

        with pytest.raises(sqlcipher.DatabaseError):
            database.add("diskfullmarker " * 20000)

        assert database.search("prior record") == ["committed prior record"]
        assert database.search("diskfullmarker") == []
        assert database.integrity_check() == "ok"
    finally:
        database.close()
