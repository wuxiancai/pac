from __future__ import annotations

import errno
import os
import sqlite3
from pathlib import Path


def is_disk_full_error(error: BaseException) -> bool:
    if isinstance(error, OSError) and error.errno == errno.ENOSPC:
        return True
    return getattr(error, "sqlite_errorcode", None) == sqlite3.SQLITE_FULL


def validate_workspace(path: Path, allowed_root: Path) -> Path:
    root = allowed_root.resolve()
    workspace = path.resolve()
    if workspace == root:
        raise ValueError("workspace must not be the POC data root")
    if root not in workspace.parents:
        raise ValueError("workspace must be inside the explicit POC data root")
    return workspace
