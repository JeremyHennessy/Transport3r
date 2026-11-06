"""Public integrity endpoint accepts only a deep audit of the installed cut."""
import copy
import json
import pathlib
import threading
import unittest
import urllib.error
import urllib.request

import duckdb
from audit_warehouse_integrity import audit
from evidence_api import EvidenceServer, Handler
from integrity_report import public_report
import test_audit_warehouse_integrity as audit_fixture


class IntegrityApiTests(unittest.TestCase):
    def setUp(self):
        self.fixture = audit_fixture.WarehouseIntegrityAuditTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.path = self.fixture.path
        self.report = audit(self.path, deep=True)
        self.assertEqual(self.report['status'], 'PASS', self.report['failures'])
        self.report_path = self.path.with_suffix('.audit.json')
        self.report_path.write_text(json.dumps(self.report))
        db = duckdb.connect(str(self.path), read_only=True)
        try:
            self.receipt = json.loads(db.execute('SELECT acceptance_json FROM warehouse_acceptance').fetchone()[0])
        finally:
            db.close()

    def start(self, with_audit=True):
        server = EvidenceServer(('127.0.0.1', 0), Handler, self.path, 'https://example.test',
                                audit_report=self.report_path if with_audit else None)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        def stop():
            server.shutdown(); server.server_close(); thread.join()
        self.addCleanup(stop)
        return f'http://127.0.0.1:{server.server_port}'

    def reject(self, mutate):
        report = copy.deepcopy(self.report)
        mutate(report)
        with self.assertRaises(ValueError):
            public_report(report, self.receipt, self.report['warehouse_sha256'])

    def test_installed_audit_and_health_agree(self):
        base = self.start()
        with urllib.request.urlopen(base + '/healthz') as response:
            health = json.load(response)
        with urllib.request.urlopen(base + '/v1/integrity') as response:
            value = json.load(response)
            self.assertEqual(response.headers['Cache-Control'], 'no-store')
            self.assertEqual(response.headers['Access-Control-Allow-Origin'], 'https://example.test')
        self.assertEqual(health['independent_audit'], 'PASS')
        self.assertEqual(health['warehouse_sha256'], value['warehouse_sha256'])
        self.assertEqual(health['cut_id'], value['cut_id'])
        self.assertEqual(value['raw_rows'], 8)
        self.assertEqual(len(value['sources']), 36)

    def test_head_has_no_response_body(self):
        base = self.start()
        with urllib.request.urlopen(urllib.request.Request(base + '/v1/integrity', method='HEAD')) as response:
            self.assertEqual(response.read(), b'')
            self.assertGreater(int(response.headers['Content-Length']), 0)

    def test_no_audit_is_not_zero_or_verified(self):
        base = self.start(False)
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(base + '/v1/integrity')
        self.assertEqual(caught.exception.code, 503)
        value = json.load(caught.exception)
        self.assertEqual(value['status'], 'NOT_AUDITED')
        self.assertNotIn('raw_rows', value)

    def test_shallow_or_old_schema_is_rejected(self):
        self.reject(lambda r: r.update(deep_exact_duplicates_checked=False))
        self.reject(lambda r: r.update(schema_version='TRANSPORT3R_WAREHOUSE_AUDIT_1'))

    def test_wrong_warehouse_or_cut_is_rejected(self):
        self.reject(lambda r: r.update(warehouse_sha256='a' * 64))
        self.reject(lambda r: r.update(cut_id='another-cut'))

    def test_missing_source_or_duplicate_source_is_rejected(self):
        self.reject(lambda r: r['sources'].pop())
        self.reject(lambda r: r['sources'].__setitem__(0, copy.deepcopy(r['sources'][1])))

    def test_wrong_counts_or_checks_are_rejected(self):
        self.reject(lambda r: r['sources'][0].update(published=999))
        self.reject(lambda r: r['sources'][0].update(actual_raw=True))
        self.reject(lambda r: r['sources'][0]['checks'].update(joined_rows=False))
        self.reject(lambda r: r['checks'].pop('census_carriers'))
        self.reject(lambda r: r.update(raw_rows=123))

    def test_duplicate_metrics_must_match_recount(self):
        self.reject(lambda r: r['sources'][0].update(exact_duplicate_rows=999))
        self.reject(lambda r: r['sources'][0].update(distinct_source_rows=-1))

    def test_future_audit_is_rejected(self):
        self.reject(lambda r: r.update(audited_at='2999-01-01T00:00:00Z'))

    def test_arbitrary_report_fields_are_not_exposed(self):
        self.report['private_notes'] = 'PRIVATE_CANARY'
        self.report['warehouse'] = '/private/policies/client.duckdb'
        self.report['sources'][0]['notes'] = 'PRIVATE_CANARY'
        self.report_path.write_text(json.dumps(self.report))
        base = self.start()
        with urllib.request.urlopen(base + '/v1/integrity') as response:
            raw = response.read().decode()
        self.assertNotIn('PRIVATE_CANARY', raw)
        self.assertNotIn('/private/', raw)

    def test_changed_warehouse_fails_closed_on_every_data_route(self):
        base = self.start()
        self.fixture.sql("UPDATE raw_fx4q_ay7w SET payload='changed'")
        for route in ('/healthz', '/v1/integrity', '/v1/carriers/3706/evidence'):
            with self.subTest(route=route), self.assertRaises(urllib.error.HTTPError) as caught:
                urllib.request.urlopen(base + route)
            self.assertEqual(caught.exception.code, 503)
            self.assertEqual(json.load(caught.exception)['status'], 'WAREHOUSE_CHANGED')

    def test_invalid_configured_audit_stops_startup(self):
        self.report_path.write_text(json.dumps({'status': 'PASS'}))
        with self.assertRaises(ValueError):
            EvidenceServer(('127.0.0.1', 0), Handler, self.path, '*', audit_report=self.report_path)


if __name__ == '__main__':
    unittest.main()
