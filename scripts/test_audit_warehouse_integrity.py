"""Regression tests for immutable warehouse audit and fail-closed source accounting."""
import json
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
from audit_warehouse_integrity import audit


class WarehouseIntegrityAuditTests(unittest.TestCase):
    def setUp(self):
        import duckdb
        self.temp=tempfile.TemporaryDirectory()
        self.path=pathlib.Path(self.temp.name)/'test.duckdb'
        db=duckdb.connect(str(self.path))
        db.execute('CREATE TABLE source_lineage(source_id VARCHAR,sha256 VARCHAR,published_rows BIGINT,acquired_rows BIGINT,warehouse_rows BIGINT)')
        db.execute("INSERT INTO source_lineage VALUES ('abcd-1234','sha-test',2,2,2)")
        db.execute('CREATE TABLE raw_abcd_1234(_warehouse_row_id BIGINT, dot VARCHAR, event VARCHAR)')
        db.execute("INSERT INTO raw_abcd_1234 VALUES (1,'123','A'),(2,'123','A')")
        db.execute('CREATE TABLE mapping_abcd_1234(_warehouse_row_id BIGINT,_mapping_status VARCHAR,_mapping_reason VARCHAR)')
        db.execute("INSERT INTO mapping_abcd_1234 VALUES (1,'RESOLVED','DIRECT_ID_CENSUS_RESOLVED'),(2,'RESOLVED','DIRECT_ID_CENSUS_RESOLVED')")
        self.receipt={'sources':1,'rows':2,'cut_id':'test','source_acceptance':[{
            'source':'abcd-1234','sha256':'sha-test','warehouse_rows':2,
            'mapping_status':{'RESOLVED':2},'mapping_reasons':{'DIRECT_ID_CENSUS_RESOLVED':2},
            'exact_duplicate_rows':1}]}
        db.execute('CREATE TABLE warehouse_acceptance(acceptance_json VARCHAR)')
        db.execute('INSERT INTO warehouse_acceptance VALUES (?)',[json.dumps(self.receipt)])
        db.close()

    def tearDown(self):
        self.temp.cleanup()

    def test_clean_counts_and_exact_duplicates(self):
        result=audit(self.path,deep=True)
        self.assertEqual(result['status'],'PASS',result['failures'])
        self.assertEqual(result['raw_rows'],2)
        self.assertEqual(result['source_count'],1)

    def test_duplicate_receipt_mismatch_fails(self):
        import duckdb
        db=duckdb.connect(str(self.path))
        changed=dict(self.receipt)
        changed['source_acceptance']=[dict(self.receipt['source_acceptance'][0],exact_duplicate_rows=0)]
        db.execute('UPDATE warehouse_acceptance SET acceptance_json=?',[json.dumps(changed)])
        db.close()
        self.assertIn('abcd-1234: exact_duplicates',audit(self.path,deep=True)['failures'])

    def test_mapping_multiplier_fails(self):
        import duckdb
        db=duckdb.connect(str(self.path))
        db.execute("INSERT INTO mapping_abcd_1234 VALUES (2,'RESOLVED','DIRECT_ID_CENSUS_RESOLVED')")
        db.close()
        self.assertIn('abcd-1234: mapping_cardinality',audit(self.path)['failures'])

    def test_missing_mapping_fails(self):
        import duckdb
        db=duckdb.connect(str(self.path))
        db.execute('DELETE FROM mapping_abcd_1234 WHERE _warehouse_row_id=2')
        db.close()
        self.assertIn('abcd-1234: mapping_cardinality',audit(self.path)['failures'])

    def test_provenance_mismatch_fails(self):
        import duckdb
        db=duckdb.connect(str(self.path))
        db.execute("UPDATE source_lineage SET sha256='tampered'")
        db.close()
        self.assertIn('abcd-1234: provenance',audit(self.path)['failures'])


if __name__=='__main__':
    unittest.main()
