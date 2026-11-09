"""Private subprocess entry point for the optional PDF parser POC."""

from __future__ import annotations

import io
import json
import resource
import sys

from pypdf import PdfReader, apply_configuration

from pac_poc.pdf_import_poc import MAX_PDF_PAGES, MAX_PDF_TEXT_CHARACTERS


def main() -> int:
    try:
        resource.setrlimit(resource.RLIMIT_CPU, (4, 5))
        data = sys.stdin.buffer.read(10 * 1024 * 1024 + 1)
        if len(data) > 10 * 1024 * 1024:
            return 2
        with apply_configuration(
            maximum_declared_stream_length=2_000_000,
            array_based_stream_maximum_output_length=2_000_000,
            array_maximum_element_count=20_000,
            dictionary_maximum_element_count=20_000,
            jbig2_maximum_output_length=2_000_000,
            lzw_maximum_output_length=2_000_000,
            run_length_maximum_output_length=2_000_000,
            zlib_maximum_output_length=2_000_000,
            brotli_maximum_output_length=2_000_000,
            image_maximum_buffer_size=2_000_000,
            stream_filters_maximum_length=8,
            stream_decoding_work_maximum_length=8_000_000,
            stream_parsing_work_maximum_count=100_000,
            page_tree_maximum_entries=MAX_PDF_PAGES,
            page_tree_maximum_depth=32,
            page_tree_maximum_page_entries=20_000,
            xmp_maximum_input_length=500_000,
            xmp_maximum_element_count=10_000,
            form_fields_maximum_entries=1_000,
            form_fields_maximum_depth=32,
        ):
            reader = PdfReader(io.BytesIO(data), strict=True, root_object_recovery_limit=2_000)
            pages = reader.pages
            if len(pages) > MAX_PDF_PAGES:
                return 3
            text_parts: list[str] = []
            character_count = 0
            for page in pages:
                page_text = page.extract_text() or ""
                character_count += len(page_text)
                if character_count > MAX_PDF_TEXT_CHARACTERS:
                    return 4
                text_parts.append(page_text)
        sys.stdout.write(json.dumps({"page_count": len(pages), "text": "\n".join(text_parts)}))
        return 0
    except Exception as exc:
        sys.stderr.write(type(exc).__name__)
        return 5


if __name__ == "__main__":
    raise SystemExit(main())
