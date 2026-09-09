import unittest
from temporal_readiness import exposure_eligibility
from capture_sms_release import parse_release
class TemporalTests(unittest.TestCase):
    def test_release_schedule_is_not_website_actual_release(self):
        raw='<div>Data current as of: July 31, 2026</div><div>Website Updated on: August 10, 2026</div><div>Next update: Week of September 7, 2026</div>'
        self.assertEqual(parse_release(raw),{'website_snapshot_date':'2026-07-31','website_updated_on':'2026-08-10'})
        with self.assertRaises(ValueError):parse_release('Next update: September 7, 2026')
    def test_exposure_date_and_unknowns_cannot_be_backdated(self):
        row={'status_code':'A','mcs150_date':'20261001','power_units':'0','total_drivers':None,'mcs150_mileage_year':'2020'}
        issues=exposure_eligibility(row,'2026-09-09T00:00:00Z')
        self.assertIn('FUTURE_REPORT_DATE',issues);self.assertIn('INELIGIBLE_POWER_UNITS',issues);self.assertIn('INELIGIBLE_TOTAL_DRIVERS',issues);self.assertIn('MILEAGE_YEAR_INELIGIBLE',issues)
if __name__=='__main__':unittest.main()
