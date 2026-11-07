from __future__ import annotations

from pathlib import Path
import json
import subprocess
import sys

from pac_poc.sqlcipher_benchmark import benchmark_pair


def test_sqlcipher_benchmark_pair_measures_same_synthetic_workload_without_content(
    tmp_path: Path,
) -> None:
    result = benchmark_pair(tmp_path, records=40, queries=8)

    assert result["records"] == 40
    assert result["queries"] == 8
    assert set(result["engines"]) == {"sqlite", "sqlcipher"}
    for metrics in result["engines"].values():
        assert metrics["write_seconds"] >= 0
        assert metrics["search_seconds"] >= 0
        assert metrics["backup_seconds"] >= 0
        assert metrics["database_bytes"] > 0
        assert metrics["backup_bytes"] > 0
        assert metrics["successful_queries"] == 8

    rendered = repr(result)
    assert "synthetic private payload" not in rendered
    assert "key" not in result
    assert list(tmp_path.glob("*.partial")) == []


def test_sqlcipher_benchmark_cli_outputs_only_synthetic_metrics(tmp_path: Path) -> None:
    backend = Path(__file__).resolve().parents[1]
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/benchmark_sqlcipher_poc.py",
            "--records",
            "20",
            "--queries",
            "4",
            "--repeats",
            "1",
            "--work-dir",
            str(tmp_path),
        ],
        cwd=backend,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    report = json.loads(completed.stdout)
    assert report["synthetic_data"] is True
    assert report["transcript_or_record_content_logged"] is False
    assert report["runs"][0]["records"] == 20
    assert "synthetic private payload" not in completed.stdout
    assert "key" not in completed.stdout.lower()
