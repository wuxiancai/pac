from __future__ import annotations

from pathlib import Path

import pytest

from pac_poc.backup import (
    EncryptedBackupError,
    extract_backup_payload,
    read_backup_header,
    write_backup_container,
)
from pac_poc.persistence import EncryptedApplicationStore


def test_backup_container_round_trips_payload_without_loading_it_into_memory(tmp_path: Path) -> None:
    source = tmp_path / "cipher.db"
    backup = tmp_path / "archive.pacbackup"
    restored = tmp_path / "restored.db"
    payload = bytes(range(256)) * 8192
    source.write_bytes(payload)

    write_backup_container(source, backup, password="correct horse", database_key=b"d" * 32)
    header, _ = read_backup_header(backup, password="correct horse", database_key=b"d" * 32)
    extract_backup_payload(backup, restored, payload_offset=header.payload_offset)

    assert restored.read_bytes() == payload
    assert backup.stat().st_mode & 0o777 == 0o600
    assert len(header.salt) == 16


def test_backup_container_rejects_wrong_password_and_another_installation(tmp_path: Path) -> None:
    source = tmp_path / "cipher.db"
    backup = tmp_path / "archive.pacbackup"
    source.write_bytes(b"encrypted database bytes")
    write_backup_container(source, backup, password="correct horse", database_key=b"d" * 32)

    with pytest.raises(EncryptedBackupError, match="incorrect or the file is damaged"):
        read_backup_header(backup, password="wrong password", database_key=b"d" * 32)
    with pytest.raises(EncryptedBackupError, match="different installation"):
        read_backup_header(backup, password="correct horse", database_key=b"x" * 32)


def test_backup_container_rejects_tampered_header_and_missing_payload(tmp_path: Path) -> None:
    source = tmp_path / "cipher.db"
    backup = tmp_path / "archive.pacbackup"
    source.write_bytes(b"database")
    write_backup_container(source, backup, password="correct horse", database_key=b"d" * 32)
    raw = bytearray(backup.read_bytes())
    mac_marker = raw.index(b'"header_mac":"') + len(b'"header_mac":"')
    raw[mac_marker] = ord("0") if raw[mac_marker] != ord("0") else ord("1")
    backup.write_bytes(raw)
    with pytest.raises(EncryptedBackupError, match="incorrect or the file is damaged"):
        read_backup_header(backup, password="correct horse", database_key=b"d" * 32)

    backup.write_bytes(b"PACBACK\x00\x00\x00\x00\x00")
    with pytest.raises(EncryptedBackupError):
        read_backup_header(backup, password="correct horse", database_key=b"d" * 32)


def test_backup_password_and_container_header_have_strict_bounds(tmp_path: Path) -> None:
    source = tmp_path / "cipher.db"
    backup = tmp_path / "archive.pacbackup"
    source.write_bytes(b"database")
    with pytest.raises(ValueError, match="must not be empty"):
        write_backup_container(source, backup, password="", database_key=b"d" * 32)
    with pytest.raises(ValueError, match="too long"):
        write_backup_container(source, backup, password="x" * 4097, database_key=b"d" * 32)
    backup.write_bytes(b"PACBACK\x00\xff\xff\xff\xff")
    with pytest.raises(EncryptedBackupError, match="header length is invalid"):
        read_backup_header(backup, password="correct horse", database_key=b"d" * 32)


def test_live_sqlcipher_store_exports_valid_encrypted_snapshot(tmp_path: Path) -> None:
    database_key = b"d" * 32
    database = (tmp_path / "product.db").resolve()
    backup = tmp_path / "product.pacbackup"
    staging = tmp_path / "extracted.db"
    store = EncryptedApplicationStore(path=database, key=database_key)
    store.open()
    try:
        conversation = store.get_or_create_default_conversation()
        store.append_chat_turn(
            conversation_id=str(conversation["id"]),
            run_id="backup-export-test",
            user_content="local-only backup test",
            assistant_content="persisted response",
            provider="ollama",
            model="fixture",
            status="COMPLETED",
        )
        result = store.export_encrypted_backup(backup, password="archive passphrase")
        assert result["bytes_written"] == backup.stat().st_size
        assert database.exists()
    finally:
        store.close()

    header, derived_key = read_backup_header(
        backup, password="archive passphrase", database_key=database_key
    )
    extract_backup_payload(backup, staging, payload_offset=header.payload_offset)
    connection = EncryptedApplicationStore._open_password_database(staging, derived_key.hex())
    try:
        row = connection.execute(
            "SELECT content FROM messages WHERE content='local-only backup test'"
        ).fetchone()
        assert row == ("local-only backup test",)
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    finally:
        connection.close()
