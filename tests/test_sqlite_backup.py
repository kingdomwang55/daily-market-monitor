"""SQLite backup and restore regression tests."""

from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from market_monitor.ops.sqlite_backup import (
    backup_database,
    check_integrity,
    restore_database,
)


class SqliteBackupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.live = self.root / "market.db"
        self.connection = sqlite3.connect(self.live)
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("CREATE TABLE samples (id INTEGER PRIMARY KEY, value TEXT)")
        self.connection.execute("INSERT INTO samples(value) VALUES ('before')")
        self.connection.commit()

    def tearDown(self):
        self.connection.close()
        self.tmp.cleanup()

    @staticmethod
    def values(path: Path) -> list[str]:
        connection = sqlite3.connect(path)
        try:
            return [row[0] for row in connection.execute("SELECT value FROM samples ORDER BY id")]
        finally:
            connection.close()

    def test_backup_captures_committed_wal_data(self):
        destination = self.root / "backups" / "snapshot.db"

        result = backup_database(self.live, destination)

        self.assertEqual(result, destination.resolve())
        self.assertEqual(self.values(destination), ["before"])
        check_integrity(destination)

    def test_restore_preserves_current_database_and_replaces_contents(self):
        snapshot = backup_database(self.live, self.root / "snapshot.db")
        self.connection.execute("INSERT INTO samples(value) VALUES ('after')")
        self.connection.commit()
        self.connection.close()

        target, safety = restore_database(snapshot, self.live)
        self.connection = sqlite3.connect(self.live)

        self.assertEqual(target, self.live.resolve())
        self.assertIsNotNone(safety)
        self.assertEqual(self.values(self.live), ["before"])
        self.assertEqual(self.values(safety), ["before", "after"])

    def test_corrupt_backup_is_rejected_before_target_changes(self):
        corrupt = self.root / "corrupt.db"
        corrupt.write_bytes(b"not a sqlite database")

        with self.assertRaises(sqlite3.DatabaseError):
            restore_database(corrupt, self.live)

        self.assertEqual(self.values(self.live), ["before"])


if __name__ == "__main__":
    unittest.main()
