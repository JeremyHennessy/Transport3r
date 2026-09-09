import importlib.util,json,pathlib,sys,tempfile,unittest
import nationwide_warehouse as w
HAS_DUCKDB=importlib.util.find_spec('duckdb') is not None

class NationwideVerification(unittest.TestCase):
    def test_incomplete_collection_is_never_promoted(self):
        with tempfile.TemporaryDirectory() as root:
            pathlib.Path(root,'manifest.json').write_text(json.dumps({'schema_version':7,'status':'PARTIAL'}))
            with self.assertRaisesRegex(ValueError,'not complete'):list(w.verified_sources(root))
    def test_complete_label_without_all_registered_sources_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            pathlib.Path(root,'manifest.json').write_text(json.dumps({'schema_version':7,'status':'COMPLETE','sources':[]}))
            with self.assertRaisesRegex(ValueError,'coverage'):list(w.verified_sources(root))

@unittest.skipUnless(HAS_DUCKDB,'Install requirements-nationwide.txt for the nationwide mapping gate')
class NationwideMapping(unittest.TestCase):
    def test_import_preserves_every_text_column_and_leading_zero(self):
        import duckdb
        with tempfile.TemporaryDirectory() as root:
            folder=pathlib.Path(root)
            (folder/'rows.csv').write_text('DOT,Policy,Note\n00003706,000123,"First, second"\n',encoding='utf-8')
            fields=['dot_number','policy','note']
            (folder/'metadata.json').write_text(json.dumps({'metadata':{'columns':[{'fieldName':f} for f in fields]}}))
            db=duckdb.connect();db.execute('CREATE TABLE source_lineage(source_id VARCHAR,cut VARCHAR,sha256 VARCHAR,available_at VARCHAR,rows_updated_at BIGINT,row_count BIGINT)')
            w.load_source(db,folder,{'id':'az4n-8mr2','metadata_after':'metadata.json','path':'rows.csv','row_count':1,'sha256':'fixture','available_at':'2026-09-09T00:00:00Z','rows_updated_at':1})
            self.assertEqual(db.execute('SELECT dot_number,policy,note FROM raw_az4n_8mr2').fetchone(),('00003706','000123','First, second'))
            db.close()
    def test_all_rows_retained_and_ambiguous_or_foreign_children_not_assigned(self):
        import duckdb
        db=duckdb.connect()
        schemas={'fx4q-ay7w':['inspection_id','dot_number'],'6eyk-hxee':['docket_number','dot_number'],'wt8s-2hbx':['inspection_id','dot_number'],'ypjt-5ydn':['prefix_docket_number']}
        for source,fields in schemas.items():db.execute(f'CREATE TABLE {w.table(source)} (_warehouse_row_id BIGINT,'+','.join(f'{f} VARCHAR' for f in fields)+')')
        db.execute("INSERT INTO raw_fx4q_ay7w VALUES (1,'10','3706'),(2,'20','1'),(3,'20','2')")
        db.execute("INSERT INTO raw_6eyk_hxee VALUES (1,'MC00123','00003706'),(2,'MC123','1'),(3,'MC123','2')")
        db.execute("INSERT INTO raw_wt8s_2hbx VALUES (1,'10',NULL),(2,'20',NULL),(3,'99',NULL),(4,'10','2'),(5,'10','bad')")
        db.execute("INSERT INTO raw_ypjt_5ydn VALUES (1,'MC00123'),(2,'MC123'),(3,'MC0123')")
        audit=w.map_sources(db,schemas)
        self.assertEqual(db.execute('SELECT _dot_number FROM carrier_wt8s_2hbx ORDER BY _warehouse_row_id').fetchall(),[('3706',),(None,),(None,),(None,),(None,)])
        self.assertEqual(db.execute('SELECT _dot_number FROM carrier_ypjt_5ydn ORDER BY _warehouse_row_id').fetchall(),[('3706',),(None,),(None,)])
        self.assertEqual(sum(sum(a['counts'].values()) for a in audit),14)
        db.close()

if __name__=='__main__':unittest.main()
