from __future__ import annotations

import pytest

from pac_poc.imported_text import (
    MAX_IMPORTED_FILE_BYTES,
    ImportRejected,
    ImportedTextRegistry,
)


def test_import_registry_accepts_utf8_text_and_removes_it_from_memory() -> None:
    registry = ImportedTextRegistry()
    document = registry.add("notes.md", b"\xef\xbb\xbfProject notes")

    assert document.display_name == "notes.md"
    assert document.text == "Project notes"
    assert document.byte_count == len(b"\xef\xbb\xbfProject notes")
    assert registry.get_many((document.import_id,)) == (document,)
    assert registry.remove(document.import_id)
    assert not registry.remove(document.import_id)


@pytest.mark.parametrize(
    ("name", "data"),
    [
        ("notes.pdf", b"%PDF-1.7"),
        ("../notes.txt", b"text"),
        ("folder\\notes.txt", b"text"),
        ("bad\nname.txt", b"text"),
        ("notes.txt", b"\xff"),
        ("notes.txt", b"text\x00data"),
        ("notes.txt", b"  \n"),
        ("notes.txt", b"x" * (MAX_IMPORTED_FILE_BYTES + 1)),
    ],
)
def test_import_registry_rejects_unsupported_or_unbounded_content(name: str, data: bytes) -> None:
    with pytest.raises(ImportRejected):
        ImportedTextRegistry().add(name, data)


def test_import_registry_enforces_count_and_total_memory_limits() -> None:
    registry = ImportedTextRegistry(max_documents=1, max_total_bytes=4)
    registry.add("one.txt", b"1234")

    with pytest.raises(ImportRejected, match="too many"):
        registry.add("two.txt", b"x")


def test_import_registry_rejects_duplicate_or_missing_ids() -> None:
    registry = ImportedTextRegistry()
    item = registry.add("one.txt", b"text")

    with pytest.raises(ImportRejected, match="duplicate"):
        registry.get_many((item.import_id, item.import_id))
    with pytest.raises(KeyError):
        registry.get_many(("00000000-0000-0000-0000-000000000000",))
