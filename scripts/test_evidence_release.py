"""Synthetic release installation, corruption, backup and rollback drills."""
import json
import pathlib
import shutil
import tempfile
import unittest
from unittest.mock import patch
import duckdb
import evidence_release as releases
from audit_warehouse_integrity import audit
from test_audit_warehouse_integrity import make_fixture


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name); self.store = self.root / 'installation'
        self.warehouse = self.root / 'source.duckdb'; make_fixture(self.warehouse)
        self.report = self.root / 'source.audit.json'; self.report.write_text(json.dumps(audit(self.warehouse, deep=True)))

    def stage(self):
        return releases.stage(self.store, self.warehouse, self.report)

    def second(self):
        with duckdb.connect(str(self.warehouse)) as db:
            receipt=json.loads(db.execute('SELECT acceptance_json FROM warehouse_acceptance').fetchone()[0])
            receipt['cut_id']='synthetic-second-cut'
            db.execute('UPDATE warehouse_acceptance SET acceptance_json=?',[json.dumps(receipt)])
        self.report.write_text(json.dumps(audit(self.warehouse, deep=True)))
        return self.stage()

    def test_stage_is_not_deployment_and_never_overwrites(self):
        original=releases.sha256(self.warehouse); result=self.stage()
        self.assertEqual(result['warehouse_sha256'], original)
        self.assertFalse(result['deployed']); self.assertFalse(result['original_source_bytes_revalidated'])
        self.assertEqual(releases.inspect(self.store, original), result)
        self.assertIsNone(releases.current(self.store))
        with self.assertRaises(FileExistsError):self.stage()
        self.assertEqual(releases.sha256(self.warehouse),original)

    def test_activation_backup_restore_and_rollback_preserve_both_releases(self):
        first=self.stage()['release_id']
        releases.activate(self.store,first,None,'Synthetic operator')
        second=self.second()['release_id']
        releases.activate(self.store,second,first,'Synthetic operator')
        backup=self.root/'backup';shutil.copytree(self.store,backup)
        restored=self.root/'restored';shutil.copytree(backup,restored)
        self.assertEqual(releases.current(restored)['release_id'],second)
        rolled=releases.rollback(restored,second,'Synthetic restore operator')
        self.assertEqual(rolled['release_id'],first);self.assertFalse(rolled['deployed'])
        self.assertEqual(releases.current(self.store)['release_id'],second)
        self.assertEqual(len(list((restored/'history').glob('*.json'))),3)
        for release in (first,second):self.assertEqual(releases.inspect(restored,release)['release_id'],release)

    def test_compare_and_swap_rejects_stale_operator(self):
        first=self.stage()['release_id'];releases.activate(self.store,first,None,'Synthetic operator')
        with self.assertRaisesRegex(ValueError,'Current release changed'):
            releases.activate(self.store,first,None,'Synthetic operator')
        with self.assertRaisesRegex(ValueError,'No previous'):
            releases.rollback(self.store,first,'Synthetic operator')
        self.assertEqual(len(list((self.store/'history').glob('*.json'))),1)

    def test_corruption_blocks_activation_without_changing_current(self):
        first=self.stage()['release_id'];releases.activate(self.store,first,None,'Synthetic operator')
        second=self.second()['release_id'];path=self.store/'releases'/second/'audit.json';path.chmod(0o600)
        value=json.loads(path.read_text());value['raw_rows']=999;path.write_text(json.dumps(value))
        with self.assertRaises(ValueError):releases.activate(self.store,second,first,'Synthetic operator')
        self.assertEqual(releases.current(self.store)['release_id'],first)

    def test_no_shallow_or_unrelated_audit_can_be_staged(self):
        value=json.loads(self.report.read_text());value['deep_exact_duplicates_checked']=False;self.report.write_text(json.dumps(value))
        with self.assertRaises(ValueError):self.stage()
        self.assertIsNone(releases.current(self.store))

    def test_deep_recount_is_not_substituted_by_a_receipt(self):
        with patch('evidence_release.audit',return_value={'status':'FAIL','release_ready':False}):
            with self.assertRaisesRegex(ValueError,'deep warehouse audit failed'):self.stage()
        self.assertIsNone(releases.current(self.store))

    def test_bad_paths_identifiers_and_missing_attribution_are_rejected(self):
        with self.assertRaises(ValueError):releases.storage(releases.ROOT/'public'/'source')
        with self.assertRaises(ValueError):releases.identifier('../../source')
        release=self.stage()['release_id']
        with self.assertRaises(ValueError):releases.activate(self.store,release,None,'')
        (self.store/'releases'/release/'extra.txt').write_text('not an authorized file')
        with self.assertRaises(ValueError):releases.inspect(self.store,release)

    def test_live_wal_and_unrecorded_pointer_are_rejected(self):
        wal=pathlib.Path(str(self.warehouse)+'.wal');wal.write_text('synthetic pending write')
        with self.assertRaisesRegex(ValueError,'immutable warehouse'):self.stage()
        wal.unlink();release=self.stage()['release_id'];releases.activate(self.store,release,None,'Synthetic operator')
        value=releases.current(self.store);value['operator']='Changed';(self.store/'current.json').write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError,'history'):releases.current(self.store)

    def test_failed_pointer_replace_preserves_current_release(self):
        first=self.stage()['release_id'];releases.activate(self.store,first,None,'Synthetic operator')
        second=self.second()['release_id']
        with patch('evidence_release.os.replace',side_effect=OSError('synthetic filesystem failure')):
            with self.assertRaises(OSError):releases.activate(self.store,second,first,'Synthetic operator')
        self.assertEqual(releases.current(self.store)['release_id'],first)
        self.assertFalse((self.store/'.activation.lock').exists())

if __name__=='__main__':unittest.main()
