"""Versioned, password-protected SQLCipher backup container primitives."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import shutil
import struct
import tempfile
from dataclasses import dataclass
from pathlib import Path


MAGIC = b"PACBACK\x00"
FORMAT_VERSION = 1
KDF_NAME = "scrypt"
SCRYPT_N = 32_768
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_MAXMEM_BYTES = 64 * 1024 * 1024
SALT_BYTES = 16
DERIVED_KEY_BYTES = 32
HEADER_LENGTH_BYTES = 4
MAX_HEADER_BYTES = 2_048
COPY_BUFFER_BYTES = 1024 * 1024


class EncryptedBackupError(RuntimeError):
    """Safe backup error that never includes a password, key, or file content."""


@dataclass(frozen=True)
class BackupHeader:
    salt: bytes
    source_key_fingerprint: str
    payload_offset: int


def derive_backup_key(password: str, salt: bytes) -> bytes:
    """Derive the SQLCipher backup passphrase using the user-approved scrypt profile."""
    if not isinstance(password, str) or not password:
        raise ValueError("backup password must not be empty")
    try:
        password_bytes = password.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError("backup password must be valid UTF-8 text") from exc
    if len(password_bytes) > 4_096:
        raise ValueError("backup password is too long")
    if not isinstance(salt, bytes) or len(salt) != SALT_BYTES:
        raise ValueError("backup salt has an invalid length")
    try:
        return hashlib.scrypt(
            password_bytes,
            salt=salt,
            n=SCRYPT_N,
            r=SCRYPT_R,
            p=SCRYPT_P,
            maxmem=SCRYPT_MAXMEM_BYTES,
            dklen=DERIVED_KEY_BYTES,
        )
    except (AttributeError, ValueError, OSError, MemoryError) as exc:
        raise EncryptedBackupError("password derivation is unavailable") from exc


def write_backup_container(
    sqlcipher_database: Path,
    target: Path,
    *,
    password: str,
    database_key: bytes,
    salt: bytes | None = None,
    replace_existing: bool = False,
) -> None:
    """Wrap an already encrypted SQLCipher database in an authenticated format header."""
    if not isinstance(database_key, bytes) or len(database_key) != DERIVED_KEY_BYTES:
        raise ValueError("database key must contain 32 bytes")
    if not sqlcipher_database.is_file() or sqlcipher_database.is_symlink():
        raise EncryptedBackupError("encrypted database staging file is unavailable")
    source = sqlcipher_database.resolve()
    destination = target.absolute()
    if source == destination.resolve(strict=False):
        raise ValueError("backup target must differ from database staging file")
    if destination.exists() and not replace_existing:
        raise FileExistsError("backup target already exists")
    try:
        destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    except OSError as exc:
        raise EncryptedBackupError("backup destination is unavailable") from exc

    salt = secrets.token_bytes(SALT_BYTES) if salt is None else salt
    if not isinstance(salt, bytes) or len(salt) != SALT_BYTES:
        raise ValueError("backup salt has an invalid length")
    key = derive_backup_key(password, salt)
    core = {
        "format_version": FORMAT_VERSION,
        "kdf": KDF_NAME,
        "kdf_parameters": {"n": SCRYPT_N, "r": SCRYPT_R, "p": SCRYPT_P},
        "salt": base64.b64encode(salt).decode("ascii"),
        "source_key_fingerprint": hashlib.sha256(database_key).hexdigest(),
    }
    canonical_core = json.dumps(core, sort_keys=True, separators=(",", ":")).encode("ascii")
    mac_key = hmac.new(key, b"PACBACK header MAC key v1", hashlib.sha256).digest()
    mac = hmac.new(mac_key, MAGIC + canonical_core, hashlib.sha256).hexdigest()
    header = json.dumps({**core, "header_mac": mac}, sort_keys=True, separators=(",", ":")).encode("ascii")
    if len(header) > MAX_HEADER_BYTES:
        raise EncryptedBackupError("backup header exceeds the supported size")

    descriptor = -1
    staging_path: Path | None = None
    try:
        descriptor, staging_name = tempfile.mkstemp(
            prefix=f".{destination.name}.", suffix=".partial", dir=destination.parent
        )
        staging_path = Path(staging_name)
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as output, source.open("rb") as payload:
            descriptor = -1
            output.write(MAGIC)
            output.write(struct.pack(">I", len(header)))
            output.write(header)
            shutil.copyfileobj(payload, output, length=COPY_BUFFER_BYTES)
            output.flush()
            os.fsync(output.fileno())
        if destination.exists() and not replace_existing:
            raise FileExistsError("backup target already exists")
        os.replace(staging_path, destination)
        staging_path = None
        _fsync_directory(destination.parent)
    except (OSError, ValueError) as exc:
        raise EncryptedBackupError("encrypted backup could not be written") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if staging_path is not None:
            staging_path.unlink(missing_ok=True)


def read_backup_header(path: Path, *, password: str, database_key: bytes) -> tuple[BackupHeader, bytes]:
    """Validate the versioned header/password and return its parsed metadata and key."""
    if not isinstance(database_key, bytes) or len(database_key) != DERIVED_KEY_BYTES:
        raise ValueError("database key must contain 32 bytes")
    if not path.is_file() or path.is_symlink():
        raise EncryptedBackupError("backup file is unavailable")
    try:
        with path.open("rb") as stream:
            if stream.read(len(MAGIC)) != MAGIC:
                raise EncryptedBackupError("backup format is invalid")
            raw_length = stream.read(HEADER_LENGTH_BYTES)
            if len(raw_length) != HEADER_LENGTH_BYTES:
                raise EncryptedBackupError("backup header is truncated")
            header_length = struct.unpack(">I", raw_length)[0]
            if not 1 <= header_length <= MAX_HEADER_BYTES:
                raise EncryptedBackupError("backup header length is invalid")
            raw_header = stream.read(header_length)
            if len(raw_header) != header_length or stream.read(1) == b"":
                raise EncryptedBackupError("backup payload is missing or header is truncated")
        header = json.loads(raw_header.decode("ascii"))
    except EncryptedBackupError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError, struct.error) as exc:
        raise EncryptedBackupError("backup format is invalid") from exc

    expected_fields = {
        "format_version", "kdf", "kdf_parameters", "salt", "source_key_fingerprint", "header_mac"
    }
    if not isinstance(header, dict) or set(header) != expected_fields:
        raise EncryptedBackupError("backup header fields are invalid")
    if type(header["format_version"]) is not int or header["format_version"] != FORMAT_VERSION:
        raise EncryptedBackupError("backup format version is unsupported")
    if header["kdf"] != KDF_NAME:
        raise EncryptedBackupError("backup format version is unsupported")
    parameters = header["kdf_parameters"]
    if (
        not isinstance(parameters, dict)
        or set(parameters) != {"n", "r", "p"}
        or any(type(value) is not int for value in parameters.values())
    ):
        raise EncryptedBackupError("backup KDF parameters are unsupported")
    if header["kdf_parameters"] != {"n": SCRYPT_N, "r": SCRYPT_R, "p": SCRYPT_P}:
        raise EncryptedBackupError("backup KDF parameters are unsupported")
    salt_text = header["salt"]
    if not isinstance(salt_text, str):
        raise EncryptedBackupError("backup salt is invalid")
    try:
        salt = base64.b64decode(salt_text, validate=True)
    except (ValueError, TypeError) as exc:
        raise EncryptedBackupError("backup salt is invalid") from exc
    if len(salt) != SALT_BYTES:
        raise EncryptedBackupError("backup salt is invalid")
    fingerprint = header["source_key_fingerprint"]
    mac = header["header_mac"]
    if not isinstance(fingerprint, str) or len(fingerprint) != 64:
        raise EncryptedBackupError("backup installation binding is invalid")
    if not isinstance(mac, str) or len(mac) != 64:
        raise EncryptedBackupError("backup authentication data is invalid")

    key = derive_backup_key(password, salt)
    core = {field: header[field] for field in expected_fields if field != "header_mac"}
    canonical_core = json.dumps(core, sort_keys=True, separators=(",", ":")).encode("ascii")
    mac_key = hmac.new(key, b"PACBACK header MAC key v1", hashlib.sha256).digest()
    expected_mac = hmac.new(mac_key, MAGIC + canonical_core, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(mac, expected_mac):
        raise EncryptedBackupError("backup password is incorrect or the file is damaged")
    expected_fingerprint = hashlib.sha256(database_key).hexdigest()
    if not hmac.compare_digest(fingerprint, expected_fingerprint):
        raise EncryptedBackupError("backup belongs to a different installation")
    return BackupHeader(
        salt=salt,
        source_key_fingerprint=fingerprint,
        payload_offset=len(MAGIC) + HEADER_LENGTH_BYTES + len(raw_header),
    ), key


def extract_backup_payload(path: Path, destination: Path, *, payload_offset: int) -> None:
    """Copy the SQLCipher bytes after a previously authenticated envelope header."""
    if payload_offset < len(MAGIC) + HEADER_LENGTH_BYTES + 1:
        raise ValueError("backup payload offset is invalid")
    descriptor = -1
    staging_path: Path | None = None
    try:
        destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        descriptor, staging_name = tempfile.mkstemp(
            prefix=f".{destination.name}.", suffix=".partial", dir=destination.parent
        )
        staging_path = Path(staging_name)
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as output, path.open("rb") as source:
            descriptor = -1
            source.seek(payload_offset)
            shutil.copyfileobj(source, output, length=COPY_BUFFER_BYTES)
            output.flush()
            os.fsync(output.fileno())
            if output.tell() == 0:
                raise EncryptedBackupError("backup payload is empty")
        os.replace(staging_path, destination)
        staging_path = None
        _fsync_directory(destination.parent)
    except EncryptedBackupError:
        raise
    except OSError as exc:
        raise EncryptedBackupError("backup payload could not be staged") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if staging_path is not None:
            staging_path.unlink(missing_ok=True)


def _fsync_directory(directory: Path) -> None:
    descriptor = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
