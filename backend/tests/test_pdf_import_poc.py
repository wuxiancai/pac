from __future__ import annotations

import io
import zlib

import pytest
import subprocess

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


def make_flate_stream_bomb() -> bytes:
    from pypdf import PdfWriter
    from pypdf.generic import (
        ArrayObject,
        DictionaryObject,
        EncodedStreamObject,
        NameObject,
        NumberObject,
        StreamObject,
    )

    writer = PdfWriter()
    page = writer.add_blank_page(width=72, height=72)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
            NameObject("/Encoding"): NameObject("/WinAnsiEncoding"),
            NameObject("/FirstChar"): NumberObject(32),
            NameObject("/LastChar"): NumberObject(126),
            NameObject("/Widths"): ArrayObject([NumberObject(500) for _ in range(95)]),
        }
    )
    page[NameObject("/Resources")] = writer._add_object(
        DictionaryObject(
            {NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})}
        )
    )
    stream = EncodedStreamObject()
    stream[NameObject("/Filter")] = NameObject("/FlateDecode")
    # The encoded PDF stays tiny while the decoded stream exceeds the worker's
    # 2 MB per-filter output budget.
    content = b"BT /F1 12 Tf (A) Tj ET\n" * 90_000
    StreamObject.set_data(stream, zlib.compress(content))
    page[NameObject("/Contents")] = writer._add_object(stream)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def make_text_limit_pdf() -> bytes:
    from pypdf import PdfWriter
    from pypdf.generic import (
        ArrayObject,
        DecodedStreamObject,
        DictionaryObject,
        NameObject,
        NumberObject,
    )

    writer = PdfWriter()
    page = writer.add_blank_page(width=72, height=72)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
            NameObject("/Encoding"): NameObject("/WinAnsiEncoding"),
            NameObject("/FirstChar"): NumberObject(32),
            NameObject("/LastChar"): NumberObject(126),
            NameObject("/Widths"): ArrayObject([NumberObject(500) for _ in range(95)]),
        }
    )
    page[NameObject("/Resources")] = writer._add_object(
        DictionaryObject(
            {NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})}
        )
    )
    stream = DecodedStreamObject()
    stream.set_data(b"BT /F1 12 Tf (" + b"A" * 200_001 + b") Tj ET")
    page[NameObject("/Contents")] = writer._add_object(stream)
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


def test_rejects_flate_stream_exceeding_decode_budget() -> None:
    pdf = make_flate_stream_bomb()
    assert len(pdf) < 10_000

    with pytest.raises(PdfImportRejected, match="safely parsed"):
        extract_pdf_text(pdf)


def test_rejects_extracted_text_exceeding_character_limit() -> None:
    with pytest.raises(PdfImportRejected, match="safely parsed"):
        extract_pdf_text(make_text_limit_pdf())


def test_converts_child_process_timeout_to_safe_rejection(monkeypatch) -> None:
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], timeout=kwargs["timeout"])

    monkeypatch.setattr("pac_poc.pdf_import_poc.subprocess.run", timeout)
    with pytest.raises(PdfImportRejected, match="time limit"):
        extract_pdf_text(make_pdf())
