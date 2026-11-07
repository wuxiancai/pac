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
import pac_poc.sqlcipher_poc as sqlcipher_poc

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
        for partial in path.parent.glob(f".{path.name}.*.partial"):
            for suffix in ("", "-wal", "-shm", "-journal"):
                Path(f"{partial}{suffix}").unlink(missing_ok=True)


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


def test_wal_database_backup_restores_committed_memory_and_fts(database_paths) -> None:
    path, backup = database_paths
    database = SQLCipherFTSDatabase(path=path, key="wal-backup-source-key")
    assert database.enable_wal_for_poc() == "wal"
    database.add("WAL first committed source memory")
    database.add("WAL second committed source memory")
    try:
        database.backup_to(backup, backup_key="wal-backup-separate-key")
        assert database.search("WAL first") == ["WAL first committed source memory"]
        assert database.integrity_check() == "ok"
    finally:
        database.close()

    restored = SQLCipherFTSDatabase.open_existing(
        path=backup, key="wal-backup-separate-key"
    )
    try:
        assert restored.search("WAL first") == ["WAL first committed source memory"]
        assert restored.search("second committed") == [
            "WAL second committed source memory"
        ]
        assert restored.integrity_check() == "ok"
    finally:
        restored.close()


def test_wal_backup_includes_commit_from_concurrent_writer(database_paths) -> None:
    path, backup = database_paths
    source_key = "wal-concurrent-backup-source-key"
    backup_key = "wal-concurrent-backup-key"
    database = SQLCipherFTSDatabase(path=path, key=source_key)
    database.enable_wal_for_poc()
    try:
        for index in range(60):
            database.add(f"seed record {index} " + ("payload " * 100))

        committed_during_backup = False

        def copy_with_concurrent_writer(destination) -> None:
            nonlocal committed_during_backup

            def on_progress(_status: int, remaining: int, total: int) -> None:
                nonlocal committed_during_backup
                if committed_during_backup or not 0 < remaining < total:
                    return
                writer = SQLCipherFTSDatabase.open_existing(path=path, key=source_key)
                try:
                    writer.add("concurrent writer transaction marker")
                finally:
                    writer.close()
                committed_during_backup = True

            database._connection.backup(destination, pages=1, progress=on_progress)

        database._copy_backup_to = copy_with_concurrent_writer
        database.backup_to(backup, backup_key=backup_key)
        assert committed_during_backup
        assert database.search('"concurrent writer transaction marker"') == [
            "concurrent writer transaction marker"
        ]
        assert database.integrity_check() == "ok"

        restored = SQLCipherFTSDatabase.open_existing(path=backup, key=backup_key)
        try:
            assert restored.search('"concurrent writer transaction marker"') == [
                "concurrent writer transaction marker"
            ]
            assert restored.search('"seed record 59"') == [
                f"seed record 59 {'payload ' * 100}"
            ]
            assert restored.integrity_check() == "ok"
        finally:
            restored.close()
    finally:
        database.close()


def test_wal_backup_with_active_reader_and_repeated_writer_commits(
    database_paths,
) -> None:
    path, backup = database_paths
    source_key = "wal-reader-writer-backup-source-key"
    backup_key = "wal-reader-writer-backup-key"
    database = SQLCipherFTSDatabase(path=path, key=source_key)
    database.enable_wal_for_poc()
    reader = SQLCipherFTSDatabase.open_existing(path=path, key=source_key)
    try:
        for index in range(80):
            database.add(f"snapshot seed {index} " + ("payload " * 90))

        reader._connection.execute("BEGIN")
        assert reader.search('"snapshot seed 79"') == [
            f"snapshot seed 79 {'payload ' * 90}"
        ]
        progress_calls = 0
        writes = 0

        def copy_with_repeated_writes(destination) -> None:
            def on_progress(_status: int, remaining: int, total: int) -> None:
                nonlocal progress_calls, writes
                progress_calls += 1
                if remaining <= 0 or progress_calls % 3 != 0 or writes >= 3:
                    return
                writer = SQLCipherFTSDatabase.open_existing(path=path, key=source_key)
                try:
                    writes += 1
                    writer.add(f"concurrent writer marker {writes}")
                finally:
                    writer.close()

            database._connection.backup(destination, pages=1, progress=on_progress)

        database._copy_backup_to = copy_with_repeated_writes
        database.backup_to(backup, backup_key=backup_key)
        assert writes == 3
        assert reader.search('"snapshot seed 79"') == [
            f"snapshot seed 79 {'payload ' * 90}"
        ]
        assert reader.search('"concurrent writer marker"') == []
        for index in range(1, 4):
            assert database.search(f'"concurrent writer marker {index}"') == [
                f"concurrent writer marker {index}"
            ]
        assert database.integrity_check() == "ok"

        restored = SQLCipherFTSDatabase.open_existing(path=backup, key=backup_key)
        try:
            for index in range(1, 4):
                assert restored.search(f'"concurrent writer marker {index}"') == [
                    f"concurrent writer marker {index}"
                ]
            assert restored.search('"snapshot seed 79"') == [
                f"snapshot seed 79 {'payload ' * 90}"
            ]
            assert restored.integrity_check() == "ok"
        finally:
            restored.close()
    finally:
        reader.close()
        database.close()


