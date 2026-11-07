from __future__ import annotations

import pytest

from pac_poc.memory_poc import MemoryStore


@pytest.fixture
def store() -> MemoryStore:
    value = MemoryStore()
    yield value
    value.close()


def test_memory_can_be_retrieved_with_its_source_evidence(store: MemoryStore) -> None:
    memory_id = store.remember(
        content="用户偏好简洁交流",
        source_id="message-7",
        claim_type="user_confirmed_fact",
        observed_at="2026-11-07T02:00:00Z",
    )

    matches = store.search("简洁")

    assert len(matches) == 1
    assert matches[0].memory_id == memory_id
    assert matches[0].source_ids == ("message-7",)
    assert matches[0].claim_type == "user_confirmed_fact"


def test_correction_versions_old_fact_and_excludes_it_from_current_search(
    store: MemoryStore,
) -> None:
    old_id = store.remember(
        content="用户偏好英文回答",
        source_id="message-8",
        claim_type="user_confirmed_fact",
        observed_at="2026-11-07T02:00:00Z",
    )

    new_id = store.correct(
        old_memory_id=old_id,
        content="用户偏好中文回答",
        source_id="message-9",
        claim_type="user_confirmed_fact",
        observed_at="2026-11-07T03:00:00Z",
    )

    assert [item.memory_id for item in store.search("英文")] == []
    assert [item.memory_id for item in store.search("回答")] == [new_id]
    assert store.history(old_id)[0].status == "superseded"


def test_delete_removes_memory_from_full_text_and_derived_index(store: MemoryStore) -> None:
    memory_id = store.remember(
        content="用户项目代号为海风",
        source_id="message-10",
        claim_type="inference",
        observed_at="2026-11-07T04:00:00Z",
    )
    store.add_embedding(memory_id, model_id="local-candidate", vector=(0.1, 0.2))

    store.delete(memory_id)

    assert store.search("海风") == []
    assert store.embedding_count(memory_id) == 0
    assert store.history(memory_id)[0].status == "deleted"


def test_in_memory_backup_can_be_restored_without_creating_a_product_database(
    store: MemoryStore,
) -> None:
    memory_id = store.remember(
        content="仅用于恢复演练",
        source_id="fixture-1",
        claim_type="inference",
        observed_at="2026-11-07T05:00:00Z",
    )
    backup = store.backup_bytes()

    restored = MemoryStore.restore_bytes(backup)
    try:
        assert [item.memory_id for item in restored.search("恢复演练")] == [memory_id]
    finally:
        restored.close()
