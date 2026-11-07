from __future__ import annotations

import argparse
import errno
import json
import os
import plistlib
import secrets
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from pac_poc.disk_full_poc import is_disk_full_error, validate_workspace
from pac_poc.sqlcipher_poc import SQLCipherFTSDatabase


def _run_hdiutil(*arguments: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["/usr/bin/hdiutil", *arguments],
        capture_output=True,
        check=True,
    )


def _attach_image(image: Path, mountpoint: Path) -> str:
    result = _run_hdiutil(
        "attach", "-plist", "-nobrowse", "-mountpoint", str(mountpoint), str(image)
    )
    attachment = plistlib.loads(result.stdout)
    expected_mountpoint = mountpoint.resolve()
    for entity in attachment.get("system-entities", []):
        device = entity.get("dev-entry")
        attached_mountpoint = entity.get("mount-point")
        if device and attached_mountpoint:
            if Path(str(attached_mountpoint)).resolve() == expected_mountpoint:
                return str(device)
    raise RuntimeError("hdiutil did not report the requested mounted volume")


def _fill_volume(mountpoint: Path, reserve_bytes: int) -> tuple[int, bool]:
    filler = mountpoint / ".capacity-poc-fill"
    written = filler.stat().st_size if filler.exists() else 0
    reached_full = False
    chunk = b"P" * (64 * 1024)
    descriptor = os.open(filler, os.O_CREAT | os.O_WRONLY | os.O_APPEND, 0o600)
    try:
        while shutil.disk_usage(mountpoint).free > reserve_bytes:
            try:
                chunk_written = os.write(descriptor, chunk)
            except OSError as exc:
                if exc.errno == errno.ENOSPC:
                    reached_full = True
                    break
                raise
            if chunk_written == 0:
                break
            written += chunk_written
            os.fsync(descriptor)
    finally:
        os.close(descriptor)
    if shutil.disk_usage(mountpoint).free == 0:
        reached_full = True
    return written, reached_full


def run_poc(
    workspace: Path, *, image_size_mb: int = 48, filesystem: str = "HFS+"
) -> dict[str, object]:
    if sys.platform != "darwin":
        raise RuntimeError("this bounded disk-image POC requires macOS")
    if filesystem not in {"HFS+", "APFS"}:
        raise ValueError("filesystem must be HFS+ or APFS")
    minimum_size_mb = 64 if filesystem == "APFS" else 32
    if image_size_mb < minimum_size_mb or image_size_mb > 256:
        raise ValueError(
            f"image size must be between {minimum_size_mb} and 256 MiB for {filesystem}"
        )

    image = workspace / "capacity.dmg"
    mountpoint = workspace / "volume"
    mountpoint.mkdir()
    device: str | None = None
    source: SQLCipherFTSDatabase | None = None
    backup_key = secrets.token_urlsafe(48)
    source_key = secrets.token_urlsafe(48)
    result: dict[str, object] | None = None
    try:
        _run_hdiutil(
            "create",
            "-size",
            f"{image_size_mb}m",
            "-fs",
            filesystem,
            "-type",
            "UDIF",
            "-volname",
            "PACPOC-ENOSPC",
            str(image),
        )
        device = _attach_image(image, mountpoint)

        database_path = mountpoint / "source.db"
        backup_path = mountpoint / "backup.db"
        source = SQLCipherFTSDatabase(path=database_path, key=source_key)
        source.add("committed baseline sentinel")
        source.backup_to(backup_path, backup_key=backup_key)
        source.close()
        source = None

        filler_bytes, _ = _fill_volume(mountpoint, reserve_bytes=512 * 1024)
        write_error: BaseException | None = None
        attempted_content = "capacity overflow token " * 100_000
        candidate = SQLCipherFTSDatabase.open_existing(path=database_path, key=source_key)
        try:
            try:
                candidate.add(attempted_content)
            except Exception as exc:
                write_error = exc
        finally:
            candidate.close()

        if write_error is None or not is_disk_full_error(write_error):
            raise RuntimeError("the write did not fail with a recognized disk-full error")

        (mountpoint / ".capacity-poc-fill").unlink(missing_ok=True)
        recovered = SQLCipherFTSDatabase.open_existing(path=database_path, key=source_key)
        try:
            source_rows = recovered.search('"baseline sentinel"')
            rejected_rows = recovered.search('"capacity overflow"')
            source_integrity = recovered.integrity_check()
        finally:
            recovered.close()

        restored = SQLCipherFTSDatabase.open_existing(path=backup_path, key=backup_key)
        try:
            backup_rows = restored.search('"baseline sentinel"')
            backup_integrity = restored.integrity_check()
        finally:
            restored.close()

        if (
            source_rows != ["committed baseline sentinel"]
            or rejected_rows
            or source_integrity != "ok"
            or backup_rows != ["committed baseline sentinel"]
            or backup_integrity != "ok"
        ):
            raise RuntimeError("post-ENOSPC recovery verification failed")

        result = {
            "status": "completed",
            "disk_full_observed": True,
            "error_type": type(write_error).__name__,
            "source_integrity": source_integrity,
            "backup_integrity": backup_integrity,
            "source_baseline_rows": len(source_rows),
            "source_rejected_rows": len(rejected_rows),
            "backup_baseline_rows": len(backup_rows),
            "image_size_mb": image_size_mb,
            "filesystem": filesystem,
            "filler_bytes_written": filler_bytes,
            "record_content_or_key_logged": False,
        }
    finally:
        if source is not None:
            source.close()
        if device is not None:
            _run_hdiutil("detach", device)
        shutil.rmtree(mountpoint, ignore_errors=True)
        image.unlink(missing_ok=True)

    if result is None:
        raise RuntimeError("disk-full POC did not produce a result")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify SQLCipher rollback and encrypted backup recovery on a bounded macOS disk image"
    )
    parser.add_argument(
        "--work-dir",
        type=Path,
        default=Path(".poc-data/enospc"),
        help="temporary workspace under backend/.poc-data; created files are removed",
    )
    parser.add_argument("--image-size-mb", type=int, default=48)
    parser.add_argument("--filesystem", choices=("HFS+", "APFS"), default="HFS+")
    args = parser.parse_args()
    backend = Path(__file__).resolve().parents[1]
    allowed_root = backend / ".poc-data"
    try:
        workspace = validate_workspace(args.work_dir, allowed_root)
        workspace.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="run-", dir=workspace) as run_directory:
            payload = run_poc(
                Path(run_directory),
                image_size_mb=args.image_size_mb,
                filesystem=args.filesystem,
            )
    except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as exc:
        print(json.dumps({"status": "error", "error_type": type(exc).__name__}))
        return 1
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