def test_sigkill_during_blocked_wal_checkpoint_recovers_committed_rows(
    database_paths,
) -> None:
    path, _ = database_paths
    source_key = "wal-checkpoint-crash-source-key"
    source = SQLCipherFTSDatabase(path=path, key=source_key)
    assert source.enable_wal_for_poc() == "wal"
    source.add("checkpoint crash committed baseline")
    source.close()

    reader = SQLCipherFTSDatabase.open_existing(path=path, key=source_key)
    reader._connection.execute("BEGIN")
    assert reader.search('"checkpoint crash committed baseline"') == [
        "checkpoint crash committed baseline"
    ]
    source = SQLCipherFTSDatabase.open_existing(path=path, key=source_key)
    source.add("checkpoint crash committed during reader snapshot")
    source.close()
    assert reader.search('"committed during reader snapshot"') == []

    backend = Path(__file__).resolve().parents[1]
    process = subprocess.Popen(
        [
            sys.executable,
            "scripts/crash_sqlcipher_checkpoint_poc.py",
            str(path.resolve()),
        ],
        cwd=backend,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert process.stdin is not None
        process.stdin.write(f"{source_key}\n")
        process.stdin.flush()
        assert process.stdout is not None
        ready, _, _ = select.select([process.stdout], [], [], 15)
        assert ready, "checkpoint injector did not announce its operation"
        assert process.stdout.readline().strip() == "CHECKPOINT_BEGIN"
        with pytest.raises(subprocess.TimeoutExpired):
            process.wait(timeout=0.5)
        process.send_signal(signal.SIGKILL)
        stdout, stderr = process.communicate(timeout=10)
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate(timeout=10)
        reader.close()

    assert process.returncode == -signal.SIGKILL
    assert "CHECKPOINT_RETURNED" not in stdout + stderr
    assert source_key not in stdout + stderr

    recovered = SQLCipherFTSDatabase.open_existing(path=path, key=source_key)
    try:
        assert recovered.search('"checkpoint crash committed baseline"') == [
            "checkpoint crash committed baseline"
        ]
        assert recovered.search('"committed during reader snapshot"') == [
            "checkpoint crash committed during reader snapshot"
        ]
        assert recovered.integrity_check() == "ok"
        busy, log_frames, checkpointed_frames = recovered.checkpoint_wal_for_poc(
            "TRUNCATE"
        )
        assert busy == 0
        assert checkpointed_frames == log_frames
    finally:
        recovered.close()

    reopened = SQLCipherFTSDatabase.open_existing(path=path, key=source_key)
    try:
        assert reopened.search('"committed during reader snapshot"') == [
            "checkpoint crash committed during reader snapshot"
        ]
        assert reopened.integrity_check() == "ok"
    finally:
        reopened.close()


def test_wal_truncate_checkpoint_preserves_encrypted_memory_and_fts(database_paths) -> None:
    path, _ = database_paths
    database = SQLCipherFTSDatabase(path=path, key="wal-checkpoint-poc-key")
    assert database.enable_wal_for_poc() == "wal"
    database.add("checkpoint preserves encrypted search index")
    database.add("a second committed memory record")
    with pytest.raises(ValueError, match="unsupported WAL checkpoint mode"):
        database.checkpoint_wal_for_poc("TRUNCATE); DROP TABLE poc_memories; --")

    busy, log_frames, checkpointed_frames = database.checkpoint_wal_for_poc("TRUNCATE")

    assert busy == 0
    assert checkpointed_frames == log_frames
    assert database.search("encrypted search") == [
        "checkpoint preserves encrypted search index"
    ]
    database.close()

    reopened = SQLCipherFTSDatabase.open_existing(path=path, key="wal-checkpoint-poc-key")
    try:
        assert reopened.search("committed memory") == ["a second committed memory record"]
        assert reopened.integrity_check() == "ok"
    finally:
        reopened.close()


def test_wal_truncate_checkpoint_reports_reader_contention_and_recovers(database_paths) -> None:
    path, _ = database_paths
    database = SQLCipherFTSDatabase(path=path, key="wal-reader-checkpoint-poc-key")
    assert database.enable_wal_for_poc() == "wal"
    database.add("baseline WAL checkpoint record")

    reader = sqlcipher.connect(str(path))
    reader.execute("PRAGMA key = 'wal-reader-checkpoint-poc-key'")
    reader.execute("SELECT count(*) FROM sqlite_master").fetchone()
    reader.execute("BEGIN")
    assert reader.execute("SELECT content FROM poc_memories").fetchall()
    try:
        database.add("committed during active WAL reader")

        blocked = database.checkpoint_wal_for_poc("TRUNCATE")

        assert blocked[0] == 1
        assert blocked[1] >= blocked[2]
        assert database.search("active WAL reader") == [
            "committed during active WAL reader"
        ]
    finally:
        reader.rollback()
        reader.close()

    retried = database.checkpoint_wal_for_poc("TRUNCATE")
    assert retried[0] == 0
    assert retried[1] == retried[2]
    database.close()

    reopened = SQLCipherFTSDatabase.open_existing(
        path=path,
        key="wal-reader-checkpoint-poc-key",
    )
    try:
        assert reopened.search("baseline WAL") == ["baseline WAL checkpoint record"]
        assert reopened.search("committed during") == [
            "committed during active WAL reader"
        ]
        assert reopened.integrity_check() == "ok"
    finally:
        reopened.close()


def test_backup_target_failure_preserves_source_database(database_paths) -> None:
    path, _ = database_paths
    database = SQLCipherFTSDatabase(path=path, key="backup-failure-poc-key")
    database.add("source remains available after backup failure")
    blocked_parent = path.parent / f"{path.stem}-not-a-directory"
    blocked_parent.write_text("occupied path", encoding="utf-8")
    try:
        with pytest.raises(SQLCipherPOCError):
            database.backup_to(
                blocked_parent / "backup.db",
                backup_key="separate-backup-key",
            )

        assert database.search("source remains") == [
            "source remains available after backup failure"
        ]
        assert database.integrity_check() == "ok"
    finally:
        database.close()
        blocked_parent.unlink(missing_ok=True)


def test_failed_backup_preserves_previous_valid_backup(database_paths, monkeypatch) -> None:
    path, backup = database_paths
    database = SQLCipherFTSDatabase(path=path, key="backup-atomic-source-key")
    database.add("new source record")
    previous = SQLCipherFTSDatabase(path=backup, key="temporary-init-key")
    previous.add("previous valid backup record")
    previous.close()
    previous = SQLCipherFTSDatabase.open_existing(
        path=backup, key="temporary-init-key"
    )
    previous.close()

    def failed_copy(_destination) -> None:
        raise sqlcipher.DatabaseError("simulated backup operation I/O failure")

    monkeypatch.setattr(database, "_copy_backup_to", failed_copy, raising=False)
    try:
        with pytest.raises(SQLCipherPOCError, match="backup operation failed"):
            database.backup_to(backup, backup_key="separate-backup-key")

        preserved = SQLCipherFTSDatabase.open_existing(
            path=backup, key="temporary-init-key"
        )
        try:
            assert preserved.search("previous valid") == [
                "previous valid backup record"
            ]
            assert preserved.integrity_check() == "ok"
        finally:
            preserved.close()
        assert database.search("new source") == ["new source record"]
        assert database.integrity_check() == "ok"
        assert list(backup.parent.glob(f".{backup.name}.*.partial")) == []
    finally:
        database.close()


def test_backup_validation_failure_preserves_previous_valid_backup(
    database_paths, monkeypatch
) -> None:
    path, backup = database_paths
    database = SQLCipherFTSDatabase(path=path, key="backup-validation-source-key")
    database.add("new data awaiting backup")
    previous = SQLCipherFTSDatabase(path=backup, key="backup-validation-old-key")
    previous.add("previous backup survives validation failure")
    previous.close()

    monkeypatch.setattr(
        database,
        "_validate_staging_backup",
        lambda _path, _key: False,
        raising=False,
    )
    try:
        with pytest.raises(SQLCipherPOCError, match="backup operation failed"):
            database.backup_to(backup, backup_key="backup-validation-new-key")

        preserved = SQLCipherFTSDatabase.open_existing(
            path=backup, key="backup-validation-old-key"
        )
        try:
            assert preserved.search("previous backup survives") == [
                "previous backup survives validation failure"
            ]
            assert preserved.integrity_check() == "ok"
        finally:
            preserved.close()
        assert database.search("new data") == ["new data awaiting backup"]
        assert list(backup.parent.glob(f".{backup.name}.*.partial")) == []
    finally:
        database.close()


def test_atomic_backup_replace_failure_preserves_previous_valid_backup(
    database_paths, monkeypatch
) -> None:
    path, backup = database_paths
    database = SQLCipherFTSDatabase(path=path, key="backup-replace-source-key")
    database.add("new source before replace failure")
    previous = SQLCipherFTSDatabase(path=backup, key="backup-replace-old-key")
    previous.add("previous backup before replace failure")
    previous.close()

    def fail_replace(_source, _target) -> None:
        raise OSError("simulated atomic replace failure")

    monkeypatch.setattr(sqlcipher_poc.os, "replace", fail_replace)
    try:
        with pytest.raises(SQLCipherPOCError, match="backup operation failed"):
            database.backup_to(backup, backup_key="backup-replace-new-key")

        preserved = SQLCipherFTSDatabase.open_existing(
            path=backup, key="backup-replace-old-key"
        )
        try:
            assert preserved.search("previous backup before") == [
                "previous backup before replace failure"
            ]
            assert preserved.integrity_check() == "ok"
        finally:
            preserved.close()
        assert database.search("new source") == ["new source before replace failure"]
        assert database.integrity_check() == "ok"
        assert list(backup.parent.glob(f".{backup.name}.*.partial")) == []
    finally:
        database.close()


@pytest.mark.parametrize("journal_mode", ["DELETE", "WAL"])
def test_sigkill_during_backup_copy_preserves_previous_backup(
    database_paths, journal_mode: str
) -> None:
    source_path, backup_path = database_paths
    source = SQLCipherFTSDatabase(path=source_path, key="backup-crash-source-key")
    try:
        if journal_mode == "WAL":
            assert source.enable_wal_for_poc() == "wal"
        for index in range(80):
            source.add(f"source marker {index} " + ("payload " * 350))
    finally:
        source.close()

    old_backup = SQLCipherFTSDatabase(path=backup_path, key="old-backup-key")
    old_backup.add("previous backup marker")
    old_backup.close()

    backend = Path(__file__).resolve().parents[1]
    process = subprocess.Popen(
        [
            sys.executable,
            "scripts/crash_sqlcipher_backup_poc.py",
            str(source_path.resolve()),
            str(backup_path.resolve()),
        ],
        cwd=backend,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert process.stdin is not None
        process.stdin.write("backup-crash-source-key\nnew-backup-key\n")
        process.stdin.flush()
        assert process.stdout is not None
        ready, _, _ = select.select([process.stdout], [], [], 15)
        assert ready, "backup injector did not enter a partial backup copy"
        progress = process.stdout.readline().strip()
        assert progress.startswith("BACKUP_COPY_PROGRESS ")
        process.send_signal(signal.SIGKILL)
        stdout, stderr = process.communicate(timeout=10)
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate(timeout=10)

    assert process.returncode == -signal.SIGKILL
    assert "backup-crash-source-key" not in stdout + stderr
    assert "new-backup-key" not in stdout + stderr

    preserved = SQLCipherFTSDatabase.open_existing(
        path=backup_path, key="old-backup-key"
    )
    try:
        assert preserved.search("previous backup") == ["previous backup marker"]
        assert preserved.integrity_check() == "ok"
    finally:
        preserved.close()

    recovered_source = SQLCipherFTSDatabase.open_existing(
        path=source_path, key="backup-crash-source-key"
    )
    try:
        row = recovered_source._connection.execute("PRAGMA journal_mode").fetchone()
        assert row is not None and str(row[0]).upper() == journal_mode
        assert recovered_source.search('"source marker 79"') == [
            f"source marker 79 {'payload ' * 350}"
        ]
        assert recovered_source.integrity_check() == "ok"
    finally:
        recovered_source.close()

    partial_files = list(backup_path.parent.glob(f".{backup_path.name}.*.partial"))
    assert partial_files, "SIGKILL should leave the interrupted staging file for cleanup"
    for partial in partial_files:
        for suffix in ("", "-wal", "-shm", "-journal"):
            Path(f"{partial}{suffix}").unlink(missing_ok=True)


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
