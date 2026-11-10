from __future__ import annotations

import shutil
import sqlite3
import stat
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import text

from pac_poc.persistence import (
    DATABASE_KEY_BYTES,
    EncryptedApplicationStore,
    PersistentStoreError,
    default_database_path,
)


@pytest.fixture
def storage_root() -> Path:
    root = Path(".poc-data/product-store-tests") / str(uuid4())
    yield root
    shutil.rmtree(root, ignore_errors=True)


def _store(path: Path, key: bytes | None = None) -> EncryptedApplicationStore:
    return EncryptedApplicationStore(path=path, key=key or b"p" * DATABASE_KEY_BYTES)


def test_default_database_path_uses_private_application_support_directory() -> None:
    path = default_database_path(Path("/Users/example"))
    assert path == Path(
        "/Users/example/Library/Application Support/PersonalAI/personal-assistant.db"
    )


def test_store_creates_encrypted_private_database_and_migrates_core_tables(
    storage_root: Path,
) -> None:
    path = (storage_root / "store.db").resolve()
    store = _store(path)
    store.open()
    try:
        assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
        assert path.read_bytes()[:16] != b"SQLite format 3\x00"
        with store.connection() as connection:
            assert str(connection.execute(text("PRAGMA cipher_status")).scalar_one()) == "1"
            assert connection.execute(text("PRAGMA foreign_keys")).scalar_one() == 1
            assert connection.execute(text("PRAGMA journal_mode")).scalar_one() == "wal"
            tables = {
                row[0]
                for row in connection.execute(
                    text("SELECT name FROM sqlite_master WHERE type='table'")
                )
            }
            assert {
                "alembic_version",
                "conversations",
                "conversation_turns",
                "messages",
                "messages_fts",
                "tasks",
                "memory_items",
                "memory_items_fts",
                "memory_versions",
            } <= tables
    finally:
        store.close()


def test_message_fts_stays_in_sync_and_conversation_delete_cascades(
    storage_root: Path,
) -> None:
    store = _store((storage_root / "store.db").resolve())
    store.open()
    conversation_id = str(uuid4())
    message_id = str(uuid4())
    timestamp = "2026-11-10T00:00:00Z"
    try:
        with store.connection() as connection, connection.begin():
            connection.execute(
                text("INSERT INTO conversations(id, created_at, updated_at) VALUES (:id, :ts, :ts)"),
                {"id": conversation_id, "ts": timestamp},
            )
            connection.execute(
                text(
                    "INSERT INTO messages(id, conversation_id, role, content, created_at) "
                    "VALUES (:id, :conversation, 'USER', :content, :ts)"
                ),
                {
                    "id": message_id,
                    "conversation": conversation_id,
                    "content": "Project persistence sample",
                    "ts": timestamp,
                },
            )
            assert connection.execute(
                text("SELECT count(*) FROM messages_fts WHERE messages_fts MATCH 'persistence'")
            ).scalar_one() == 1

            connection.execute(
                text("UPDATE messages SET deleted_at=:ts WHERE id=:id"),
                {"id": message_id, "ts": timestamp},
            )
            assert connection.execute(
                text("SELECT count(*) FROM messages_fts WHERE messages_fts MATCH 'persistence'")
            ).scalar_one() == 0

            connection.execute(text("DELETE FROM conversations WHERE id=:id"), {"id": conversation_id})
            assert connection.execute(text("SELECT count(*) FROM messages WHERE id=:id"), {"id": message_id}).scalar_one() == 0
    finally:
        store.close()


