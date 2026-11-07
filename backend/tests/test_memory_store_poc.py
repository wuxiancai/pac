from __future__ import annotations

import pytest

from pac_poc.memory_poc import MemoryStore


class FixtureEmbeddingProvider:
    model_id = "fixture-memory-embedding"

    def embed(self, texts: list[str]) -> list[tuple[float, ...]]:
        vectors = {
            "我喜欢徒步旅行": (1.0, 0.0),
            "用户偏好山间步行": (0.99, 0.01),
            "用户正在学习 Swift 编程": (0.0, 1.0),
            "用户偏好登山活动": (0.9, 0.1),
        }
        return [vectors[text] for text in texts]


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


def test_semantic_memory_search_is_opt_in_and_preserves_source_evidence() -> None:
    store = MemoryStore(embedding_provider=FixtureEmbeddingProvider())
    try:
        hiking_id = store.remember(
            content="我喜欢徒步旅行",
            source_id="message-hiking",
            claim_type="user_confirmed_fact",
            observed_at="2026-11-07T06:00:00Z",
        )
        store.remember(
            content="用户正在学习 Swift 编程",
            source_id="message-swift",
            claim_type="event",
            observed_at="2026-11-07T06:01:00Z",
        )

        matches = store.search_semantic("用户偏好山间步行")

        assert matches[0].memory_id == hiking_id
        assert matches[0].source_ids == ("message-hiking",)
        assert matches[0].score > matches[1].score
    finally:
        store.close()


def test_correction_replaces_old_semantic_vector_and_delete_clears_new_one() -> None:
    store = MemoryStore(embedding_provider=FixtureEmbeddingProvider())
    try:
        old_id = store.remember(
            content="我喜欢徒步旅行",
            source_id="message-old",
            claim_type="user_confirmed_fact",
            observed_at="2026-11-07T06:00:00Z",
        )
        new_id = store.correct(
            old_memory_id=old_id,
            content="用户偏好登山活动",
            source_id="message-new",
            claim_type="user_confirmed_fact",
            observed_at="2026-11-07T07:00:00Z",
        )

        assert store.embedding_count(old_id) == 0
        assert store.search_semantic("用户偏好山间步行")[0].memory_id == new_id

        store.delete(new_id)
        assert store.embedding_count(new_id) == 0
        assert store.search_semantic("用户偏好山间步行") == []
    finally:
        store.close()


def test_embedding_failure_during_correction_preserves_active_memory_and_index() -> None:
    class ToggleProvider(FixtureEmbeddingProvider):
        fail = False

        def embed(self, texts: list[str]) -> list[tuple[float, ...]]:
            if self.fail:
                raise RuntimeError("fixture embedding unavailable")
            return super().embed(texts)

    provider = ToggleProvider()
    store = MemoryStore(embedding_provider=provider)
    try:
        memory_id = store.remember(
            content="我喜欢徒步旅行",
            source_id="message-old",
            claim_type="user_confirmed_fact",
            observed_at="2026-11-07T06:00:00Z",
        )
        provider.fail = True

        with pytest.raises(RuntimeError, match="fixture embedding unavailable"):
            store.correct(
                old_memory_id=memory_id,
                content="用户偏好登山活动",
                source_id="message-new",
                claim_type="user_confirmed_fact",
                observed_at="2026-11-07T07:00:00Z",
            )

        provider.fail = False
        assert store.search("徒步")
        assert store.embedding_count(memory_id) == 1
        assert store.search_semantic("用户偏好山间步行")[0].memory_id == memory_id
    finally:
        store.close()


def test_restored_memory_can_reuse_explicit_embedding_provider() -> None:
    original = MemoryStore(embedding_provider=FixtureEmbeddingProvider())
    memory_id = original.remember(
        content="我喜欢徒步旅行",
        source_id="message-hiking",
        claim_type="user_confirmed_fact",
        observed_at="2026-11-07T06:00:00Z",
    )
    backup = original.backup_bytes()
    original.close()

    restored = MemoryStore.restore_bytes(
        backup,
        embedding_provider=FixtureEmbeddingProvider(),
    )
    try:
        assert restored.search_semantic("用户偏好山间步行")[0].memory_id == memory_id
    finally:
        restored.close()


def test_semantic_search_fails_explicitly_when_embedding_is_not_configured(
    store: MemoryStore,
) -> None:
    with pytest.raises(RuntimeError, match="embedding provider is not configured"):
        store.search_semantic("任意查询")
