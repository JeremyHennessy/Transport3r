"""Fail-closed tests against the actual 36-source acceptance contract."""
import json
import pathlib
import tempfile
import unittest

import duckdb
from audit_warehouse_integrity import audit
from test_nationwide_evidence import NationwideEvidence


class WarehouseIntegrityAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = pathlib.Path(self.temp.name, 'test.duckdb')
        NationwideEvidence().fixture(self.path)
        db = duckdb.connect(str(self.path))
        receipt = json.loads(db.execute('SELECT acceptance_json FROM warehouse_acceptance').fetchone()[0])
        db.execute('CREATE TABLE source_lineage(source_id VARCHAR,cut VARCHAR,sha256 VARCHAR,available_at VARCHAR,'
                   'rows_updated_at BIGINT,published_rows BIGINT,acquired_rows BIGINT,warehouse_rows BIGINT)')
        for item in receipt['source_lineage']:
            db.execute('INSERT INTO source_lineage VALUES (?,?,?,?,?,?,?,?)', [item[key] for key in (
                'source', 'cut', 'sha256', 'available_at', 'rows_updated_at', 'published_rows', 'acquired_rows', 'warehouse_rows')])
            suffix = item['source'].replace('-', '_')
            db.execute(f'CREATE VIEW carrier_{suffix} AS SELECT r.*,m.* EXCLUDE (_warehouse_row_id) '
                       f'FROM raw_{suffix} r JOIN mapping_{suffix} m USING (_warehouse_row_id)')
        for item in receipt['source_acceptance']:
            item['exact_duplicate_rows'] = 0
        receipt['census_carriers'] = 1
        db.execute('UPDATE warehouse_acceptance SET acceptance_json=?', [json.dumps(receipt)])
        db.close()

    def sql(self, query):
        db = duckdb.connect(str(self.path))
        try:
            db.execute(query)
        finally:
            db.close()

    def change_receipt(self, change):
        db = duckdb.connect(str(self.path))
        try:
            receipt = json.loads(db.execute('SELECT acceptance_json FROM warehouse_acceptance').fetchone()[0])
            change(receipt)
            db.execute('UPDATE warehouse_acceptance SET acceptance_json=?', [json.dumps(receipt)])
        finally:
            db.close()

    def failed(self, text=None, deep=False):
        result = audit(self.path, deep=deep)
        self.assertEqual(result['status'], 'FAIL', result)
        self.assertFalse(result['release_ready'])
        if text:
            self.assertIn(text, ' '.join(result['failures']))
        return result

    def test_clean_counts_and_exact_duplicates(self):
        result = audit(self.path, deep=True)
        self.assertEqual(result['status'], 'PASS', result['failures'])
        self.assertTrue(result['release_ready'])
        self.assertEqual(result['source_count'], 36)
        self.assertEqual(result['raw_rows'], 3)
        self.assertEqual(result['census_carriers'], 1)
        self.assertNotIn(str(self.temp.name), json.dumps(result))

    def test_shallow_pass_never_certifies_duplicate_metrics(self):
        result = audit(self.path)
        self.assertEqual(result['status'], 'PASS', result['failures'])
        self.assertFalse(result['release_ready'])
        self.assertIsNone(result['duplicate_rule'])
        self.assertTrue(all(row['exact_duplicate_rows'] is None and row['distinct_source_rows'] is None
                            for row in result['sources']))

    def test_non_verified_receipt(self):
        self.change_receipt(lambda r: r.update(status='REJECTED'))
        self.failed('acceptance_receipt')

    def test_failed_gate(self):
        self.change_receipt(lambda r: r['acceptance_gates'].update(source_coverage='FAIL'))
        self.failed('acceptance_receipt')

    def test_missing_gate(self):
        self.change_receipt(lambda r: r['acceptance_gates'].pop('row_mapping_accounting'))
        self.failed('acceptance_receipt')

    def test_published_receipt_count(self):
        self.change_receipt(lambda r: r['source_acceptance'][0].update(published_rows=999))
        self.failed('acceptance_receipt')

    def test_acquired_receipt_count(self):
        self.change_receipt(lambda r: r['source_acceptance'][0].update(acquired_rows=999))
        self.failed('acceptance_receipt')

    def test_multiple_receipts(self):
        self.sql('INSERT INTO warehouse_acceptance SELECT * FROM warehouse_acceptance')
        self.failed('acceptance_receipt')

    def test_registry_source_omission(self):
        self.change_receipt(lambda r: r['source_acceptance'].pop())
        self.failed('acceptance_receipt')

    def test_physical_lineage_omission(self):
        self.sql("DELETE FROM source_lineage WHERE source_id='aayw-vxb3'")
        self.failed('source_coverage')

    def test_duplicate_physical_lineage(self):
        self.sql("INSERT INTO source_lineage SELECT * FROM source_lineage WHERE source_id='aayw-vxb3'")
        self.failed('source_coverage')

    def test_mapping_multiplier(self):
        self.sql("INSERT INTO mapping_fx4q_ay7w SELECT * FROM mapping_fx4q_ay7w WHERE _warehouse_row_id=1")
        self.failed('mapping_cardinality')

    def test_missing_mapping(self):
        self.sql('DELETE FROM mapping_fx4q_ay7w WHERE _warehouse_row_id=2')
        self.failed('mapping_cardinality')

    def test_orphan_mapping_even_when_counts_unchanged(self):
        self.sql('UPDATE mapping_fx4q_ay7w SET _warehouse_row_id=99 WHERE _warehouse_row_id=2')
        self.failed('mapping_cardinality')

    def test_duplicate_raw_row_identity(self):
        self.sql('UPDATE raw_fx4q_ay7w SET _warehouse_row_id=1 WHERE _warehouse_row_id=2')
        self.failed('raw_identity')

    def test_installed_view_loses_records(self):
        self.sql('CREATE OR REPLACE VIEW carrier_fx4q_ay7w AS SELECT * FROM raw_fx4q_ay7w WHERE false')
        self.failed('joined_rows')

    def test_actual_counts_mismatch(self):
        self.sql("INSERT INTO raw_fx4q_ay7w VALUES (3,'unexpected')")
        self.failed('source_counts')

    def test_provenance_mismatch(self):
        self.sql("UPDATE source_lineage SET sha256=repeat('a',64) WHERE source_id='fx4q-ay7w'")
        self.failed('provenance')

    def test_blank_mapping_reason(self):
        self.sql("UPDATE mapping_fx4q_ay7w SET _mapping_reason='' WHERE _warehouse_row_id=2")
        self.failed('mapping_reasons')

    def test_wrong_census_carrier_total(self):
        self.change_receipt(lambda r: r.update(census_carriers=2))
        self.failed('census_carriers')

    def test_exact_duplicate_mismatch_is_not_silently_corrected(self):
        self.sql("UPDATE raw_fx4q_ay7w SET payload='same'")
        result = self.failed('exact_duplicates', deep=True)
        row = next(s for s in result['sources'] if s['source']=='fx4q-ay7w')
        self.assertEqual(row['exact_duplicate_rows'], 1)
        db = duckdb.connect(str(self.path), read_only=True)
        try:
            receipt = json.loads(db.execute('SELECT acceptance_json FROM warehouse_acceptance').fetchone()[0])
            self.assertEqual(next(s for s in receipt['source_acceptance'] if s['source']=='fx4q-ay7w')['exact_duplicate_rows'], 0)
        finally:
            db.close()


if __name__ == '__main__':
    unittest.main()
