"""Fail-closed tests against the actual 36-source acceptance contract."""
import hashlib
import json
import pathlib
import tempfile
import unittest

import duckdb
from audit_warehouse_integrity import audit
import nationwide_warehouse as warehouse
from source_contract import source_contracts, catalog_sources


def make_fixture(path):
    """Synthetic public-source shapes only; never publish this as acquisition evidence."""
    db = duckdb.connect(str(path))
    contracts = source_contracts()
    schemas = {}
    extra = {'fx4q-ay7w':['inspection_id','payload'], '6eyk-hxee':['docket_number'], 'wt8s-2hbx':['dot_number']}
    for sid, contract in contracts.items():
        fields = list(dict.fromkeys([contract['identity']['field']] + contract['event_date_fields'] + extra.get(sid, [])))
        schemas[sid] = fields
        db.execute(f'CREATE TABLE {warehouse.table(sid)} (_warehouse_row_id BIGINT,' + ','.join(warehouse.ident(f)+' VARCHAR' for f in fields) + ')')
    db.execute("INSERT INTO raw_az4n_8mr2 (_warehouse_row_id,dot_number) VALUES (1,'3706'),(2,'123')")
    db.execute("INSERT INTO raw_fx4q_ay7w (_warehouse_row_id,dot_number,inspection_id,payload) VALUES (1,'3706','10','resolved'),(2,'999','20','identified')")
    db.execute("INSERT INTO raw_6eyk_hxee (_warehouse_row_id,dot_number,docket_number) VALUES (1,'00003706','MC0001')")
    db.execute("INSERT INTO raw_wt8s_2hbx (_warehouse_row_id,inspection_id) VALUES (1,'10'),(2,'20')")
    db.execute("INSERT INTO raw_ypjt_5ydn (_warehouse_row_id,prefix_docket_number) VALUES (1,'MC0001')")
    mapped = {row['source']:row for row in warehouse.map_sources(db, schemas)}
    db.execute('CREATE TABLE source_lineage(source_id VARCHAR,cut VARCHAR,sha256 VARCHAR,available_at VARCHAR,'
               'rows_updated_at BIGINT,published_rows BIGINT,acquired_rows BIGINT,warehouse_rows BIGINT)')
    lineage, accepted = [], []
    for source in catalog_sources():
        sid = source['id']; row = mapped[sid]; n = row['rows']
        item = {'source':sid, 'cut':f'/synthetic/{sid}/cut', 'sha256':hashlib.sha256(sid.encode()).hexdigest(),
                'available_at':'2026-10-23T00:00:00Z', 'rows_updated_at':1,
                'published_rows':n,'acquired_rows':n,'warehouse_rows':n}
        lineage.append(item)
        db.execute('INSERT INTO source_lineage VALUES (?,?,?,?,?,?,?,?)', list(item.values()))
        accepted.append({**item, **row, 'count_gate':'PASS','reason_gate':'PASS'})
    receipt = {'status':'VERIFIED', 'cut_id':'synthetic-test-cut', 'cut_available_at':'2026-10-23T00:01:00Z',
               'scope':'ALL_PUBLISHED_ROWS_ALL_REGISTERED_SOURCES','identity_contract':'FMCSA_CARRIER_IDENTITY_1',
               'sources':36,'rows':8,'census_carriers':2,'source_lineage':lineage,'source_acceptance':accepted,
               'acceptance_gates':{k:'PASS' for k in ('source_coverage','published_acquired_warehouse_counts',
                    'row_mapping_accounting','unresolved_reason_accounting','arbitrary_assignment_prevention')},
               'mapping_totals':{'resolved':6,'identified_only':2,'unresolved':0},
               'sms_release_binding':'UNVERIFIED','historical_feature_validity':'NOT_CERTIFIED'}
    db.execute('CREATE TABLE warehouse_acceptance(acceptance_json VARCHAR)')
    db.execute('INSERT INTO warehouse_acceptance VALUES (?)',[json.dumps(receipt)])
    db.close()


class WarehouseIntegrityAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = pathlib.Path(self.temp.name, 'test.duckdb')
        make_fixture(self.path)

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
        self.assertEqual(result['raw_rows'], 8)
        self.assertEqual(result['census_carriers'], 2)
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
        self.sql("INSERT INTO raw_fx4q_ay7w (_warehouse_row_id,payload) VALUES (3,'unexpected')")
        self.failed('source_counts')

    def test_provenance_mismatch(self):
        self.sql("UPDATE source_lineage SET sha256=repeat('a',64) WHERE source_id='fx4q-ay7w'")
        self.failed('provenance')

    def test_blank_mapping_reason(self):
        self.sql("UPDATE mapping_fx4q_ay7w SET _mapping_reason='' WHERE _warehouse_row_id=2")
        self.failed('mapping_reasons')

    def test_wrong_census_carrier_total(self):
        self.change_receipt(lambda r: r.update(census_carriers=99))
        self.failed('census_carriers')

    def test_same_count_wrong_carrier_assignment_fails_deep_audit(self):
        self.sql("UPDATE mapping_fx4q_ay7w SET _dot_number='123' WHERE _warehouse_row_id=1")
        self.failed('identity_mapping', deep=True)

    def test_child_and_docket_reassignment_fails_deep_audit(self):
        self.sql("UPDATE mapping_wt8s_2hbx SET _dot_number='123' WHERE _warehouse_row_id=1")
        self.sql("UPDATE mapping_ypjt_5ydn SET _dot_number='123'")
        self.failed('identity_mapping', deep=True)

    def test_exact_duplicate_mismatch_is_not_silently_corrected(self):
        self.sql("UPDATE raw_fx4q_ay7w SET payload='same',dot_number='3706',inspection_id='10'")
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
