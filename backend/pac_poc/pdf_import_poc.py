"""Isolated PDF text extraction proof of concept. Not wired into beta imports."""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass

MAX_PDF_BYTES = 10 * 1024 * 1024
MAX_PDF_PAGES = 100
MAX_PDF_TEXT_CHARACTERS = 200_000
PDF_WALL_TIMEOUT_SECONDS = 5


class PdfImportRejected(ValueError):
    """The PDF was invalid or exceeded a POC resource boundary."""


@dataclass(frozen=True)
class PdfTextResult:
    page_count: int
    text: str


def extract_pdf_text(data: bytes) -> PdfTextResult:
    """Parse user-provided bytes in a short-lived, resource-bounded child process."""
    if not data or len(data) > MAX_PDF_BYTES:
        raise PdfImportRejected("PDF size is outside the allowed range")
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pac_poc.pdf_import_worker"],
            input=data,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=PDF_WALL_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise PdfImportRejected("PDF parsing exceeded the time limit") from exc
    if result.returncode != 0:
        raise PdfImportRejected("PDF could not be safely parsed")
    try:
        payload = json.loads(result.stdout)
        text = payload["text"]
        page_count = payload["page_count"]
    except (ValueError, TypeError, KeyError) as exc:
        raise PdfImportRejected("PDF parser returned an invalid result") from exc
    if not isinstance(text, str) or not isinstance(page_count, int):
        raise PdfImportRejected("PDF parser returned an invalid result")
    if len(text) > MAX_PDF_TEXT_CHARACTERS:
        raise PdfImportRejected("PDF text exceeds the allowed limit")
    return PdfTextResult(page_count=page_count, text=text)
