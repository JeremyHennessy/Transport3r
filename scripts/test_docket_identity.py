import copy,json,pathlib,tempfile,unittest
from unittest.mock import patch
import cohort_snapshot as cs
from docket_identity import BRIDGE,DOCKET_ONLY,docket_index,docket_dot,docket_where,verify_bridge
from snapshot_store import digest

class DocketTests(unittest.TestCase):
    def proof(self,rows):
        state={'rows_updated_at':1,'schema_sha256':'a','table_id':'t','row_count':len(rows)}
        return {'source_id':BRIDGE,'where':"docket_number in ('MC001')",'before':state,'after':state,'rows':rows,'rows_sha256':digest(rows)}

    def test_legacy_padded_dot_queries_and_identity_are_exact(self):
        self.assertEqual(cs.source_dot(BRIDGE,{'dot_number':'00003706'}),'3706')
        self.assertEqual(cs.cohort_where(BRIDGE,['3706']),"dot_number in ('00003706','3706')")
        self.assertEqual(docket_index([{'docket_number':'MC001','dot_number':'00003706'}]),{'MC001':'3706'})
        for value in ['00000000','3706 OR true','-3706',None]:
            with self.assertRaises(ValueError):cs.source_dot(BRIDGE,{'dot_number':value})
        from evidence_warehouse import cut_eligible
        self.assertFalse(cut_eligible({'source_profile':'underwriting_evidence_v3'}))
        self.assertTrue(cut_eligible({'source_profile':'underwriting_evidence_v2'}))

    def test_exact_docket_keeps_prefix_and_leading_zeros(self):
        index=docket_index([{'docket_number':'MC001','dot_number':'1'}])
        self.assertEqual(docket_dot({'prefix_docket_number':'MC001'},index),'1')
        for value in ['MC1','FF001','001','MC001 OR true']:
            with self.assertRaises(ValueError):docket_dot({'prefix_docket_number':value},index)
        self.assertEqual(docket_where('prefix_docket_number',{}),'1=0')

    def test_global_collision_and_unknown_carrier_are_rejected(self):
        with self.assertRaisesRegex(ValueError,'multiple'):
            docket_index([{'docket_number':'MC001','dot_number':dot} for dot in ['1','2']])
        with self.assertRaises(ValueError):docket_index([{'docket_number':'MC001','dot_number':None}])
        with self.assertRaises(ValueError):docket_dot({'prefix_docket_number':'MC001','dot_number':'2'},{'MC001':'1'})

    def test_full_bridge_proof_rejects_missing_duplicate_and_wrong_scope(self):
        rows=[{'source_row_id':'r','docket_number':'MC001','dot_number':'1'}];proof=self.proof(rows)
        self.assertEqual(verify_bridge(proof,{'MC001':'1'}),{'MC001':'1'})
        for kind in ['count','duplicate','scope','owner']:
            changed=copy.deepcopy(proof)
            if kind=='count':changed['after']['row_count']=2
            if kind=='duplicate':changed['rows']*=2;changed['rows_sha256']=digest(changed['rows'])
            if kind=='scope':changed['where']='1=1'
            if kind=='owner':changed['rows'][0]['dot_number']='2';changed['rows_sha256']=digest(changed['rows'])
            with self.subTest(kind=kind),self.assertRaises(ValueError):verify_bridge(changed,{'MC001':'1'})

    def test_all_36_sources_are_in_v3_without_changing_prior_profiles(self):
        sources=json.loads((cs.ROOT/'data/fmcsa_sources.json').read_text())
        if isinstance(sources,dict):sources=sources['sources']
        self.assertEqual(set(cs.PROFILES['underwriting_evidence_v3']),{s['id'] for s in sources})
        self.assertEqual(len(cs.PROFILES['underwriting_evidence_v2']),18)
        self.assertEqual(len(cs.PROFILES['underwriting_evidence_v1']),14)
        self.assertEqual(cs.source_dot('yu5v-wbh6',{'usdot_number':'1'}),'1')

    def test_docket_acquisition_preserves_raw_rows_and_complete_pages(self):
        rows=[{'source_row_id':'r1','prefix_docket_number':'MC001'}]
        proof=self.proof([{'source_row_id':'b','docket_number':'MC001','dot_number':'1'}]);proof['before']['observed_at']='2026-09-09T00:00:00Z'
        state={**proof['after'],'observed_at':'2026-09-09T00:00:01Z'}
        def query(sid,**params):return rows[params['offset']:params['offset']+params['limit']]
        with tempfile.TemporaryDirectory() as folder,patch.object(cs,'state',return_value=state),patch.object(cs,'query',side_effect=query):
            result=cs.collect(DOCKET_ONLY,['1'],pathlib.Path(folder),page_size=1,dockets={'MC001':'1'},bridge_proof=proof)
            self.assertEqual(result['row_count'],1);self.assertEqual(len(result['pages']),2)
            raw=json.loads((pathlib.Path(folder)/result['pages'][0]['path']).read_text());self.assertNotIn('dot_number',raw[0])

if __name__=='__main__':unittest.main()
