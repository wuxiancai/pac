from __future__ import annotations

import shutil
import sqlite3
import stat
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

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
            assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "0005_security_audit"
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
        assert [
            {"role": message["role"], "content": message["content"]}
            for message in snapshot["messages"]
        ] == [
            {"role": "user", "content": "Remember this project title"},
            {"role": "assistant", "content": "Project Atlas"},
        ]
        assert all(UUID(message["id"]) for message in snapshot["messages"])
        assert store.delete_conversation(conversation_id)
        assert store.load_conversation()["messages"] == []
    finally:
        store.close()


def test_task_lifecycle_is_idempotent_and_completed_tasks_expire_after_30_days(
    storage_root: Path,
) -> None:
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
        assert task["allowed_transitions"] == ["CANCELLED", "READY"]
        ready = store.transition_task(str(task["id"]), "READY")
        assert ready["status"] == "READY"
        assert ready["allowed_transitions"] == ["CANCELLED", "PAUSED", "RUNNING"]
        running = store.transition_task(str(task["id"]), "RUNNING")
        assert running["started_at"] is not None
        assert running["allowed_transitions"] == [
            "CANCELLED", "COMPLETED", "FAILED", "PARTIAL", "WAITING"
        ]
        completed = store.transition_task(str(task["id"]), "COMPLETED")
        assert completed["completed_at"] is not None
        assert completed["allowed_transitions"] == []
        repeated_completion = store.transition_task(str(task["id"]), "COMPLETED")
        assert repeated_completion["completed_at"] == completed["completed_at"]
        assert repeated_completion["updated_at"] == completed["updated_at"]
        with pytest.raises(ValueError, match="transition"):
            store.transition_task(str(task["id"]), "READY")

        seeded_tasks = [
            ("expired-task", "COMPLETED", now - timedelta(days=31)),
            ("exactly-30-days-task", "COMPLETED", now - timedelta(days=30)),
            ("recent-completed-task", "COMPLETED", now - timedelta(days=29)),
            ("old-failed-task", "FAILED", now - timedelta(days=31)),
        ]
        with store.connection() as connection, connection.begin():
            for task_id, status, completed_at in seeded_tasks:
                timestamp = completed_at.isoformat()
                connection.execute(text(
                    "INSERT INTO tasks(id,title,status,priority,retry_count,idempotency_key,"
                    "created_at,updated_at,started_at,completed_at) "
                    "VALUES(:id,:title,:status,0,0,:idempotency,:timestamp,:timestamp,:timestamp,:timestamp)"
                ), {
                    "id": task_id,
                    "title": task_id,
                    "status": status,
                    "idempotency": f"{task_id}-key",
                    "timestamp": timestamp,
                })
        assert store.purge_expired_completed_tasks(now=now) == 2
        remaining_ids = {item["id"] for item in store.list_tasks()}
        assert remaining_ids == {
            task["id"], "recent-completed-task", "old-failed-task"
        }
    finally:
        store.close()


def test_local_skill_catalog_is_fixed_prompt_only_and_rejects_unknown_keys(
    storage_root: Path,
) -> None:
    store = _store((storage_root / "skills.db").resolve())
    store.open()
    try:
        skills = store.list_skills()
        assert {skill["skill_key"] for skill in skills} == {
            "risk_review", "decision_brief", "action_items"
        }
        assert store.get_skill_prompts(["risk_review"])[0].startswith("对用户提供的项目")
        assert store.get_skill_prompts([]) == []
        with store.connection() as connection:
            manifest = connection.execute(
                text("SELECT permission_manifest_json FROM skills WHERE skill_key='risk_review'")
            ).scalar_one()
        assert manifest == '{"tools":[],"external_write":false}'
        with pytest.raises(ValueError, match="selection"):
            store.get_skill_prompts(["unknown_skill"])
        with pytest.raises(ValueError, match="selection"):
            store.get_skill_prompts(["risk_review", "risk_review"])
        with pytest.raises(ValueError, match="selection"):
            store.get_skill_prompts(["risk_review", "decision_brief", "action_items", "risk_review"])
        with store.connection() as connection, connection.begin():
            connection.execute(
                text("UPDATE skills SET definition_json='invalid' WHERE skill_key='risk_review'")
            )
        with pytest.raises(RuntimeError, match="definition"):
            store.get_skill_prompts(["risk_review"])
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
        versions = store.list_memory_versions(str(memory["id"]))
        assert [version["version_no"] for version in versions] == [1, 2]
        assert versions[0]["snapshot"]["content"] == "Use a local encrypted archive"
        assert versions[1]["snapshot"]["content"] == "Use a local private archive"
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
        second = store.rename_conversation(second["id"], "Planning")
        assert second["title"] == "Planning"
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


