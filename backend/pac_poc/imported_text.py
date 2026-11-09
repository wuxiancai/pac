"""Ephemeral, user-selected plain-text document intake for the local beta."""

from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from uuid import uuid4


MAX_IMPORTED_FILE_BYTES = 10 * 1024 * 1024
MAX_IMPORTED_DOCUMENTS = 8
MAX_IMPORTED_TOTAL_BYTES = 20 * 1024 * 1024
ALLOWED_TEXT_SUFFIXES = frozenset({".txt", ".md", ".markdown"})


class ImportRejected(ValueError):
    """A selected file does not satisfy the beta's bounded text import contract."""


@dataclass(frozen=True)
class ImportedTextDocument:
    import_id: str
    display_name: str
    byte_count: int
    character_count: int
    text: str


class ImportedTextRegistry:
    """Keep user-selected text in bounded process memory; never store paths or bytes on disk."""

    def __init__(
        self,
        *,
        max_documents: int = MAX_IMPORTED_DOCUMENTS,
        max_total_bytes: int = MAX_IMPORTED_TOTAL_BYTES,
    ) -> None:
        if max_documents < 1 or max_total_bytes < 1:
            raise ValueError("import registry limits must be positive")
        self._max_documents = max_documents
        self._max_total_bytes = max_total_bytes
        self._documents: dict[str, ImportedTextDocument] = {}
        self._lock = Lock()

    def add(self, display_name: str, data: bytes) -> ImportedTextDocument:
        if (
            not display_name
            or len(display_name) > 255
            or display_name in {".", ".."}
            or "/" in display_name
            or "\\" in display_name
            or any(ord(char) < 32 or ord(char) == 127 for char in display_name)
        ):
            raise ImportRejected("invalid file name")
        suffix = "." + display_name.rsplit(".", 1)[-1].lower() if "." in display_name else ""
        if suffix not in ALLOWED_TEXT_SUFFIXES:
            raise ImportRejected("file type is not supported")
        if not data or len(data) > MAX_IMPORTED_FILE_BYTES:
            raise ImportRejected("file size is outside the allowed range")
        try:
            text = data.decode("utf-8-sig", errors="strict")
        except UnicodeDecodeError as exc:
            raise ImportRejected("file must be valid UTF-8 text") from exc
        if not text.strip() or "\x00" in text:
            raise ImportRejected("file is empty or contains binary data")
        document = ImportedTextDocument(
            import_id=str(uuid4()),
            display_name=display_name,
            byte_count=len(data),
            character_count=len(text),
            text=text,
        )
        with self._lock:
            total_bytes = sum(item.byte_count for item in self._documents.values())
            if len(self._documents) >= self._max_documents:
                raise ImportRejected("too many imported files; remove one and retry")
            if total_bytes + document.byte_count > self._max_total_bytes:
                raise ImportRejected("temporary imported-file memory limit reached")
            self._documents[document.import_id] = document
        return document

    def get_many(self, import_ids: tuple[str, ...]) -> tuple[ImportedTextDocument, ...]:
        if len(import_ids) != len(set(import_ids)):
            raise ImportRejected("duplicate import id")
        with self._lock:
            missing = [item for item in import_ids if item not in self._documents]
            if missing:
                raise KeyError("imported file is unavailable")
            return tuple(self._documents[item] for item in import_ids)

    def remove(self, import_id: str) -> bool:
        with self._lock:
            return self._documents.pop(import_id, None) is not None
