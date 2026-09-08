import unittest
from audit_fleet_consistency import audit, validate, expected

class FleetGateTests(unittest.TestCase):
    def test_mismatch_fails_even_when_sample_is_large(self):
        result = audit([{'power_units': '1', 'fleetsize': 'A'}] * 100 + [{'power_units': '5001', 'fleetsize': 'A'}])
        with self.assertRaisesRegex(ValueError, 'mismatches'):
            validate(result)

    def test_unknown_is_not_a_match(self):
        result = audit([{'power_units': value, 'fleetsize': 'A'} for value in ['', '0', 'nan', '1.5']])
        self.assertEqual(result['unknown'], 4)
        with self.assertRaisesRegex(ValueError, 'too few'):
            validate(result)

    def test_boundaries_and_passing_sample(self):
        self.assertEqual([expected(n) for n in [1, 2, 3, 4, 999, 1000, 5000, 5001]], ['A','B','B','C','U','V','Y','Z'])
        validate(audit([{'power_units': '1', 'fleetsize': 'A'}] * 100))

if __name__ == '__main__':
    unittest.main()