def test_conversation_history_uses_stable_bounded_keyset_pages(storage_root: Path) -> None:
    store = _store((storage_root / "paged-history.db").resolve())
    store.open()
    try:
        conversation = store.get_or_create_default_conversation()
        for number in range(3):
            store.append_chat_turn(
                conversation_id=conversation["id"], run_id=f"page-run-{number}",
                user_content=f"user-{number}", assistant_content=f"assistant-{number}",
                provider="ollama", model="local", status="COMPLETED",
            )
        latest = store.load_conversation(conversation["id"], limit=3)
        assert [item["content"] for item in latest["messages"]] == [
            "assistant-1", "user-2", "assistant-2",
        ]
        assert latest["has_more"] is True
        older = store.load_conversation(
            conversation["id"], limit=3, before_message_id=latest["messages"][0]["id"]
        )
        assert [item["content"] for item in older["messages"]] == [
            "user-0", "assistant-0", "user-1",
        ]
        assert older["has_more"] is False
    finally:
        store.close()


def test_long_conversation_history_pages_have_no_gaps_or_duplicates(storage_root: Path) -> None:
    store = _store((storage_root / "long-paged-history.db").resolve())
    store.open()
    try:
        conversation = store.get_or_create_default_conversation()
        expected = {
            content
            for number in range(60)
            for content in (f"user-long-{number}", f"assistant-long-{number}")
        }
        for number in range(60):
            store.append_chat_turn(
                conversation_id=conversation["id"], run_id=f"long-page-run-{number}",
                user_content=f"user-long-{number}",
                assistant_content=f"assistant-long-{number}",
                provider="ollama", model="local", status="COMPLETED",
            )

        page = store.load_conversation(conversation["id"], limit=100)
        collected: list[str] = []
        while True:
            messages = page["messages"]
            assert len(messages) <= 100
            collected.extend(message["content"] for message in messages)
            if not page["has_more"]:
                break
            page = store.load_conversation(
                conversation["id"], limit=100,
                before_message_id=messages[0]["id"],
            )

        assert len(collected) == 120
        assert len(set(collected)) == 120
        assert set(collected) == expected
    finally:
        store.close()


def test_monthly_cloud_budget_is_encrypted_atomic_and_validated(storage_root: Path) -> None:
    store = _store((storage_root / "cloud-budget.db").resolve())
    store.open()
    try:
        assert store.monthly_cloud_budget_micros("2026-11") == 0
        with ThreadPoolExecutor(max_workers=8) as pool:
            totals = list(pool.map(
                lambda _: store.add_monthly_cloud_budget_estimate(
                    "2026-11", amount_micros=125_000, price_version="2026-11-10"
                ),
                range(16),
            ))
        assert store.monthly_cloud_budget_micros("2026-11") == 2_000_000
        assert max(totals) == 2_000_000
        with pytest.raises(ValueError, match="YYYY-MM"):
            store.monthly_cloud_budget_micros("2026-13")
        with pytest.raises(ValueError, match="non-negative integer"):
            store.add_monthly_cloud_budget_estimate(
                "2026-11", amount_micros=-1, price_version="2026-11-10"
            )
    finally:
        store.close()


