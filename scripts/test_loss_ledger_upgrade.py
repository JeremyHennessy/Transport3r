"""Schema rejection must preserve existing private ledger bytes and objects."""
from contextlib import closing
import hashlib
import pathlib
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import private_loss_history as ledger
from test_private_loss_history import POLICY, raw


class LossLedgerUpgradeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.path = pathlib.Path(self.temp.name) / 'loss-history.sqlite'

    def initialize(self, script):
        with closing(sqlite3.connect(self.path)) as db:
            db.executescript(script)
        self.path.chmod(0o600)

    def state(self):
        with closing(sqlite3.connect(self.path)) as db:
            objects = db.execute('SELECT type,name,sql FROM sqlite_master ORDER BY type,name').fetchall()
            values = list(db.iterdump())
        return hashlib.sha256(self.path.read_bytes()).hexdigest(), objects, values

    def attempt(self):
        source = raw(); policies = [POLICY]
        with closing(sqlite3.connect(self.path)) as db:
            return ledger.import_loss_history(db, source, policies, 'Synthetic reviewer',
                                              ledger.preview(source, policies)['preview_sha256'])

    def test_unversioned_populated_ledger_rejection_is_byte_preserving(self):
        self.initialize("CREATE TABLE loss_observations (legacy_claim TEXT); "
                        "INSERT INTO loss_observations VALUES ('SYNTHETIC-LEGACY');")
        before = self.state()
        with self.assertRaisesRegex(ValueError, 'LEGACY_LEDGER_IDENTITY_REVIEW_REQUIRED'):
            self.attempt()
        self.assertEqual(self.state(), before)

    def test_unknown_marker_rejection_does_not_create_missing_tables(self):
        self.initialize("CREATE TABLE loss_ledger_schema(singleton INTEGER PRIMARY KEY, schema TEXT); "
                        "INSERT INTO loss_ledger_schema VALUES (1,'UNKNOWN_LEGACY');")
        before = self.state()
        with self.assertRaisesRegex(ValueError, 'UNSUPPORTED_LEDGER_IDENTITY_SCHEMA'):
            self.attempt()
        self.assertEqual(self.state(), before)

    def test_schema_error_rolls_back_all_prior_ddl(self):
        self.initialize('CREATE TABLE legacy_metadata (value TEXT);')
        before = self.state()
        with patch.object(ledger, 'DDL', ledger.DDL + '\nNOT VALID SQL;'):
            with self.assertRaises(sqlite3.OperationalError):
                self.attempt()
        self.assertEqual(self.state(), before)

    def test_new_empty_database_initializes_and_imports_normally(self):
        self.initialize('')
        result = self.attempt()
        self.assertEqual(result['imported_rows'], 1)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT schema FROM loss_ledger_schema').fetchall(), [(ledger.LEDGER_SCHEMA,)])
            self.assertEqual(db.execute('SELECT count(*) FROM loss_observations').fetchone()[0], 1)

    def test_summary_rejection_also_preserves_existing_legacy_bytes(self):
        self.initialize("CREATE TABLE loss_observations (legacy_claim TEXT); "
                        "INSERT INTO loss_observations VALUES ('SYNTHETIC-LEGACY');")
        before = self.state()
        with closing(sqlite3.connect(self.path)) as db:
            with self.assertRaisesRegex(ValueError, 'LEGACY_LEDGER_IDENTITY_REVIEW_REQUIRED'):
                ledger.summarize_batch(db, 'a' * 64)
        self.assertEqual(self.state(), before)


if __name__ == '__main__':
    unittest.main()