def test_memory_fts_contains_only_active_non_deleted_confirmed_items(
    storage_root: Path,
) -> None:
    store = _store((storage_root / "store.db").resolve())
    store.open()
    timestamp = "2026-11-10T00:00:00Z"
    try:
        with store.connection() as connection, connection.begin():
            for memory_id, status, deleted_at in (
                (str(uuid4()), "ACTIVE", None),
                (str(uuid4()), "ARCHIVED", None),
                (str(uuid4()), "ACTIVE", timestamp),
            ):
                connection.execute(
                    text(
                        "INSERT INTO memory_items "
                        "(id, category, subject, content, claim_type, status, confirmed_at, "
                        "created_at, updated_at, deleted_at) VALUES "
                        "(:id, 'fact', 'confirmed subject', 'confirmed content', "
                        "'user_confirmed_fact', :status, :ts, :ts, :ts, :deleted)"
                    ),
                    {"id": memory_id, "status": status, "ts": timestamp, "deleted": deleted_at},
                )
            assert connection.execute(
                text("SELECT count(*) FROM memory_items_fts WHERE memory_items_fts MATCH 'confirmed'")
            ).scalar_one() == 1
    finally:
        store.close()


def test_wrong_key_is_rejected_without_exposing_key_or_database_path(storage_root: Path) -> None:
    path = (storage_root / "store.db").resolve()
    store = _store(path, b"a" * DATABASE_KEY_BYTES)
    store.open()
    store.close()

    wrong_key = b"sensitive-test-key-material-1234"
    assert len(wrong_key) == DATABASE_KEY_BYTES
    wrong_store = _store(path, wrong_key)
    with pytest.raises(PersistentStoreError) as error:
        wrong_store.open()
    assert wrong_key.hex() not in str(error.value)
    assert str(path) not in str(error.value)
    wrong_store.close()


def test_store_reopens_and_migrations_are_idempotent(storage_root: Path) -> None:
    path = (storage_root / "store.db").resolve()
    key = b"r" * DATABASE_KEY_BYTES
    first = _store(path, key)
    first.open()
    with first.connection() as connection, connection.begin():
        connection.execute(
            text("INSERT INTO conversations(id, created_at, updated_at) VALUES ('c1', 't', 't')")
        )
    first.close()

    second = _store(path, key)
    second.open()
    try:
        with second.connection() as connection:
            assert connection.execute(text("SELECT count(*) FROM conversations")).scalar_one() == 1
            assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "0001_product_store"
    finally:
        second.close()


def test_store_requires_a_32_byte_key_and_absolute_path(storage_root: Path) -> None:
    with pytest.raises(ValueError, match="32 random bytes"):
        EncryptedApplicationStore(path=(storage_root / "store.db").resolve(), key=b"short")
    with pytest.raises(ValueError, match="absolute"):
        EncryptedApplicationStore(path=Path("relative.db"), key=b"p" * DATABASE_KEY_BYTES)


def test_existing_symlink_database_is_rejected(storage_root: Path) -> None:
    root = storage_root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    target = root / "target.db"
    target.write_bytes(b"do not open")
    link = root / "store.db"
    link.symlink_to(target)

    store = _store(link)
    with pytest.raises(PersistentStoreError, match="owned by the current user"):
        store.open()


def test_encrypted_file_is_not_readable_by_plain_sqlite(storage_root: Path) -> None:
    path = (storage_root / "store.db").resolve()
    store = _store(path)
    store.open()
    store.close()
    with pytest.raises(sqlite3.DatabaseError):
        sqlite3.connect(path).execute("SELECT name FROM sqlite_master").fetchall()


def test_conversation_turns_load_in_order_and_manual_delete_removes_content(
    storage_root: Path,
) -> None:
    store = _store((storage_root / "store.db").resolve())
    store.open()
    try:
        conversation = store.get_or_create_default_conversation()
        conversation_id = conversation["id"]
        store.append_chat_turn(
            conversation_id=conversation_id,
            run_id=str(uuid4()),
            user_content="Remember this project title",
            assistant_content="Project Atlas",
            provider="ollama",
            model="local-test",
            status="COMPLETED",
        )
        snapshot = store.load_conversation(conversation_id)
        assert snapshot["title"] == "Remember this project title"
        assert snapshot["messages"] == [
            {"role": "user", "content": "Remember this project title"},
            {"role": "assistant", "content": "Project Atlas"},
        ]
        assert store.delete_conversation(conversation_id)
        assert store.load_conversation()["messages"] == []
    finally:
        store.close()


