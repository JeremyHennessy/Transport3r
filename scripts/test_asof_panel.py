import copy
import json
import pathlib
import tempfile
import unittest
from unittest.mock import patch

import cohort_snapshot as cs
import build_asof_panel as panel
from snapshot_store import write_once

STATE={'observed_at':'2026-08-31T20:00:00Z','rows_updated_at':123,'schema_sha256':'schema','table_id':'table','row_count':1}
AS_OF='2026-08-31T23:59:59Z'

class CohortTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=pathlib.Path(self.temp.name)

    def test_ordered_paging_reads_lookahead_and_checks_counts(self):
        row={'dot_number':'1','source_row_id':'a'}
        with patch.object(cs,'state',side_effect=[STATE,STATE]), patch.object(cs,'query',side_effect=[[row],[]]) as query:
            result=cs.collect('az4n-8mr2',['1'],self.root,page_size=1)
        self.assertEqual(result['row_count'],1)
        self.assertEqual(len(result['pages']),2)
        self.assertEqual(query.call_args_list[1].kwargs['offset'],1)

    def test_duplicate_and_cross_carrier_rows_fail(self):
        for rows in [[{'dot_number':'2','source_row_id':'a'}],
                     [{'dot_number':'1','source_row_id':'a'},{'dot_number':'1','source_row_id':'a'}]]:
            with tempfile.TemporaryDirectory() as folder, patch.object(cs,'state',return_value=STATE), patch.object(cs,'query',return_value=rows):
                with self.assertRaisesRegex(ValueError,'contamination'):
                    cs.collect('az4n-8mr2',['1'],pathlib.Path(folder))

    def test_short_response_is_not_mistaken_for_complete(self):
        with patch.object(cs,'state',return_value=STATE), patch.object(cs,'query',return_value=[]):
            with self.assertRaisesRegex(ValueError,'count'):
                cs.collect('az4n-8mr2',['1'],self.root)

    def test_upstream_changes_reject_cut(self):
        after={**STATE,'rows_updated_at':124}
        with patch.object(cs,'state',side_effect=[STATE,after]), patch.object(cs,'query',return_value=[{'dot_number':'1','source_row_id':'a'}]):
            with self.assertRaisesRegex(ValueError,'changed'):
                cs.collect('az4n-8mr2',['1'],self.root)

    def fixture(self):
        cut=self.root/'cut'
        cut.mkdir()
        cohort={'selected_at':'2026-08-31T19:00:00Z','dots':['1']}
        write_once(cut/'cohort.json',cohort)
        datasets=[]
        for sid in cs.SOURCES:
            page=f'{sid}.page.json'
            write_once(cut/page,[{'dot_number':'1','source_row_id':'a','inspection_id':'1','crash_id':'1','insp_date':'20260830','report_date':'20260830'}])
            lineage=f'{sid}.lineage.json'
            write_once(cut/lineage,{'before':STATE,'after':STATE})
            datasets.append({'id':sid,'status':'COMPLETE','started_at':'2026-08-31T20:00:00Z','available_at':'2026-08-31T21:00:00Z',
                             'row_count':1,'lineage':lineage,'lineage_sha256':cs.hash_file(cut/lineage),
                             'pages':[{'path':page,'sha256':cs.hash_file(cut/page),'rows':1,'offset':0}]})
        manifest={'schema_version':3,'status':'COMPLETE','acquisition_kind':'CURRENT_COHORT_PUBLIC_SOURCE','historical_reconstruction':False,
                  'snapshot_id':'cut','started_at':'2026-08-31T19:00:00Z','completed_at':'2026-08-31T22:00:00Z',
                  'cohort_path':'cohort.json','cohort_sha256':cs.hash_file(cut/'cohort.json'),'datasets':datasets}
        write_once(cut/'manifest.json',manifest)
        return cut

    def test_offline_integrity_and_no_backdating(self):
        cut=self.fixture()
        self.assertEqual(len(cs.load_verified(cut,AS_OF)[2]),7)
        with self.assertRaisesRegex(ValueError,'as-of'):
            cs.load_verified(cut,'2026-07-31T23:59:59Z')
        (cut/'az4n-8mr2.page.json').write_text('[]')
        with self.assertRaisesRegex(ValueError,'hash'):
            cs.load_verified(cut)

    def test_monthly_builder_rejects_unavailable_and_future_observations(self):
        cut=self.fixture()
        for at,message in [('2026-07-31T23:59:59Z','No verified'),('2099-01-31T23:59:59Z','future'),('2026-08-15T23:59:59Z','month end')]:
            with self.assertRaisesRegex(ValueError,message):
                panel.build([cut],at,self.root/'output',month_end=True)
        self.assertFalse((self.root/'output').exists())

    def test_month_end_build_is_reproducible_and_outputs_not_replaced(self):
        cut=self.fixture()
        one=panel.build([cut],AS_OF,self.root/'one',month_end=True)
        two=panel.build([cut],AS_OF,self.root/'two',month_end=True)
        self.assertEqual(one['features_sha256'],two['features_sha256'])
        self.assertEqual(one['grain'],'USDOT_MONTH_END')
        with self.assertRaises(FileExistsError):
            panel.build([cut],AS_OF,self.root/'one',month_end=True)

    def test_mixed_cohort_cuts_cannot_silently_change_population(self):
        original=cs.load_verified(self.fixture())
        changed=copy.deepcopy(original)
        changed[1]['dots']=['2']
        with patch.object(panel,'load_verified',side_effect=[original,changed]):
            with self.assertRaisesRegex(ValueError,'different cohorts'):
                panel.build(['first','second'],AS_OF,self.root/'output',month_end=True)

