from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_native_swift_client_connects_to_loopback_fastapi_without_logging_token() -> None:
    backend = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "scripts/run_swift_fastapi_poc.py"],
        cwd=backend,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == (
        "Swift client reached local FastAPI over loopback; restart handshake passed."
    )
    assert "Bearer " not in result.stdout + result.stderr
