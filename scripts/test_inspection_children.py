import copy
import json
import pathlib
import tempfile
import unittest
import urllib.error
from unittest.mock import patch

import cohort_snapshot as cs
import evidence_warehouse as warehouse
import test_evidence_warehouse as fixtures
from inspection_children import CHILDREN, PARENT, batches, child_dot, child_where, collect_children, parent_index, verify_children
from snapshot_store import now


class InspectionChildTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        self.parents = {'123':'1'}
        self.parent_lineage = {'where':cs.cohort_where(PARENT,['1']), 'after':{
            'observed_at':now(),'rows_updated_at':123,'schema_sha256':'schema','table_id':'table','row_count':1}}

    def collect(self,sid='wt8s-2hbx',rows=None,parents=None,**options):
        rows = rows if rows is not None else [{'inspection_id':'123','source_row_id':'child1'}, {'inspection_id':'123','source_row_id':'child2'}]
        def state(source,where):
            return {**self.parent_lineage['after'],'observed_at':now(),'row_count':1 if source==PARENT else len(rows),
                    'metadata':{'columns':[{'fieldName':'inspection_id','dataTypeName':CHILDREN.get(source,'number')}]}}
        def query(source,**params):
            if params.get('select')=='count(*) as count': return [{'count':str(len(rows))}]
            offset=params['offset']; return rows[offset:offset+params['limit']]
        with patch.object(cs,'state',side_effect=state),patch.object(cs,'query',side_effect=query):
            return collect_children(sid,self.parents if parents is None else parents,self.root,self.parent_lineage,**options)

    def read(self,name,checksum):
        path=self.root/name
        if cs.hash_file(path)!=checksum: raise ValueError('Hash changed')
        return json.loads(path.read_text())

    def test_complete_pages_verify_without_adding_carrier_to_raw_rows(self):
        source=self.collect(page_size=1)
        lineage=self.read(source['lineage'],source['lineage_sha256'])
        rows=verify_children(source,lineage,self.parents,self.parent_lineage,self.read,100)
        self.assertEqual(len(rows),2)
        self.assertEqual(child_dot(rows[0],self.parents),'1')
        self.assertNotIn('dot_number',rows[0])
        self.assertEqual(len(source['pages']),3)  # exact page boundary requires empty terminal page

    def test_parent_uniqueness_and_query_key_types(self):
        self.assertEqual(child_where('wt8s-2hbx',['123']),"inspection_id in ('123')")
        self.assertEqual(child_where('876r-jsdb',['123']),'inspection_id in (123)')
        self.assertEqual(len(batches({str(i):'1' for i in range(1,502)})),3)
        with self.assertRaisesRegex(ValueError,'parent ID'):
            parent_index([{'inspection_id':'123','dot_number':'1'}]*2)
        with self.assertRaisesRegex(ValueError,'query'):
            child_where('876r-jsdb',["123' OR 1=1"])

    def test_orphan_and_cross_carrier_rows_are_rejected(self):
        for row in [{'inspection_id':'999'},{'inspection_id':'123','dot_number':'2'}]:
            with self.subTest(row=row),self.assertRaisesRegex(ValueError,'Orphan'):
                child_dot(row,self.parents)

    def test_missing_parent_batches_or_changed_scope_cannot_verify(self):
        source=self.collect()
        lineage=self.read(source['lineage'],source['lineage_sha256'])
        for mutate in [lambda l:l['batches'].clear(),lambda l:l.update(parent_map_sha256='bad'),
                       lambda l:l['batches'][0].update(where='inspection_id is not null'),
                       lambda l:l['batches'][0].update(count_after=100)]:
            altered=copy.deepcopy(lineage);mutate(altered)
            with self.assertRaises(ValueError):verify_children(source,altered,self.parents,self.parent_lineage,self.read,100)

    def test_child_and_parent_updates_invalidate_lineage(self):
        source=self.collect();lineage=self.read(source['lineage'],source['lineage_sha256'])
        for field in ['after','parent_source_after']:
            altered=copy.deepcopy(lineage);altered[field]['rows_updated_at']+=1
            with self.assertRaisesRegex(ValueError,'changed'):
                verify_children(source,altered,self.parents,self.parent_lineage,self.read,100)

    def test_empty_parent_set_has_no_child_pages(self):
        source=self.collect(parents={})
        self.assertEqual(source['row_count'],0);self.assertEqual(source['pages'],[])
        lineage=self.read(source['lineage'],source['lineage_sha256'])
        self.assertEqual(verify_children(source,lineage,{},self.parent_lineage,self.read,100),[])

    def test_row_ceiling_fails_instead_of_returning_partial_success(self):
        with self.assertRaisesRegex(ValueError,'ceiling'):self.collect(max_rows=1)

    def test_child_page_growth_is_source_drift_not_a_row_ceiling(self):
        # A source can add rows after the initial per-batch count. Never accept
        # extra rows, truncate them, or mistake this for max_rows exhaustion.
        sid='wt8s-2hbx'
        changed_rows=[{'inspection_id':'123','source_row_id':'child1'},
                      {'inspection_id':'123','source_row_id':'child2'}]
        def state(source,where):
            return {**self.parent_lineage['after'],'observed_at':now(),
                    'row_count':1 if source==PARENT else len(changed_rows),
                    'metadata':{'columns':[{'fieldName':'inspection_id',
                                             'dataTypeName':CHILDREN.get(source,'number')} ]}}
        def query(source,**params):
            if params.get('select')=='count(*) as count':
                return [{'count':'1'}]
            return changed_rows[params['offset']:params['offset']+params['limit']]
        with patch.object(cs,'state',side_effect=state),patch.object(cs,'query',side_effect=query):
            with self.assertRaisesRegex(cs.SourceChangedError,'preflight count'):
                collect_children(sid,self.parents,self.root,self.parent_lineage,
                                 max_rows=10,page_size=5000)
        # The failed partial pages remain audit evidence, not a complete manifest.
        self.assertTrue(list(self.root.glob('*.page-*.json')))

    def test_child_growth_past_actual_hard_cap_stays_fatal(self):
        # Distinguish a changed source from an ACTUAL configured safety breach:
        # if count_before=1, page has 2, and max_rows=1, never auto-retry.
        sid='wt8s-2hbx'
        changed_rows=[{'inspection_id':'123','source_row_id':'child1'},
                      {'inspection_id':'123','source_row_id':'child2'}]
        def state(source,where):
            return {**self.parent_lineage['after'],'observed_at':now(),
                    'row_count':1 if source==PARENT else 2,
                    'metadata':{'columns':[{'fieldName':'inspection_id',
                                            'dataTypeName':CHILDREN.get(source,'number')} ]}}
        def query(source,**params):
            if params.get('select')=='count(*) as count':
                return [{'count':'1'}]
            return changed_rows[params['offset']:params['offset']+params['limit']]
        with patch.object(cs,'state',side_effect=state),patch.object(cs,'query',side_effect=query):
            with self.assertRaisesRegex(ValueError,'accepted row ceiling') as raised:
                collect_children(sid,self.parents,self.root,self.parent_lineage,
                                 max_rows=1,page_size=5000)
        self.assertNotIsInstance(raised.exception,cs.SourceChangedError)

    def test_aggregate_parallel_growth_over_hard_cap_is_fatal(self):
        sid='wt8s-2hbx'
        parents={'123':'1','124':'1'}
        def state(source,where):
            return {**self.parent_lineage['after'],'observed_at':now(),
                    'row_count':2,
                    'metadata':{'columns':[{'fieldName':'inspection_id',
                                            'dataTypeName':CHILDREN.get(source,'number')}]}}
        def query(source,**params):
            identity=params['where'].split("'")[1]
            if params.get('select')=='count(*) as count':
                return [{'count':'1'}]
            rows=[{'inspection_id':identity,'source_row_id':identity+'-a'},
                  {'inspection_id':identity,'source_row_id':identity+'-b'}]
            return rows[params['offset']:params['offset']+params['limit']]
        with patch('inspection_children.BATCH_SIZE',1),patch.object(cs,'state',side_effect=state),patch.object(cs,'query',side_effect=query):
            with self.assertRaisesRegex(ValueError,'accepted row ceiling') as raised:
                collect_children(sid,parents,self.root,self.parent_lineage,
                                 max_rows=3,page_size=5000)
        self.assertNotIsInstance(raised.exception,cs.SourceChangedError)

    def test_aggregate_final_count_growth_over_hard_cap_is_fatal(self):
        sid='wt8s-2hbx'
        parents={'123':'1','124':'1'}
        queried={}
        def state(source,where):
            return {**self.parent_lineage['after'],'observed_at':now(),
                    'row_count':2,
                    'metadata':{'columns':[{'fieldName':'inspection_id',
                                            'dataTypeName':CHILDREN.get(source,'number')}]}}
        def query(source,**params):
            identity=params['where'].split("'")[1]
            if params.get('select')=='count(*) as count':
                queried[identity]=queried.get(identity,0)+1
                return [{'count':str(1 if queried[identity]==1 else 2)}]
            rows=[{'inspection_id':identity,'source_row_id':identity+'-a'}]
            return rows[params['offset']:params['offset']+params['limit']]
        with patch('inspection_children.BATCH_SIZE',1),patch.object(cs,'state',side_effect=state),patch.object(cs,'query',side_effect=query):
            with self.assertRaisesRegex(ValueError,'accepted row ceiling') as raised:
                collect_children(sid,parents,self.root,self.parent_lineage,
                                 max_rows=3,page_size=5000)
        self.assertNotIsInstance(raised.exception,cs.SourceChangedError)

    def test_mixed_per_batch_observations_sum_to_hard_cap_failure(self):
        # The page for batch 123 grows, while postflight on disjoint batch 124
        # grows. Neither pages-only nor postflight-only totals reveal the cap;
        # per-batch maximum observations prove at least four rows (cap three).
        sid='wt8s-2hbx'
        parents={'123':'1','124':'1'}
        counts={}
        def state(source,where):
            return {**self.parent_lineage['after'],'observed_at':now(),
                    'row_count':2,'metadata':{'columns':[
                        {'fieldName':'inspection_id','dataTypeName':CHILDREN.get(source,'number')}]}}
        def query(source,**params):
            identity=params['where'].split("'")[1]
            if params.get('select')=='count(*) as count':
                counts[identity]=counts.get(identity,0)+1
                return [{'count':str(2 if identity=='124' and counts[identity]>1 else 1)}]
            rows=[{'inspection_id':identity,'source_row_id':identity+'-a'}]
            if identity=='123':
                rows.append({'inspection_id':identity,'source_row_id':identity+'-b'})
            return rows[params['offset']:params['offset']+params['limit']]
        with patch('inspection_children.BATCH_SIZE',1),patch.object(cs,'state',side_effect=state),patch.object(cs,'query',side_effect=query):
            with self.assertRaisesRegex(ValueError,'accepted row ceiling') as raised:
                collect_children(sid,parents,self.root,self.parent_lineage,
                                 max_rows=3,page_size=5000)
        self.assertNotIsInstance(raised.exception,cs.SourceChangedError)

    def test_permanent_http_404_outweighs_parallel_source_change(self):
        sid='wt8s-2hbx'
        parents={'123':'1','124':'1'}
        def state(source,where):
            return {**self.parent_lineage['after'],'observed_at':now(),
                    'row_count':2,'metadata':{'columns':[
                        {'fieldName':'inspection_id','dataTypeName':CHILDREN.get(source,'number')}]}}
        def query(source,**params):
            identity=params['where'].split("'")[1]
            if params.get('select')=='count(*) as count':
                return [{'count':'1'}]
            if identity=='124':
                raise urllib.error.HTTPError('https://example.invalid/source',404,'Not Found',{},None)
            return [{'inspection_id':identity,'source_row_id':identity+'-a'},
                    {'inspection_id':identity,'source_row_id':identity+'-b'}]
        with patch('inspection_children.BATCH_SIZE',1),patch.object(cs,'state',side_effect=state),patch.object(cs,'query',side_effect=query):
            with self.assertRaises(urllib.error.HTTPError) as raised:
                collect_children(sid,parents,self.root,self.parent_lineage,
                                 max_rows=10,page_size=5000)
        self.assertEqual(raised.exception.code,404)

    def test_growing_child_page_rejects_wrong_parent_before_source_drift(self):
        sid='wt8s-2hbx'
        def state(source,where):
            return {**self.parent_lineage['after'],'observed_at':now(),
                    'row_count':2,'metadata':{'columns':[
                        {'fieldName':'inspection_id','dataTypeName':CHILDREN.get(source,'number')}]}}
        def query(source,**params):
            if params.get('select')=='count(*) as count':
                return [{'count':'1'}]
            return [{'inspection_id':'123','source_row_id':'first'},
                    {'inspection_id':'999','source_row_id':'unrelated'}]
        with patch.object(cs,'state',side_effect=state),patch.object(cs,'query',side_effect=query):
            with self.assertRaisesRegex(ValueError,'wrong parent batch') as raised:
                collect_children(sid,self.parents,self.root,self.parent_lineage,
                                 max_rows=10,page_size=5000)
        self.assertNotIsInstance(raised.exception,cs.SourceChangedError)

    def test_growing_child_page_rejects_duplicate_id_before_source_drift(self):
        sid='wt8s-2hbx'
        def state(source,where):
            return {**self.parent_lineage['after'],'observed_at':now(),
                    'row_count':2,'metadata':{'columns':[
                        {'fieldName':'inspection_id','dataTypeName':CHILDREN.get(source,'number')}]}}
        def query(source,**params):
            if params.get('select')=='count(*) as count':
                return [{'count':'1'}]
            return [{'inspection_id':'123','source_row_id':'duplicate'},
                    {'inspection_id':'123','source_row_id':'duplicate'}]
        with patch.object(cs,'state',side_effect=state),patch.object(cs,'query',side_effect=query):
            with self.assertRaisesRegex(ValueError,'Duplicate/missing child row ID') as raised:
                collect_children(sid,self.parents,self.root,self.parent_lineage,
                                 max_rows=10,page_size=5000)
        self.assertNotIsInstance(raised.exception,cs.SourceChangedError)

    def test_parallel_preflight_http_404_overrides_http_503(self):
        sid='wt8s-2hbx'
        parents={'123':'1','124':'1'}
        def state(source,where):
            return {**self.parent_lineage['after'],'observed_at':now(),
                    'row_count':2,'metadata':{'columns':[
                        {'fieldName':'inspection_id','dataTypeName':CHILDREN.get(source,'number')}]}}
        def query(source,**params):
            identity=params['where'].split("'")[1]
            code=503 if identity=='123' else 404
            raise urllib.error.HTTPError('https://example.invalid/source',code,'HTTP failure',{},None)
        with patch('inspection_children.BATCH_SIZE',1),patch.object(cs,'state',side_effect=state),patch.object(cs,'query',side_effect=query):
            with self.assertRaises(urllib.error.HTTPError) as raised:
                collect_children(sid,parents,self.root,self.parent_lineage,
                                 max_rows=10,page_size=5000)
        self.assertEqual(raised.exception.code,404)

    def test_child_final_count_mismatch_is_retryable_source_drift(self):
        sid='wt8s-2hbx'
        rows=[{'inspection_id':'123','source_row_id':'child1'}]
        counter=0
        def state(source,where):
            return {**self.parent_lineage['after'],'observed_at':now(),
                    'row_count':1 if source==PARENT else 2,
                    'metadata':{'columns':[{'fieldName':'inspection_id',
                                             'dataTypeName':CHILDREN.get(source,'number')} ]}}
        def query(source,**params):
            if params.get('select')=='count(*) as count':
                return [{'count':'2'}]
            return rows[params['offset']:params['offset']+params['limit']]
        with patch.object(cs,'state',side_effect=state),patch.object(cs,'query',side_effect=query):
            with self.assertRaisesRegex(cs.SourceChangedError,'preflight, page and final counts'):
                collect_children(sid,self.parents,self.root,self.parent_lineage,
                                 max_rows=10,page_size=5000)

    def test_retry_policy_retries_only_changed_sources_not_actual_ceilings(self):
        from validate_evidence_warehouse import retryable_acquisition
        def manifest(error):
            return {'status':'PARTIAL','datasets':[
                {'id':'wt8s-2hbx','status':'FAILED','error':error}]}
        self.assertTrue(retryable_acquisition(
            manifest('SourceChangedError: Inspection child page exceeded preflight count')))
        self.assertFalse(retryable_acquisition(
            manifest('ValueError: Complete child source exceeds accepted row ceiling')))

    def test_combined_batch_ceiling_is_checked_before_downloading_pages(self):
        with patch('inspection_children.BATCH_SIZE',1):
            with self.assertRaisesRegex(ValueError,'ceiling'):
                self.collect(parents={'123':'1','124':'1'},max_rows=3)
        self.assertEqual(list(self.root.glob('*.page-*.json')),[])

    def test_v5_warehouse_indexes_children_through_preserved_parents(self):
        cut=fixtures.WarehouseTests.fixture(self)
        manifest=json.loads((cut/'manifest.json').read_text())
        parent=next(s for s in manifest['datasets'] if s['id']==PARENT)
        path=cut/parent['pages'][0]['path']; rows=json.loads(path.read_text());rows[0]['inspection_id']='123'
        path.write_text(json.dumps(rows));parent['pages'][0]['sha256']=cs.hash_file(path)
        self.parent_lineage=json.loads((cut/parent['lineage']).read_text())
        # Child test writer uses the same folder as the verified parent cut.
        self.root=cut
        for sid in CHILDREN:manifest['datasets'].append(self.collect(sid,rows=[{'inspection_id':'123','source_row_id':'c1'}]))
        manifest.update(schema_version=5,source_profile='underwriting_evidence_v2',completed_at=now())
        (cut/'manifest.json').write_text(json.dumps(manifest))
        self.assertEqual(len(cs.load_verified(cut)[2]),18)
        db=cut/'test.sqlite';warehouse.promote(cut,db)
        result=warehouse.carrier_evidence(db,'1',include_records=True,profile='underwriting_evidence_v2')
        self.assertEqual(len(result['sources']),18)
        child=next(s for s in result['sources'] if s['source_id']=='wt8s-2hbx')
        self.assertEqual(child['carrier_rows'],1);self.assertNotIn('dot_number',child['rows'][0])
        self.assertEqual(warehouse.promote(cut,db)['promotion'],'ALREADY_PRESENT')


if __name__=='__main__':unittest.main()
