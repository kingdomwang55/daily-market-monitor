"""Consistent SQLite backup and guarded restore helpers."""

from __future__ import annotations

from datetime import datetime
import os
from pathlib import Path
import sqlite3
import tempfile

from ..core.db_path import sqlite_db_path


def check_integrity(path: Path) -> None:
    """Raise ValueError when a SQLite file fails its integrity check."""
    if not path.is_file():
        raise FileNotFoundError(f"SQLite database not found: {path}")
    connection = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    try:
        result = connection.execute("PRAGMA integrity_check").fetchone()
    finally:
        connection.close()
    if not result or result[0] != "ok":
        detail = result[0] if result else "no result"
        raise ValueError(f"SQLite integrity check failed: {detail}")


def default_backup_path(source: Path, directory: Path | None = None) -> Path:
    destination_dir = directory or source.parent / "backups"
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return destination_dir / f"{source.stem}-{timestamp}.db"


def backup_database(source: Path | None = None, destination: Path | None = None) -> Path:
    """Create a WAL-safe backup and atomically publish it."""
    source = (source or sqlite_db_path()).resolve()
    destination = (destination or default_backup_path(source)).resolve()
    if source == destination:
        raise ValueError("Backup destination must differ from the live database")
    if not source.is_file():
        raise FileNotFoundError(f"SQLite database not found: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)

    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
    )
    os.close(fd)
    temporary = Path(temporary_name)
    source_connection = sqlite3.connect(str(source), timeout=30)
    destination_connection = sqlite3.connect(str(temporary))
    try:
        source_connection.backup(destination_connection)
        destination_connection.commit()
    finally:
        destination_connection.close()
        source_connection.close()
    try:
        check_integrity(temporary)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def restore_database(
    backup: Path,
    target: Path | None = None,
    *,
    keep_current: bool = True,
) -> tuple[Path, Path | None]:
    """Restore a checked backup and return target plus optional safety backup."""
    backup = backup.resolve()
    target = (target or sqlite_db_path()).resolve()
    if backup == target:
        raise ValueError("Restore source must differ from the live database")
    check_integrity(backup)
    target.parent.mkdir(parents=True, exist_ok=True)

    safety_backup = None
    if keep_current and target.is_file():
        safety_dir = target.parent / "backups"
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        safety_path = safety_dir / f"{target.stem}-pre-restore-{timestamp}.db"
        safety_backup = backup_database(target, safety_path)

    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".restore", dir=target.parent
    )
    os.close(fd)
    temporary = Path(temporary_name)
    source_connection = sqlite3.connect(str(backup), timeout=30)
    target_connection = sqlite3.connect(str(temporary))
    try:
        source_connection.backup(target_connection)
        target_connection.commit()
    finally:
        target_connection.close()
        source_connection.close()
    try:
        check_integrity(temporary)
        for suffix in ("-wal", "-shm"):
            Path(f"{target}{suffix}").unlink(missing_ok=True)
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    return target, safety_backup
