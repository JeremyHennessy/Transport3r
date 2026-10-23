import unittest
from unittest.mock import patch

import validate_fmcsa_data_contract as contract


class NormalizationAuditTests(unittest.TestCase):
    def test_source_invalid_dates_are_reported_not_hidden_or_treated_as_runtime_failure(self):
        schema={'columns':[{'field_name':'report_date'}]}
        with patch.object(contract,'query',return_value=[{'report_date':'20261023'},{'report_date':'not-a-date'}]):
            result=contract.validate_sample_normalization('aayw-vxb3',schema)
        self.assertEqual(result['dates']['report_date'],1)
        self.assertEqual(result['invalid_dates']['report_date'],{'count':1,'samples':['not-a-date']})

    def test_supported_fmcsa_date_forms_parse_deterministically(self):
        for value in ['20261023','10232026','20261023 1230','2026-10-23','10/23/2026','23-Oct-26','2026-10-23T12:30:00Z']:
            with self.subTest(value=value):self.assertEqual(str(contract.parse_fmcsa_date(value)),'2026-10-23')
        for value in ['', '0', '00000000', 'not-a-date']:
            with self.subTest(value=value):self.assertIsNone(contract.parse_fmcsa_date(value))


if __name__=='__main__':unittest.main()
