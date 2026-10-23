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
    def test_canonical_dot_accepts_only_positive_integer_renderings(self):
        import duckdb
        db=duckdb.connect()
        values=[' 00003706.00 ','3706','0','000.0','3706.5','bad',None]
        actual=[row[0] for row in db.execute(f"SELECT {w.canonical('value')} FROM (SELECT unnest(?) AS value)",[values]).fetchall()]
        self.assertEqual(actual,['3706','3706',None,None,None,None,None])
        db.close()
    def test_date_quality_matches_supported_fmcsa_encodings(self):
        import duckdb
        db=duckdb.connect()
        db.execute('CREATE TABLE raw_dates(value VARCHAR)')
        db.executemany('INSERT INTO raw_dates VALUES (?)',[(value,) for value in ['20261023','10232026','20261023 1230','10/23/2026','23-Oct-26','23-Oct-2026','2026-10-23T12:30:00.000','bad',None]])
        result=w.date_quality(db,'raw_dates',['value'],['value'])[0]
        self.assertEqual((result['rows'],result['missing'],result['valid'],result['invalid']),(9,1,7,1))
        self.assertEqual((result['earliest'],result['latest']),('2026-10-23','2026-10-23'))
        db.close()
    def test_import_preserves_every_text_column_and_leading_zero(self):
        import duckdb
        with tempfile.TemporaryDirectory() as root:
            folder=pathlib.Path(root)
            (folder/'rows.csv').write_text('DOT,Policy,Note\n00003706,000123,"First, second"\n',encoding='utf-8')
            fields=['dot_number','policy','note']
            (folder/'metadata.json').write_text(json.dumps({'row_count':1,'metadata':{'columns':[{'fieldName':f} for f in fields]}}))
            db=duckdb.connect();db.execute('CREATE TABLE source_lineage(source_id VARCHAR,cut VARCHAR,sha256 VARCHAR,available_at VARCHAR,rows_updated_at BIGINT,published_rows BIGINT,acquired_rows BIGINT,warehouse_rows BIGINT)')
            w.load_source(db,folder,{'id':'az4n-8mr2','metadata_after':'metadata.json','path':'rows.csv','row_count':1,'sha256':'fixture','available_at':'2026-09-09T00:00:00Z','rows_updated_at':1})
            self.assertEqual(db.execute('SELECT dot_number,policy,note FROM raw_az4n_8mr2').fetchone(),('00003706','000123','First, second'))
            db.close()
    def test_all_rows_retained_and_ambiguous_or_foreign_children_not_assigned(self):
        import duckdb
        db=duckdb.connect()
        primary_fields={'az4n-8mr2':['dot_number'],'aayw-vxb3':['dot_number'],
                        'fx4q-ay7w':['inspection_id','dot_number'],'6eyk-hxee':['docket_number','dot_number'],
                        'wt8s-2hbx':['inspection_id','dot_number'],'ypjt-5ydn':['prefix_docket_number']}
        contracts=w.source_contracts()
        schemas={source:list(dict.fromkeys(fields+contracts[source]['event_date_fields']))
                 for source,fields in primary_fields.items()}
        for source,fields in schemas.items():db.execute(f'CREATE TABLE {w.table(source)} (_warehouse_row_id BIGINT,'+','.join(f'{f} VARCHAR' for f in fields)+')')
        db.execute("INSERT INTO raw_az4n_8mr2 (_warehouse_row_id,dot_number,mcs150_date) VALUES (1,'3706','20260101'),(2,'1','20260101'),(3,'2','20260101'),(4,'2','20260101')")
        db.execute("INSERT INTO raw_aayw_vxb3 (_warehouse_row_id,dot_number,report_date) VALUES (1,'3706','20260101'),(2,'99','bad'),(3,'2','20260102')")
        db.execute("INSERT INTO raw_fx4q_ay7w (_warehouse_row_id,inspection_id,dot_number,insp_date) VALUES (1,'10','3706','20260101'),(2,'20','1','20260101'),(3,'20','2','20260101')")
        db.execute("INSERT INTO raw_6eyk_hxee (_warehouse_row_id,docket_number,dot_number) VALUES (1,'MC00123','00003706'),(2,'MC123','1'),(3,'MC123','2')")
        db.execute("INSERT INTO raw_wt8s_2hbx (_warehouse_row_id,inspection_id,dot_number) VALUES (1,'10',NULL),(2,'20',NULL),(3,'99',NULL),(4,'10','2'),(5,'10','bad')")
        db.execute("INSERT INTO raw_ypjt_5ydn (_warehouse_row_id,prefix_docket_number,effective_date) VALUES (1,' mc00123 ','20260101'),(2,'MC123',NULL),(3,'MC0123','bad')")
        audit=w.map_sources(db,schemas)
        self.assertEqual(db.execute('SELECT _dot_number FROM carrier_wt8s_2hbx ORDER BY _warehouse_row_id').fetchall(),[('3706',),(None,),(None,),(None,),(None,)])
        self.assertEqual(db.execute('SELECT _dot_number FROM carrier_ypjt_5ydn ORDER BY _warehouse_row_id').fetchall(),[('3706',),(None,),(None,)])
        self.assertEqual(db.execute('SELECT _mapping_reason FROM carrier_wt8s_2hbx ORDER BY _warehouse_row_id').fetchall(),
                         [('INSPECTION_PARENT_CENSUS_RESOLVED',),('DUPLICATE_PARENT',),('MISSING_PARENT',),('CHILD_DOT_CONFLICT',),('CHILD_DOT_INVALID',)])
        self.assertEqual(db.execute('SELECT _mapping_reason FROM carrier_ypjt_5ydn ORDER BY _warehouse_row_id').fetchall(),
                         [('DOCKET_CENSUS_RESOLVED',),('DOCKET_MULTIPLE_OWNERS',),('DOCKET_NOT_FOUND',)])
        self.assertEqual(db.execute('SELECT _mapping_status,_mapping_reason FROM carrier_aayw_vxb3 ORDER BY _warehouse_row_id').fetchall(),
                         [('RESOLVED','DIRECT_ID_CENSUS_RESOLVED'),('IDENTIFIED_ONLY','DIRECT_ID_NO_CENSUS_RECORD'),('IDENTIFIED_ONLY','DIRECT_ID_AMBIGUOUS_CENSUS')])
        self.assertEqual(sum(a['rows'] for a in audit),21)
        crash=next(a for a in audit if a['source']=='aayw-vxb3')
        self.assertEqual(crash['date_quality'][0]['invalid'],1)
        db.close()

if __name__=='__main__':unittest.main()
