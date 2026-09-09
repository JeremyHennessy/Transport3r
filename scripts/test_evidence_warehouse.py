import json
import pathlib
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import cohort_snapshot as cs
import evidence_warehouse as warehouse
from snapshot_store import write_once
from verify_snapshot import verify as verify_snapshot


class WarehouseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        self.db = self.root/'curated/evidence.sqlite'

    def fixture(self, extended=True):
        cut = self.root/'cut'; cut.mkdir()
        cohort = {'selected_at':'2026-08-31T19:00:00Z','dots':['1']}
        write_once(cut/'cohort.json',cohort)
        profile = 'underwriting_evidence_v1' if extended else 'baseline'
        sources = []
        for sid in cs.PROFILES[profile]:
            rows = [{cs.DOT_FIELDS.get(sid,'dot_number'):'1','source_row_id':'row1','inspection_id':'a','crash_id':'b',
                     'status_code':'A','insp_date':'20260830','report_date':'20260830','oos_total':'0'}]
            page = f'{sid}.page.json'; write_once(cut/page,rows)
            before = {'observed_at':'2026-08-31T20:01:00Z','rows_updated_at':123,'schema_sha256':'schema','table_id':'table','row_count':1}
            after = {**before,'observed_at':'2026-08-31T20:02:00Z'}
            lineage = f'{sid}.lineage.json'
            write_once(cut/lineage,{'before':before,'after':after,'where':cs.cohort_where(sid,['1']),'order':':id','select':'*, :id as source_row_id'})
            sources.append({'id':sid,'status':'COMPLETE','started_at':'2026-08-31T20:00:00Z','available_at':'2026-08-31T21:00:00Z',
                            'row_count':1,'lineage':lineage,'lineage_sha256':cs.hash_file(cut/lineage),
                            'pages':[{'path':page,'sha256':cs.hash_file(cut/page),'rows':1,'offset':0}]})
        manifest = {'schema_version':4 if extended else 3,'status':'COMPLETE','acquisition_kind':'CURRENT_COHORT_PUBLIC_SOURCE','historical_reconstruction':False,
                    'snapshot_id':'cut','started_at':'2026-08-31T19:00:00Z','completed_at':'2026-08-31T22:00:00Z',
                    'cohort_path':'cohort.json','cohort_sha256':cs.hash_file(cut/'cohort.json'),'datasets':sources}
        if extended: manifest.update(source_profile=profile,max_rows_per_source=100000)
        write_once(cut/'manifest.json',manifest)
        return cut

    def rewrite(self,path,value):
        path.write_text(json.dumps(value)+'\n',encoding='utf-8')

    def test_extended_and_legacy_cuts_remain_readable(self):
        cut = self.fixture()
        self.assertEqual(len(cs.load_verified(cut)[2]),14)
        self.assertEqual(verify_snapshot(cut)['source_count'],14)
        warehouse.promote(cut,self.db)
        result = warehouse.carrier_evidence(self.db,'1','2026-08-31T23:00:00Z',include_records=True)
        self.assertEqual(len(result['sources']),14)
        motus = next(source for source in result['sources'] if source['source_id']=='inys-ebih')
        self.assertEqual(motus['rows'][0]['usdot_number'],'1')
        self.assertFalse(motus['browser_cap_applied'])
        self.assertIsNone(result['risk_score'])
        legacy = json.loads((cut/'manifest.json').read_text())
        legacy.update(schema_version=3,datasets=legacy['datasets'][:7])
        legacy.pop('source_profile')
        self.rewrite(cut/'manifest.json',legacy)
        self.assertEqual(len(cs.load_verified(cut)[2]),7)

    def test_complete_profile_cannot_omit_extended_sources(self):
        cut = self.fixture()
        m = json.loads((cut/'manifest.json').read_text()); m['datasets'].pop()
        self.rewrite(cut/'manifest.json',m)
        with self.assertRaisesRegex(ValueError,'source set'):
            warehouse.promote(cut,self.db)
        self.assertFalse(self.db.exists())

    def test_raw_tampering_and_changed_query_scope_fail(self):
        cut = self.fixture()
        path = cut/'az4n-8mr2.page.json'; original = path.read_text(); path.write_text('[]')
        with self.assertRaisesRegex(ValueError,'hash'):
            warehouse.promote(cut,self.db)
        path.write_text(original,encoding='utf-8')
        m = json.loads((cut/'manifest.json').read_text())
        source = m['datasets'][0]; path = cut/source['lineage']
        lineage = json.loads(path.read_text()); lineage['where'] = "dot_number='2'"
        self.rewrite(path,lineage); source['lineage_sha256'] = cs.hash_file(path)
        self.rewrite(cut/'manifest.json',m)
        with self.assertRaisesRegex(ValueError,'scope'):
            warehouse.promote(cut,self.db)

    def test_idempotent_import_does_not_duplicate_rows(self):
        cut = self.fixture()
        self.assertEqual(warehouse.promote(cut,self.db)['promotion'],'INSERTED')
        self.assertEqual(warehouse.promote(cut,self.db)['promotion'],'ALREADY_PRESENT')
        result = warehouse.verify(self.db)
        self.assertEqual(len(result['cuts']),1)
        self.assertEqual(result['cuts'][0]['total_rows'],14)

    def test_changed_manifest_cannot_replace_an_existing_cut(self):
        cut = self.fixture(); warehouse.promote(cut,self.db)
        path = cut/'manifest.json'; m = json.loads(path.read_text()); m['extra']='changed'
        self.rewrite(path,m)
        with self.assertRaisesRegex(ValueError,'already exists'):
            warehouse.promote(cut,self.db)
        self.assertEqual(warehouse.verify(self.db)['cuts'][0]['total_rows'],14)

    def test_partial_import_rolls_back_every_source(self):
        cut = self.fixture(); original = warehouse.insert_source; calls = []
        def fail(connection,folder,cut_id,source,rows,parents=None,dockets=None):
            calls.append(source['id'])
            if len(calls)==2: raise RuntimeError('Simulated interrupted import')
            return original(connection,folder,cut_id,source,rows,parents,dockets)
        with patch.object(warehouse,'insert_source',side_effect=fail):
            with self.assertRaisesRegex(RuntimeError,'interrupted'):
                warehouse.promote(cut,self.db)
        connection = sqlite3.connect(self.db)
        for table in ['cuts','members','sources','records']:
            self.assertEqual(connection.execute(f'SELECT count(*) FROM {table}').fetchone()[0],0)
        connection.close()

    def test_knowledge_time_and_cohort_membership_are_required(self):
        warehouse.promote(self.fixture(),self.db)
        for dot,at in [('1','2026-08-31T21:59:59Z'),('2','2026-08-31T23:00:00Z')]:
            with self.assertRaisesRegex(ValueError,'No preserved'):
                warehouse.carrier_evidence(self.db,dot,at)
        self.assertEqual(warehouse.carrier_evidence(self.db,'1','2026-09-01T00:00:00+02:00')['cut_id'],'cut')
        with self.assertRaisesRegex(ValueError,'Future'):
            warehouse.carrier_evidence(self.db,'1','2099-01-01T00:00:00Z')

    def test_stored_payload_or_dot_index_tampering_is_detected(self):
        warehouse.promote(self.fixture(),self.db)
        connection = sqlite3.connect(self.db)
        connection.execute("UPDATE records SET dot='2' WHERE source_id='az4n-8mr2'"); connection.commit()
        with self.assertRaisesRegex(ValueError,'index'):
            warehouse.carrier_evidence(self.db,'1')
        connection.execute("UPDATE records SET dot='1',payload='{}' WHERE source_id='az4n-8mr2'"); connection.commit(); connection.close()
        with self.assertRaisesRegex(ValueError,'hash'):
            warehouse.verify(self.db)

    def test_unrelated_database_is_never_reinitialized(self):
        self.db.parent.mkdir()
        connection = sqlite3.connect(self.db); connection.execute('CREATE TABLE user_data (value TEXT)'); connection.commit(); connection.close()
        with self.assertRaisesRegex(ValueError,'Unrecognized'):
            warehouse.promote(self.fixture(),self.db)
        connection = sqlite3.connect(self.db)
        self.assertEqual(connection.execute('SELECT count(*) FROM user_data').fetchone()[0],0)
        connection.close()

    def test_motus_queries_and_rows_use_usdot_number(self):
        state = {'observed_at':'2026-08-31T20:01:00Z','rows_updated_at':123,'schema_sha256':'schema','table_id':'table','row_count':1}
        with patch.object(cs,'state',return_value=state),patch.object(cs,'query',return_value=[{'source_row_id':'1','usdot_number':'1'}]) as query:
            result = cs.collect('inys-ebih',['1'],self.root)
        self.assertEqual(result['row_count'],1)
        self.assertEqual(query.call_args.kwargs['where'],"usdot_number in ('1')")


if __name__ == '__main__':
    unittest.main()
