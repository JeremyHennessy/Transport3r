import importlib.util,hashlib,json,pathlib,tempfile,threading,unittest,urllib.error,urllib.request

HAS_DUCKDB=importlib.util.find_spec('duckdb') is not None


@unittest.skipUnless(HAS_DUCKDB,'Install requirements-nationwide.txt for the nationwide API gate')
class NationwideEvidence(unittest.TestCase):
    def fixture(self,path):
        import duckdb
        from source_contract import catalog_sources
        from nationwide_warehouse import table
        db=duckdb.connect(str(path));lineage=[]
        for source in catalog_sources():
            sid=source['id'];raw=table(sid);mapping=raw.replace('raw_','mapping_')
            count=1 if sid=='az4n-8mr2' else 2 if sid=='fx4q-ay7w' else 0
            extra=',dot_number VARCHAR' if sid=='az4n-8mr2' else ',payload VARCHAR'
            db.execute(f'CREATE TABLE {raw}(_warehouse_row_id BIGINT{extra})')
            db.execute(f'CREATE TABLE {mapping}(_warehouse_row_id BIGINT,_dot_number VARCHAR,_mapping_status VARCHAR,_mapping_reason VARCHAR)')
            lineage.append({'source':sid,'cut':f'/tmp/collection/{sid}/cut','sha256':hashlib.sha256(sid.encode()).hexdigest(),'available_at':'2026-10-23T00:00:00Z','rows_updated_at':1,'published_rows':count,'acquired_rows':count,'warehouse_rows':count})
        db.execute("INSERT INTO raw_az4n_8mr2 VALUES (1,'3706')")
        db.execute("INSERT INTO mapping_az4n_8mr2 VALUES (1,'3706','RESOLVED','CENSUS_SELF_RESOLVED')")
        db.execute("INSERT INTO raw_fx4q_ay7w VALUES (1,'resolved'),(2,'ambiguous')")
        db.execute("INSERT INTO mapping_fx4q_ay7w VALUES (1,'3706','RESOLVED','DIRECT_ID_CENSUS_RESOLVED'),(2,'3706','IDENTIFIED_ONLY','DIRECT_ID_AMBIGUOUS_CENSUS')")
        source_acceptance=[]
        for item in lineage:
            count=item['warehouse_rows'];statuses={};reasons={}
            if item['source']=='az4n-8mr2':statuses={'RESOLVED':1};reasons={'CENSUS_SELF_RESOLVED':1}
            elif item['source']=='fx4q-ay7w':statuses={'RESOLVED':1,'IDENTIFIED_ONLY':1};reasons={'DIRECT_ID_CENSUS_RESOLVED':1,'DIRECT_ID_AMBIGUOUS_CENSUS':1}
            source_acceptance.append({'source':item['source'],'sha256':item['sha256'],'rows_updated_at':item['rows_updated_at'],'published_rows':count,'acquired_rows':count,'warehouse_rows':count,'mapping_status':statuses,'mapping_reasons':reasons,'count_gate':'PASS','reason_gate':'PASS'})
        receipt={'status':'VERIFIED','cut_id':'cut-1','cut_available_at':'2026-10-23T00:01:00Z','scope':'ALL_PUBLISHED_ROWS_ALL_REGISTERED_SOURCES','identity_contract':'FMCSA_CARRIER_IDENTITY_1','sources':36,'rows':3,'source_lineage':lineage,'source_acceptance':source_acceptance,
                 'acceptance_gates':{'source_coverage':'PASS','published_acquired_warehouse_counts':'PASS','row_mapping_accounting':'PASS','unresolved_reason_accounting':'PASS','arbitrary_assignment_prevention':'PASS'},
                 'mapping_totals':{'resolved':2,'identified_only':1,'unresolved':0},
                 'sms_release_binding':'UNVERIFIED','historical_feature_validity':'NOT_CERTIFIED'}
        db.execute('CREATE TABLE warehouse_acceptance(acceptance_json VARCHAR)');db.execute('INSERT INTO warehouse_acceptance VALUES (?)',[json.dumps(receipt)]);db.close()

    def test_api_returns_only_census_resolved_rows_and_all_source_receipts(self):
        from nationwide_evidence import read
        with tempfile.TemporaryDirectory() as root:
            path=pathlib.Path(root,'warehouse.duckdb');self.fixture(path)
            result=read(path,'3706')
            self.assertEqual(result['source_count'],36);self.assertEqual(result['carrier_rows'],2)
            self.assertEqual(result['cut_available_at'],'2026-10-23T00:01:00Z')
            inspection=next(row for row in result['sources'] if row['source_id']=='fx4q-ay7w')
            self.assertEqual(inspection['carrier_rows'],1);self.assertEqual(inspection['rows'],[{'payload':'resolved'}])
            self.assertTrue(result['completeness_receipt']['unresolved_rows_excluded_from_carrier_assignment'])
            self.assertEqual(result['completeness_receipt']['mapping_totals'],{'resolved':2,'identified_only':1,'unresolved':0})
            with self.assertRaisesRegex(ValueError,'uniquely resolved'):read(path,'999')

    def test_acceptance_rejects_lineage_or_mapping_total_tampering(self):
        import duckdb
        from nationwide_evidence import acceptance
        with tempfile.TemporaryDirectory() as root:
            path=pathlib.Path(root,'warehouse.duckdb');self.fixture(path)
            db=duckdb.connect(str(path))
            receipt=json.loads(db.execute('SELECT acceptance_json FROM warehouse_acceptance').fetchone()[0])
            receipt['source_lineage'][0]['warehouse_rows']+=1
            db.execute('UPDATE warehouse_acceptance SET acceptance_json=?',[json.dumps(receipt)]);db.close()
            db=duckdb.connect(str(path),read_only=True)
            try:
                with self.assertRaisesRegex(ValueError,'source count acceptance'):acceptance(db)
            finally:db.close()

    def test_http_health_and_carrier_routes_fail_closed(self):
        from evidence_api import EvidenceServer,Handler
        with tempfile.TemporaryDirectory() as root:
            path=pathlib.Path(root,'warehouse.duckdb');self.fixture(path)
            server=EvidenceServer(('127.0.0.1',0),Handler,path,'https://example.test')
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            try:
                base=f'http://127.0.0.1:{server.server_port}'
                with urllib.request.urlopen(base+'/healthz') as response:
                    health=json.load(response);self.assertEqual(health['status'],'ok');self.assertEqual(response.headers['Access-Control-Allow-Origin'],'https://example.test')
                with urllib.request.urlopen(base+'/v1/carriers/3706/evidence') as response:self.assertEqual(json.load(response)['carrier_rows'],2)
                with self.assertRaises(urllib.error.HTTPError) as missing:urllib.request.urlopen(base+'/v1/carriers/999/evidence')
                self.assertEqual(missing.exception.code,404)
            finally:server.shutdown();server.server_close();thread.join()


if __name__=='__main__':unittest.main()
