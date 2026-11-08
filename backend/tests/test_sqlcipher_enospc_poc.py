from __future__ import annotations

import errno
import sqlite3
from pathlib import Path
import json
import subprocess
import sys
import tempfile

import pytest
import sqlcipher3.dbapi2 as sqlcipher

from pac_poc.disk_full_poc import is_disk_full_error, validate_workspace


def test_disk_full_classifier_accepts_os_and_sqlite_full_errors() -> None:
    os_error = OSError(errno.ENOSPC, "no space left on device")
    sqlite_error = sqlite3.OperationalError("database or disk is full")
    sqlite_error.sqlite_errorcode = sqlite3.SQLITE_FULL

    assert is_disk_full_error(os_error)
    assert is_disk_full_error(sqlite_error)
    assert not is_disk_full_error(OSError(errno.EIO, "I/O error"))
    assert not is_disk_full_error(sqlite3.OperationalError("database is locked"))
    assert is_disk_full_error(sqlcipher.OperationalError("database or disk is full"))


def test_disk_full_classifier_recognizes_wrapped_sqlite_full_error() -> None:
    wrapped = RuntimeError("safe domain error")
    original = sqlite3.OperationalError("database or disk is full")
    original.sqlite_errorcode = sqlite3.SQLITE_FULL
    wrapped.__cause__ = original

    assert is_disk_full_error(wrapped)


def test_workspace_must_be_a_child_of_explicit_poc_root(tmp_path: Path) -> None:
    allowed_root = tmp_path / "backend" / ".poc-data"
    workspace = allowed_root / "enospc"
    workspace.mkdir(parents=True)

    assert validate_workspace(workspace, allowed_root) == workspace.resolve()
    with pytest.raises(ValueError, match="inside the explicit POC data root"):
        validate_workspace(tmp_path / "outside", allowed_root)
    with pytest.raises(ValueError, match="must not be the POC data root"):
        validate_workspace(allowed_root, allowed_root)


def test_workspace_rejects_symlink_escape(tmp_path: Path) -> None:
    allowed_root = tmp_path / "backend" / ".poc-data"
    outside = tmp_path / "outside"
    allowed_root.mkdir(parents=True)
    outside.mkdir()
    link = allowed_root / "escape"
    link.symlink_to(outside, target_is_directory=True)

    with pytest.raises(ValueError, match="inside the explicit POC data root"):
        validate_workspace(link / "run", allowed_root)


@pytest.mark.skipif(sys.platform != "darwin", reason="requires macOS hdiutil")
@pytest.mark.parametrize(("filesystem", "image_size_mb"), [("HFS+", 32), ("APFS", 128)])
def test_bounded_disk_image_exhaustion_preserves_encrypted_data_and_backup(
    filesystem: str, image_size_mb: int
) -> None:
    backend = Path(__file__).resolve().parents[1]
    allowed_root = backend / ".poc-data"
    allowed_root.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="enospc-test-", dir=allowed_root) as workspace:
        completed = subprocess.run(
            [
                sys.executable,
                "scripts/run_sqlcipher_enospc_poc.py",
                "--work-dir",
                workspace,
                "--image-size-mb",
                str(image_size_mb),
                "--filesystem",
                filesystem,
            ],
            cwd=backend,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )

    assert completed.returncode == 0, completed.stderr + completed.stdout
    report = json.loads(completed.stdout)
    assert report["disk_full_observed"] is True
    assert report["filesystem"] == filesystem
    assert report["source_integrity"] == "ok"
    assert report["backup_integrity"] == "ok"
    assert report["source_baseline_rows"] == 1
    assert report["source_rejected_rows"] == 0
    assert report["backup_baseline_rows"] == 1
    assert report["record_content_or_key_logged"] is False
    assert "baseline sentinel" not in completed.stdout
    assert "capacity overflow" not in completed.stdout


@pytest.mark.skipif(sys.platform != "darwin", reason="requires macOS hdiutil")
def test_backup_copy_enospc_preserves_source_and_previous_backup() -> None:
    backend = Path(__file__).resolve().parents[1]
    allowed_root = backend / ".poc-data"
    allowed_root.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="backup-enospc-test-", dir=allowed_root) as workspace:
        completed = subprocess.run(
            [
                sys.executable,
                "scripts/run_sqlcipher_enospc_poc.py",
                "--work-dir",
                workspace,
                "--scenario",
                "backup-copy",
                "--image-size-mb",
                "128",
            ],
            cwd=backend,
            capture_output=True,
            text=True,
            timeout=90,
            check=False,
        )

    assert completed.returncode == 0, completed.stderr + completed.stdout
    report = json.loads(completed.stdout)
    assert report["backup_disk_full_observed"] is True
    assert report["filesystem"] == "APFS"
    assert report["source_integrity"] == "ok"
    assert report["old_backup_integrity"] == "ok"
    assert report["source_baseline_rows"] == 1
    assert report["source_bulk_rows"] == 12
    assert report["old_backup_baseline_rows"] == 1
    assert report["partial_files_cleaned"] is True
    assert report["record_content_or_keys_logged"] is False
    assert "source baseline sentinel" not in completed.stdout
    assert "bulkcopytoken" not in completed.stdout
