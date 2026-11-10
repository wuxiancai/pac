from __future__ import annotations

from pathlib import Path

import pytest

from pac_poc.backup import (
    EncryptedBackupError,
    extract_backup_payload,
    read_backup_header,
    write_backup_container,
)
from pac_poc.persistence import EncryptedApplicationStore, PersistentStoreError


def test_backup_container_round_trips_payload_without_loading_it_into_memory(tmp_path: Path) -> None:
    source = tmp_path / "cipher.db"
    backup = tmp_path / "archive.pacbackup"
    restored = tmp_path / "restored.db"
    payload = bytes(range(256)) * 8192
    source.write_bytes(payload)

    write_backup_container(source, backup, password="correct horse", database_key=b"d" * 32)  # pragma: allowlist secret
    header, _ = read_backup_header(backup, password="correct horse", database_key=b"d" * 32)  # pragma: allowlist secret
    extract_backup_payload(backup, restored, payload_offset=header.payload_offset)

    assert restored.read_bytes() == payload
    assert backup.stat().st_mode & 0o777 == 0o600
    assert len(header.salt) == 16


def test_backup_container_rejects_wrong_password_and_another_installation(tmp_path: Path) -> None:
    source = tmp_path / "cipher.db"
    backup = tmp_path / "archive.pacbackup"
    source.write_bytes(b"encrypted database bytes")
    write_backup_container(source, backup, password="correct horse", database_key=b"d" * 32)  # pragma: allowlist secret

    with pytest.raises(EncryptedBackupError, match="incorrect or the file is damaged"):
        read_backup_header(backup, password="wrong password", database_key=b"d" * 32)  # pragma: allowlist secret
    with pytest.raises(EncryptedBackupError, match="different installation"):
        read_backup_header(backup, password="correct horse", database_key=b"x" * 32)  # pragma: allowlist secret


