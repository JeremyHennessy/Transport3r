"""Synthetic, pinned-cut date quality; never silently repair source observations."""
import unittest
import duckdb
from nationwide_warehouse import date_quality

class DatePlausibilityTests(unittest.TestCase):
    def setUp(self):
        self.db=duckdb.connect(':memory:');self.addCleanup(self.db.close)
        self.db.execute('CREATE TABLE dates(value VARCHAR)')
        self.values=['0200-04-12','4196-01-23','2020-02-29','2021-02-29',
                     '2026-11-09','2026-11-10','bad',None,'','20261023']
        self.db.executemany('INSERT INTO dates VALUES (?)',[(v,) for v in self.values])

    def test_pinned_plausibility_counts_and_raw_preservation(self):
        q=date_quality(self.db,'dates',['value'],['value'],'2026-11-09T00:00:00Z')[0]
        self.assertEqual((q['rows'],q['missing'],q['valid'],q['invalid']),(10,2,6,2))
        p=q['plausibility']
        self.assertEqual((p['before_review_floor'],p['after_cut_date'],p['within_review_window']),(1,2,3))
        self.assertEqual(sum(p[k] for k in ('before_review_floor','after_cut_date','within_review_window')),q['valid'])
        self.assertFalse(p['source_values_modified'])
        self.assertEqual([r[0] for r in self.db.execute('SELECT value FROM dates').fetchall()],self.values)

    def test_no_wall_clock_guess_without_pinned_cut(self):
        self.assertEqual(date_quality(self.db,'dates',['value'],['value'])[0]['plausibility']['status'],'NOT_CHECKED')

    def test_cut_boundary_moves_only_when_explicitly_changed(self):
        q=date_quality(self.db,'dates',['value'],['value'],'2026-11-10T00:00:00Z')[0]
        self.assertEqual(q['plausibility']['after_cut_date'],1)
        self.assertEqual(q['plausibility']['within_review_window'],4)

    def test_timezone_cut_uses_utc_date(self):
        q=date_quality(self.db,'dates',['value'],['value'],'2026-11-09T23:30:00-04:00')[0]
        self.assertEqual(q['plausibility']['cut_date_utc'],'2026-11-10')
        self.assertEqual(q['plausibility']['after_cut_date'],1)

    def test_invalid_cut_and_missing_field_fail_closed(self):
        for cut in ('bad','2026-02-30T00:00:00Z','2026-11-09'):
            with self.subTest(cut=cut),self.assertRaises((ValueError,TypeError)):
                date_quality(self.db,'dates',['value'],['value'],cut)
        with self.assertRaises(ValueError):
            date_quality(self.db,'dates',['value'],['missing'],'2026-11-09T00:00:00Z')

if __name__=='__main__':unittest.main()
