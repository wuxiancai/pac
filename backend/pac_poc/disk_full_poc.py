from __future__ import annotations

import errno
import os
import sqlite3
from pathlib import Path


def is_disk_full_error(error: BaseException) -> bool:
    seen: set[int] = set()
    current: BaseException | None = error
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, OSError) and current.errno == errno.ENOSPC:
            return True
        if getattr(current, "sqlite_errorcode", None) == sqlite3.SQLITE_FULL:
            return True
        is_sqlite_error = isinstance(current, sqlite3.Error) or type(
            current
        ).__module__.startswith("sqlcipher3.")
        if (
            is_sqlite_error
            and str(current).strip().casefold() == "database or disk is full"
        ):
            return True
        current = current.__cause__ or current.__context__
    return False


def validate_workspace(path: Path, allowed_root: Path) -> Path:
    root = allowed_root.resolve()
    workspace = path.resolve()
    if workspace == root:
        raise ValueError("workspace must not be the POC data root")
    if root not in workspace.parents:
        raise ValueError("workspace must be inside the explicit POC data root")
    return workspace
