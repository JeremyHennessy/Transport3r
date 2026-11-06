"""Regression: exact duplicates exclude ingestion row ID."""
import pathlib,sys,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
from nationwide_warehouse import duplicate_rows
class DuplicateAuditTests(unittest.TestCase):
    def setUp(self):
        import duckdb
        self.db=duckdb.connect(':memory:')
        self.db.execute('CREATE TABLE raw_test (_warehouse_row_id BIGINT, dot VARCHAR, code VARCHAR, note VARCHAR)')
    def tearDown(self): self.db.close()
    def test_unique(self):
        self.db.execute("INSERT INTO raw_test VALUES (1,'123','A','x'),(2,'123','B','x'),(3,'456','A','x')")
        self.assertEqual(duplicate_rows(self.db,'raw_test'),0)
    def test_repeats(self):
        self.db.execute("INSERT INTO raw_test VALUES (1,'123','A','x'),(2,'123','A','x'),(3,'123','A','x'),(4,'123','B','x')")
        self.assertEqual(duplicate_rows(self.db,'raw_test'),2)
    def test_nulls(self):
        self.db.execute("INSERT INTO raw_test VALUES (1,'123',NULL,NULL),(2,'123',NULL,NULL),(3,'123',NULL,'different'),(4,'456',NULL,NULL)")
        self.assertEqual(duplicate_rows(self.db,'raw_test'),1)
if __name__=='__main__': unittest.main()
