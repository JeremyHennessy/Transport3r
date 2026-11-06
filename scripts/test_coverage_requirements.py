"""Synthetic-only tests of private document metadata, exact identity and history."""
import datetime as dt
import http.client
import json
import pathlib
import sqlite3
import tempfile
import threading
import unittest

from coverage_requirements import TEMPLATES, checklist, save_requirement, history
from insurance_reviews import LINES, save_review
from private_workspace import Workspace, make_server

POLICY = {'account_id': ' TEST-ACCOUNT ', 'policy_id': 'TEST-POLICY', 'dot_number': '3706'}
REVIEW = {**POLICY, 'line': 'auto-liability', 'status': 'needs_data', 'notes': 'SYNTHETIC: request dated loss history'}


class CoverageRequirementTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(':memory:'); self.db.row_factory = sqlite3.Row
        self.addCleanup(self.db.close)
        self.review_id = save_review(self.db, REVIEW, [POLICY], 'Synthetic owner')['id']
        self.body = {'review_id': self.review_id, 'requirement_key': 'loss-runs', 'status': 'requested',
                     'due_date': '2030-01-01', 'received_on': '', 'evidence_url': '', 'notes': '', 'expected_revision': 0}

    def save(self, patch=None):
        return save_requirement(self.db, {**self.body, **(patch or {})}, [POLICY], 'Synthetic owner')

    def test_default_is_unrequested_not_complete_and_read_does_not_save(self):
        plan = checklist(self.db, self.review_id)
        self.assertEqual(plan['summary'], {'total': 4, 'reviewed_or_not_applicable': 0, 'outstanding': 4})
        self.assertFalse(plan['coverage_determined'])
        self.assertEqual(plan['account_id'], POLICY['account_id'])
        self.assertTrue(all(i['status'] == 'not_requested' and i['revision'] == 0 for i in plan['items']))
        self.assertEqual(self.db.execute('SELECT count(*) FROM coverage_requirements').fetchone()[0], 0)

    def test_all_eight_lines_have_distinct_nonempty_prompts(self):
        self.assertEqual(set(TEMPLATES), LINES)
        for line, items in TEMPLATES.items():
            self.assertEqual(len(items), len(dict(items)))
            rid = save_review(self.db, {**REVIEW, 'line': line}, [POLICY], 'Synthetic owner')['id']
            self.assertEqual(len(checklist(self.db, rid)['items']), 4)

    def test_request_receive_review_with_immutable_history_and_idempotency(self):
        first = self.save(); self.assertEqual(first['revision'], 1)
        unchanged = self.save({'expected_revision': 1}); self.assertFalse(unchanged['changed'])
        received = self.save({'expected_revision': 1, 'status': 'received', 'received_on': '2020-01-02',
                              'evidence_url': 'https://example.org/synthetic-document'})
        self.assertEqual(received['revision'], 2)
        self.assertEqual(checklist(self.db, self.review_id)['summary']['outstanding'], 4)
        self.save({'expected_revision': 2, 'status': 'reviewed', 'received_on': '2020-01-02',
                   'evidence_url': 'https://example.org/synthetic-document', 'notes': 'SYNTHETIC analyst checked period and identity'})
        events = history(self.db, self.review_id, 'loss-runs')
        self.assertEqual(len(events), 3); self.assertIsNone(events[0]['previous_json'])
        self.assertEqual(json.loads(events[2]['previous_json'])['status'], 'received')
        self.assertEqual(checklist(self.db, self.review_id)['summary']['outstanding'], 3)
        self.assertEqual(self.db.execute('SELECT status FROM insurance_reviews').fetchone()[0], 'needs_data')

    def test_not_applicable_requires_recorded_rationale(self):
        self.save({'status': 'not_applicable', 'notes': 'SYNTHETIC: operating agreement excludes this item'})
        self.assertEqual(checklist(self.db, self.review_id)['summary']['reviewed_or_not_applicable'], 1)

    def test_invalid_status_dates_references_and_unknown_fields_fail(self):
        cases = [{'status': 'bound'}, {'status': 'approved'}, {'requirement_key': 'commodity-mix'},
                 {'due_date': ''}, {'due_date': '2026-02-30'}, {'status': 'received'},
                 {'status': 'received', 'received_on': '2020-01-01'},
                 {'status': 'reviewed', 'received_on': '2020-01-01', 'evidence_url': 'https://example.org'},
                 {'status': 'not_applicable', 'notes': 'x'}, {'evidence_url': 'javascript:alert(1)'},
                 {'evidence_url': 'http://example.org'}, {'evidence_url': 'https://user:secret@example.org'},
                 {'evidence_url': 'https://example.org/a\nb'}, {'notes': 'x' * 4001}, {'notes': 'a\x00b'},
                 {'expected_revision': True}, {'expected_revision': -1}, {'expected_revision': '0'},
                 {'risk_score': 90}, {'account_id': 'wrong'}, {'received_on': '2999-01-01'}]
        for patch in cases:
            with self.subTest(patch=patch), self.assertRaises(ValueError): self.save(patch)
        self.assertEqual(history(self.db, self.review_id, 'loss-runs'), [])

    def test_missing_review_or_reassigned_policy_cannot_accept_documents(self):
        with self.assertRaises(ValueError): self.save({'review_id': '0' * 64})
        with self.assertRaises(ValueError): self.save({'review_id': '../private'})
        for portfolio in ([], [{**POLICY, 'dot_number': '999'}], [{**POLICY, 'policy_id': 'other'}]):
            with self.assertRaises(ValueError): save_requirement(self.db, self.body, portfolio, 'Synthetic owner')
        with self.assertRaises(ValueError): save_requirement(self.db, self.body, [POLICY], '')

    def test_stale_revision_does_not_overwrite_or_append_history(self):
        self.save()
        with self.assertRaisesRegex(ValueError, 'refresh'): self.save({'notes': 'Stale edit'})
        self.assertEqual(len(history(self.db, self.review_id, 'loss-runs')), 1)
        self.assertEqual(checklist(self.db, self.review_id)['items'][0]['notes'], '')

    def test_history_cannot_select_another_line(self):
        with self.assertRaises(ValueError): history(self.db, self.review_id, 'commodity-mix')

    def test_notes_are_not_interpreted_as_markup_or_a_claims_total(self):
        notes = '<script>SYNTHETIC</script> & unknown loss history'
        self.save({'notes': notes})
        item = checklist(self.db, self.review_id)['items'][0]
        self.assertEqual(item['notes'], notes)
        self.assertNotIn('claims_count', item)


class CoverageRequirementApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.app = Workspace(pathlib.Path(self.temp.name))
        self.server = make_server(self.app, 0); self.cookie = None
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True); self.thread.start()

    def tearDown(self):
        self.app.stop.set(); self.server.shutdown(); self.server.server_close(); self.thread.join(); self.temp.cleanup()

    def request(self, path, data=None, origin=True, host=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        headers = {'Cookie': self.cookie} if self.cookie else {}
        if host: headers['Host'] = host
        if data is not None:
            headers['Content-Type'] = 'application/json'
            if origin: headers['Origin'] = f'http://127.0.0.1:{self.server.server_port}'
        conn.request('GET' if data is None else 'POST', path, json.dumps(data) if data is not None else None, headers)
        res = conn.getresponse(); body = json.loads(res.read())
        if res.getheader('Set-Cookie'): self.cookie = res.getheader('Set-Cookie').split(';')[0]
        status = res.status; conn.close(); return status, body

    def test_authenticated_complete_flow_and_write_boundaries(self):
        self.assertEqual(self.request('/api/insurance-requirements?review_id=' + '0' * 64)[0], 401)
        self.assertEqual(self.request('/api/insurance-requirement', {})[0], 401)
        self.assertEqual(self.request('/api/setup', {'name': 'SYNTHETIC', 'password': 'synthetic-test-password'})[0], 200)
        policy = {**POLICY, 'policy_start': '2026-01-01', 'policy_end': '2027-01-01', 'status': 'watch', 'review_status': 'unreviewed'}
        self.assertEqual(self.request('/api/portfolio', {'records': [policy]})[0], 200)
        status, review = self.request('/api/insurance-review', REVIEW); self.assertEqual(status, 200)
        rid = review['id']
        self.assertEqual(self.request('/api/insurance-requirements?review_id=' + rid)[1]['summary']['outstanding'], 4)
        body = {'review_id': rid, 'requirement_key': 'loss-runs', 'status': 'requested', 'due_date': '2030-01-01', 'expected_revision': 0}
        self.assertEqual(self.request('/api/insurance-requirement', body, origin=False)[0], 403)
        self.assertEqual(self.request('/api/insurance-requirement', body, host='example.org')[0], 403)
        self.assertEqual(self.request('/api/insurance-requirement', body)[0], 200)
        self.assertEqual(self.request('/api/insurance-requirement', body)[0], 400)
        hist = '/api/insurance-requirement-history?review_id=' + rid + '&requirement_key=loss-runs'
        self.assertEqual(len(self.request(hist)[1]), 1)
        self.assertEqual(self.request('/api/portfolio', {'records': [{**policy, 'dot_number': '123'}]})[0], 400)
        self.assertEqual(self.request('/api/logout', {})[0], 200)
        self.assertEqual(self.request(hist)[0], 401)
        self.assertEqual(self.request('/api/insurance-requirements?review_id=' + rid)[0], 401)


if __name__ == '__main__': unittest.main()