def test_monthly_cloud_budget_reservations_serialize_across_store_instances(
    storage_root: Path,
) -> None:
    path = (storage_root / "shared-cloud-budget.db").resolve()
    first = _store(path)
    second = _store(path)
    first.open()
    second.open()
    try:
        def reserve(store: EncryptedApplicationStore, reservation_id: str) -> bool:
            return store.reserve_monthly_cloud_budget(
                "2026-11",
                reservation_id=reservation_id,
                amount_micros=60_000_000,
                limit_micros=100_000_000,
                expires_at="2999-01-01T00:00:00+00:00",
            )

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(
                lambda args: reserve(*args),
                [(first, "first-request"), (second, "second-request")],
            ))
        assert sorted(results) == [False, True]
        winner = "first-request" if results[0] else "second-request"
        assert second.renew_monthly_cloud_budget_reservation(
            winner, expires_at="2999-02-01T00:00:00+00:00"
        ) is True
        assert first.settle_monthly_cloud_budget_reservation(
            "2026-11",
            reservation_id=winner,
            amount_micros=50_000_000,
            price_version="2026-11-10",
        ) == 50_000_000
        assert second.renew_monthly_cloud_budget_reservation(
            winner, expires_at="2999-03-01T00:00:00+00:00"
        ) is False
        assert second.reserve_monthly_cloud_budget(
            "2026-11",
            reservation_id="third-request",
            amount_micros=50_000_000,
            limit_micros=100_000_000,
            expires_at="2999-01-01T00:00:00+00:00",
        ) is False
        assert second.reserve_monthly_cloud_budget(
            "2026-11",
            reservation_id="fourth-request",
            amount_micros=49_999_999,
            limit_micros=100_000_000,
            expires_at="2999-01-01T00:00:00+00:00",
        ) is True
        first.release_monthly_cloud_budget_reservation("fourth-request")
    finally:
        first.close()
        second.close()


def test_security_audit_is_metadata_only_and_purges_events_older_than_30_days(
    storage_root: Path,
) -> None:
    store = _store((storage_root / "security-audit.db").resolve())
    store.open()
    trace_id = str(uuid4())
    resource_id = str(uuid4())
    try:
        first = store.record_security_audit_event(
            trace_id=trace_id,
            action="provider_request",
            resource_id=resource_id,
            decision="ATTEMPTED",
            reason_code="user_confirmed_budget_reserved",
            data_sensitivity="L2",
            provider_id="openrouter",
            model_id="deepseek/deepseek-v4.1-flash-1017",
            region="global",
            purpose="beta-interactive-chat",
        )
        assert set(first) == {
            "id", "trace_id", "action", "resource_id", "decision", "reason_code",
            "data_sensitivity", "provider_id", "model_id", "region", "purpose", "created_at",
        }
        with store.connection() as connection:
            connection.execute(text(
                "UPDATE security_audit_events SET created_at=:created_at WHERE id=:id"
            ), {
                "created_at": (datetime.now(timezone.utc) - timedelta(days=31)).isoformat(),
                "id": first["id"],
            })
            connection.commit()
        second = store.record_security_audit_event(
            trace_id=trace_id,
            action="provider_request",
            resource_id=resource_id,
            decision="SUCCEEDED",
            reason_code="provider_stream_completed",
            data_sensitivity="L2",
            provider_id="openrouter",
            model_id="deepseek/deepseek-v4.1-flash-1017",
            region="global",
            purpose="beta-interactive-chat",
        )
        listed = store.list_security_audit_events()
        assert [event["id"] for event in listed] == [second["id"]]
        with pytest.raises(ValueError, match="data sensitivity"):
            store.record_security_audit_event(
                trace_id=trace_id,
                action="provider_request",
                resource_id=resource_id,
                decision="DENIED",
                reason_code="blocked",
                data_sensitivity="L3",
                provider_id="deepseek",
                model_id="deepseek-flash",
                region="china",
                purpose="beta-interactive-chat",
            )
    finally:
        store.close()