def test_task_lifecycle_is_idempotent_and_completed_tasks_expire_after_30_days(
    storage_root: Path,
) -> None:
    from datetime import datetime, timedelta, timezone

    store = _store((storage_root / "tasks.db").resolve())
    store.open()
    now = datetime(2026, 11, 10, tzinfo=timezone.utc)
    try:
        task = store.create_task(
            title="Prepare V2 task flow", idempotency_key="task-create-once"
        )
        repeated = store.create_task(
            title="Ignored duplicate", idempotency_key="task-create-once"
        )
        assert repeated["id"] == task["id"]
        assert repeated["title"] == "Prepare V2 task flow"
        ready = store.transition_task(str(task["id"]), "READY")
        assert ready["status"] == "READY"
        running = store.transition_task(str(task["id"]), "RUNNING")
        assert running["started_at"] is not None
        completed = store.transition_task(str(task["id"]), "COMPLETED")
        assert completed["completed_at"] is not None
        with pytest.raises(ValueError, match="transition"):
            store.transition_task(str(task["id"]), "READY")

        old_id = "expired-task"
        with store.connection() as connection, connection.begin():
            old = (now - timedelta(days=31)).isoformat()
            connection.execute(
                text(
                    "INSERT INTO tasks(id,title,status,priority,retry_count,idempotency_key,"
                    "created_at,updated_at,started_at,completed_at) "
                    "VALUES(:id,'Old task','COMPLETED',0,0,'old-task',:old,:old,:old,:old)"
                ), {"id": old_id, "old": old}
            )
        assert store.purge_expired_completed_tasks(now=now) == 1
        assert [item["id"] for item in store.list_tasks()] == [task["id"]]
    finally:
        store.close()


def test_confirmed_memory_search_version_and_delete_lifecycle(storage_root: Path) -> None:
    store = _store((storage_root / "memories.db").resolve())
    store.open()
    try:
        memory = store.create_confirmed_memory(
            subject="Project Atlas",
            content="Use a local encrypted archive",
            category="decision",
        )
        assert memory["claim_type"] == "user_confirmed_fact"
        assert store.search_memories("encrypted archive")[0]["id"] == memory["id"]
        updated = store.update_confirmed_memory(
            str(memory["id"]), subject="Project Atlas", content="Use a local private archive", category="decision"
        )
        assert updated["content"] == "Use a local private archive"
        assert store.search_memories("private archive")[0]["id"] == memory["id"]
        assert store.search_memories("encrypted archive") == []
        with store.connection() as connection:
            assert connection.execute(
                text("SELECT count(*) FROM memory_versions WHERE memory_id=:id"),
                {"id": memory["id"]},
            ).scalar_one() == 2
        assert store.delete_memory(str(memory["id"]))
        assert store.search_memories("encrypted archive") == []
        assert store.list_memories() == []
    finally:
        store.close()


def test_conversation_list_create_and_targeted_delete_isolate_histories(storage_root: Path) -> None:
    store = _store((storage_root / "conversations.db").resolve())
    store.open()
    try:
        first = store.get_or_create_default_conversation()
        second = store.create_conversation(title="Second conversation")
        store.append_chat_turn(
            conversation_id=first["id"], run_id="conversation-run-1",
            user_content="first only", assistant_content="reply one",
            provider="ollama", model="local", status="COMPLETED",
        )
        store.append_chat_turn(
            conversation_id=second["id"], run_id="conversation-run-2",
            user_content="second only", assistant_content="reply two",
            provider="ollama", model="local", status="COMPLETED",
        )
        conversations = store.list_conversations()
        assert {item["id"] for item in conversations} == {first["id"], second["id"]}
        assert next(item for item in conversations if item["id"] == first["id"])["message_count"] == 2
        assert store.delete_conversation(first["id"])
        assert store.load_conversation(second["id"])["messages"][0]["content"] == "second only"
    finally:
        store.close()