class FeatureTests(unittest.TestCase):
    def data(self):
        data={sid:[] for sid in cs.SOURCES}
        data['az4n-8mr2']=[{'dot_number':'1','power_units':'2','total_drivers':'2','mcs150_date':'20260801'}]
        return data

    def test_window_boundaries_future_and_known_oos(self):
        data=self.data()
        data['fx4q-ay7w']=[{'dot_number':'1','inspection_id':str(i),'insp_date':date,'oos_total':oos} for i,date,oos in
                          [(1,'20260831','1'),(2,'20260801','0'),(3,'20260731','5'),(4,'20260901','1')]]
        row=panel.features('1',data,AS_OF)
        self.assertEqual(row['inspections_30d'],1)
        self.assertEqual(row['oos_rate_30d'],1)
        self.assertEqual(row['future_inspections_excluded'],1)

    def test_missing_date_and_oos_do_not_become_zero(self):
        data=self.data()
        data['fx4q-ay7w']=[{'dot_number':'1','inspection_id':'1','insp_date':'20260831','oos_total':''}]
        row=panel.features('1',data,AS_OF)
        self.assertIsNone(row['oos_inspections_90d'])
        self.assertEqual(row['inspections_90d'],1)
        data['fx4q-ay7w'][0]['insp_date']='invalid'
        self.assertIsNone(panel.features('1',data,AS_OF)['inspections_90d'])

    def test_severity_known_positive_survives_other_unknown_fields(self):
        data=self.data()
        data['aayw-vxb3']=[{'dot_number':'1','crash_id':'1','report_date':'20260830','fatalities':'1'}]
        row=panel.features('1',data,AS_OF)
        self.assertEqual(row['severe_vehicle_reports_90d'],1)
        data['aayw-vxb3'][0]['fatalities']=''
        row=panel.features('1',data,AS_OF)
        self.assertIsNone(row['severe_vehicle_reports_90d'])
        self.assertEqual(row['known_severe_vehicle_reports_90d'],0)

    def test_missing_exposure_does_not_gain_denominator(self):
        data=self.data()
        data['az4n-8mr2']=[]
        row=panel.features('1',data,AS_OF)
        self.assertIsNone(row['power_units_reported'])
        self.assertIsNone(row['crash_vehicle_reports_per_current_power_unit_90d'])
        self.assertIsNone(row['oos_rate_90d'])
        self.assertEqual(panel.number(0,True),0)
        data['az4n-8mr2']=[{'dot_number':'1','power_units':'0'}]
        row=panel.features('1',data,AS_OF)
        self.assertEqual(row['fleet_group'],'ZERO_REPORTED')
        self.assertIsNone(row['crash_vehicle_reports_per_current_power_unit_90d'])

    def test_sms_populations_remain_separate_and_no_fake_percentile(self):
        data=self.data()
        data['4y6x-dmck']=[{'dot_number':'1','veh_maint_measure':'2'}]
        data['m3ry-qcip']=[{'dot_number':'1','veh_maint_pct':'80'}]
        row=panel.features('1',data,AS_OF)
        self.assertIsNone(row['official_sms_by_population']['AB_PROPERTY']['percentiles']['veh_maint'])
        self.assertEqual(row['official_sms_by_population']['AB_PASSENGER']['percentiles']['veh_maint'],80)
        self.assertTrue(all(v['value'] is None for v in row['future_labels'].values()))

    def test_duplicate_events_are_rejected(self):
        data=self.data()
        data['fx4q-ay7w']=[{'dot_number':'1','inspection_id':'1'}]*2
        with self.assertRaisesRegex(ValueError,'duplicate'):
            panel.features('1',data,AS_OF)

if __name__=='__main__':
    unittest.main()
