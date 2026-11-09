from __future__ import annotations

import io

import pytest

pypdf = pytest.importorskip("pypdf")

from pac_poc.pdf_import_poc import (  # noqa: E402
    MAX_PDF_BYTES,
    PdfImportRejected,
    extract_pdf_text,
)


def make_pdf(page_count: int = 1) -> bytes:
    from pypdf import PdfWriter

    writer = PdfWriter()
    for _ in range(page_count):
        writer.add_blank_page(width=72, height=72)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def test_extracts_valid_pdf_in_child_process() -> None:
    result = extract_pdf_text(make_pdf())
    assert result.page_count == 1
    assert result.text == ""


def test_rejects_input_larger_than_byte_limit() -> None:
    with pytest.raises(PdfImportRejected, match="size"):
        extract_pdf_text(b"%PDF-" + b"x" * MAX_PDF_BYTES)


def test_rejects_invalid_pdf() -> None:
    with pytest.raises(PdfImportRejected, match="safely parsed"):
        extract_pdf_text(b"%PDF-1.7\nnot a valid PDF")


def test_rejects_pdf_exceeding_page_tree_limit() -> None:
    with pytest.raises(PdfImportRejected, match="safely parsed"):
        extract_pdf_text(make_pdf(page_count=101))