def test_backup_container_rejects_tampered_header_and_missing_payload(tmp_path: Path) -> None:
    source = tmp_path / "cipher.db"
    backup = tmp_path / "archive.pacbackup"
    source.write_bytes(b"database")
    write_backup_container(source, backup, password="correct horse", database_key=b"d" * 32)  # pragma: allowlist secret
    raw = bytearray(backup.read_bytes())
    mac_marker = raw.index(b'"header_mac":"') + len(b'"header_mac":"')
    raw[mac_marker] = ord("0") if raw[mac_marker] != ord("0") else ord("1")
    backup.write_bytes(raw)
    with pytest.raises(EncryptedBackupError, match="incorrect or the file is damaged"):
        read_backup_header(backup, password="correct horse", database_key=b"d" * 32)  # pragma: allowlist secret

    backup.write_bytes(b"PACBACK\x00\x00\x00\x00\x00")
    with pytest.raises(EncryptedBackupError):
        read_backup_header(backup, password="correct horse", database_key=b"d" * 32)  # pragma: allowlist secret


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
        read_backup_header(backup, password="correct horse", database_key=b"d" * 32)  # pragma: allowlist secret


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
        result = store.export_encrypted_backup(backup, password="archive passphrase")  # pragma: allowlist secret
        assert result["bytes_written"] == backup.stat().st_size
        assert database.exists()
    finally:
        store.close()

    header, derived_key = read_backup_header(
        backup, password="archive passphrase", database_key=database_key  # pragma: allowlist secret
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


def test_live_sqlcipher_restore_prebacks_up_and_reencrypts_with_local_key(tmp_path: Path) -> None:
    database_key = b"r" * 32
    database = (tmp_path / "product.db").resolve()
    backup = tmp_path / "snapshot.pacbackup"
    store = EncryptedApplicationStore(path=database, key=database_key)
    store.open()
    original = store.get_or_create_default_conversation()
    store.append_chat_turn(
        conversation_id=str(original["id"]), run_id="restore-original",
        user_content="before restore", assistant_content="old response",
        provider="ollama", model="fixture", status="COMPLETED",
    )
    store.export_encrypted_backup(backup, password="restore passphrase")  # pragma: allowlist secret
    store.append_chat_turn(
        conversation_id=str(original["id"]), run_id="restore-later",
        user_content="after backup", assistant_content="later response",
        provider="ollama", model="fixture", status="COMPLETED",
    )

    result = store.restore_encrypted_backup(backup, password="restore passphrase")  # pragma: allowlist secret
    assert Path(result["prebackup_path"]).is_file()
    assert Path(result["prebackup_path"]).stat().st_mode & 0o777 == 0o600
    restored = store.load_conversation(str(original["id"]))
    assert [message["content"] for message in restored["messages"]] == ["before restore", "old response"]
    first_prebackup = EncryptedApplicationStore._open_password_database(
        Path(result["prebackup_path"]), database_key.hex()
    )
    try:
        assert first_prebackup.execute(
            "SELECT count(*) FROM messages WHERE content='after backup'"
        ).fetchone() == (1,)
    finally:
        first_prebackup.close()
    store.append_chat_turn(
        conversation_id=str(original["id"]), run_id="restore-second-later",
        user_content="after second restore", assistant_content="latest response",
        provider="ollama", model="fixture", status="COMPLETED",
    )
    second_result = store.restore_encrypted_backup(backup, password="restore passphrase")  # pragma: allowlist secret
    assert second_result["prebackup_path"] == result["prebackup_path"]
    assert list((tmp_path / "pre-restore").glob("*.sqlcipher")) == [Path(result["prebackup_path"])]
    store.close()

    prebackup = EncryptedApplicationStore._open_password_database(
        Path(result["prebackup_path"]), database_key.hex()
    )
    try:
        assert prebackup.execute(
            "SELECT count(*) FROM messages WHERE content='after backup'"
        ).fetchone() == (0,)
        assert prebackup.execute(
            "SELECT count(*) FROM messages WHERE content='after second restore'"
        ).fetchone() == (1,)
    finally:
        prebackup.close()


def test_live_sqlcipher_restore_wrong_password_leaves_database_untouched(tmp_path: Path) -> None:
    database = (tmp_path / "product.db").resolve()
    store = EncryptedApplicationStore(path=database, key=b"w" * 32)
    store.open()
    conversation = store.get_or_create_default_conversation()
    store.append_chat_turn(
        conversation_id=str(conversation["id"]), run_id="restore-wrong-password",
        user_content="keep this", assistant_content="safe",
        provider="ollama", model="fixture", status="COMPLETED",
    )
    backup = tmp_path / "snapshot.pacbackup"
    store.export_encrypted_backup(backup, password="right password")  # pragma: allowlist secret
    with pytest.raises(EncryptedBackupError, match="incorrect or the file is damaged"):
        store.restore_encrypted_backup(backup, password="wrong password")  # pragma: allowlist secret
    assert store.load_conversation(str(conversation["id"]))["messages"][0]["content"] == "keep this"
    assert not (tmp_path / "pre-restore").exists()
    store.close()


def test_live_sqlcipher_restore_rolls_back_if_new_database_cannot_open(tmp_path: Path) -> None:
    database = (tmp_path / "product.db").resolve()
    store = EncryptedApplicationStore(path=database, key=b"t" * 32)
    store.open()
    conversation = store.get_or_create_default_conversation()
    store.append_chat_turn(
        conversation_id=str(conversation["id"]), run_id="rollback-before",
        user_content="keep after rollback", assistant_content="safe",
        provider="ollama", model="fixture", status="COMPLETED",
    )
    backup = tmp_path / "snapshot.pacbackup"
    store.export_encrypted_backup(backup, password="rollback passphrase")  # pragma: allowlist secret
    store.append_chat_turn(
        conversation_id=str(conversation["id"]), run_id="rollback-after",
        user_content="later state", assistant_content="still safe",
        provider="ollama", model="fixture", status="COMPLETED",
    )
    original_open = store.open
    fail_once = True

    def fail_first_reopen() -> None:
        nonlocal fail_once
        if fail_once:
            fail_once = False
            raise PersistentStoreError("synthetic activation failure")
        original_open()

    store.open = fail_first_reopen  # type: ignore[method-assign]
    with pytest.raises(PersistentStoreError, match="synthetic activation failure"):
        store.restore_encrypted_backup(backup, password="rollback passphrase")  # pragma: allowlist secret
    assert store.load_conversation(str(conversation["id"]))["messages"][-2]["content"] == "later state"
    assert database.exists()
    assert not list(tmp_path.glob("*.rollback"))
    store.close()


@pytest.mark.parametrize("database_present", [True, False])
def test_store_open_recovers_uncommitted_restore_rollback(tmp_path: Path, database_present: bool) -> None:
    database = (tmp_path / "product.db").resolve()
    store = EncryptedApplicationStore(path=database, key=b"i" * 32)
    store.open()
    conversation = store.get_or_create_default_conversation()
    store.append_chat_turn(
        conversation_id=str(conversation["id"]), run_id="startup-recovery",
        user_content="rollback should win", assistant_content="old committed state",
        provider="ollama", model="fixture", status="COMPLETED",
    )
    rollback = database.with_name(f".{database.name}.interrupted.rollback")
    snapshot = EncryptedApplicationStore._open_password_database(rollback, (b"i" * 32).hex())
    connection = store.connection()
    try:
        source = connection.connection.driver_connection
        assert source is not None
        source.backup(snapshot)
    finally:
        snapshot.close()
        connection.close()
    store.delete_conversation(str(conversation["id"]))
    store.close()
    if not database_present:
        database.unlink()

    recovered = EncryptedApplicationStore(path=database, key=b"i" * 32)
    recovered.open()
    assert recovered.load_conversation(str(conversation["id"]))["messages"][0]["content"] == "rollback should win"
    assert not rollback.exists()
    recovered.close()
