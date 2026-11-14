"""Public report/CLI regressions for missing records versus missing review."""
import contextlib
import copy
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import ledger
import round_report
from render_round import render
from test_report import fixture
from decision_fixtures import assessment, TARGET, REVISION


def requirements():
    body = json.dumps({'description': '- Keep A\n- Keep B\n- Keep C',
                       'comments': [{'body': 'Owner decision remains limited to C'}]})
    saved = {'source': 'https://tracker.test/item', 'retrieved_at': REVISION, 'revision': 'revision-1',
             'coverage': 'complete', 'body': body, 'sha256': hashlib.sha256(body.encode()).hexdigest()}
    source = {'source': saved['source'], 'retrieved_at': REVISION, 'snapshot_sha256': saved['sha256'],
              'source_path': ['description'], 'acceptance_text': json.loads(body)['description'],
              'criteria': [{'id': 'A', 'quote': 'Keep A'}, {'id': 'B', 'quote': 'Keep B'}],
              'matrix': [{'criterion_id': 'A', 'result': 'verified'}, {'criterion_id': 'B', 'result': 'verified'}]}
    return {'tickets': [{'id': 'APP-1'}], 'source_snapshots': [saved], 'requirements': [source]}


class SourceEvidenceTests(unittest.TestCase):
    def collect(self, *, saved=(), ticket=None, targets=None, merged=True, reviews=None):
        raw, record = fixture()
        raw['timeline'], raw['requestedReviewers'] = [], []
        raw['ticketEvidence'] = ticket or {}
        if reviews is not None:
            raw['pr']['reviews'] = reviews
        pr = {**raw['pr'], 'id': 'PR_fixture', 'isDraft': False, 'state': 'MERGED' if merged else 'OPEN',
              'reviewDecision': 'APPROVED', 'mergeStateStatus': 'CLEAN', 'updatedAt': REVISION,
              'mergedAt': '2026-11-03T16:00:00Z' if merged else None}
        raw['pr'] = pr
        output, errors = io.StringIO(), io.StringIO()
        with patch.object(sys, 'argv', ['round_report.py', 'main', '--since', '2026-11-03T00:00:00Z', '--me', 'Other']), \
                patch.object(round_report, 'repo_slug', return_value=record['repository']), \
                patch.object(round_report, 'gh', side_effect=[[] if merged else [pr], [pr] if merged else []]), \
                patch.object(round_report, 'history_evidence', return_value=raw), \
                patch.object(round_report, 'assessment_history', return_value=list(saved)), \
                patch.object(round_report, 'target_state', side_effect=targets or [TARGET, TARGET], create=True), \
                patch.object(round_report, 'queue_state', return_value='not_queued'), \
                patch.object(ledger, 'heads', return_value={}), \
                contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            round_report.main()
        return json.loads(output.getvalue())[0], errors.getvalue()

    def test_missing_local_assessment_shows_observed_exact_head_review_without_unreviewed_claim(self):
        row, errors = self.collect()
        page = render([row], 'main')
        self.assertIn('Merged head has no saved local assessment', page)
        self.assertNotIn('UNREVIEWED HEAD', errors)
        self.assertNotIn('not assessed by this round', page)
        self.assertIn('Observed exact-head review', page)
        self.assertIn('Alex', page)
        self.assertIn('before merge', page)
        self.assertIn('https://example.test/review/11', page)
        self.assertIn('not acceptance certification', page)
        self.assertEqual(len(row['merge_evidence']['exact_head_reviews']), 1)

    def test_later_saved_owner_decision_survives_old_import_and_post_merge_time_stays_explicit(self):
        _, record = fixture()
        old = assessment(482, 'code', 'Author', head=record['head'], base=record['base'], assessed_at='2026-11-01T00:00:00Z')
        later = assessment(482, 'evidence', 'Operator', head=record['head'], base=record['base'], assessed_at='2026-11-04T00:00:00Z',
                           provenance='https://example.test/later-assessment')
        old['recorded_at'] = '2026-11-05T00:00:00Z'  # Imported later, assessed earlier.
        later['decisions'][0]['waiver'] = {'actor': 'Owner', 'source': 'https://example.test/original-owner',
            'at': '2026-11-04T00:00:00Z', 'scope': 'C only, not A or B', 'criterion': later['decisions'][0]['criterion']}
        row, _ = self.collect(saved=[later, old])
        page = render([row], 'main')
        self.assertEqual(row['assessment'], later)
        self.assertEqual(len(row['assessment_history']), 2)
        self.assertFalse(row['merge_review_gap'])
        self.assertIn('after merge', page)
        self.assertIn(later['provenance'], page)
        self.assertIn('C only, not A or B', page)
        self.assertIn('https://example.test/original-owner', page)
        self.assertEqual(row['assessment']['assessed_at'], '2026-11-04T00:00:00Z')

    def test_review_time_offsets_equal_timestamps_and_unknown_dates_do_not_imply_premerge_review(self):
        raw, _ = fixture()
        for at, expected in [('2026-11-03T15:30:00-02:00', 'after merge'),
                             ('2026-11-03T18:00:00+02:00', 'at recorded merge time · order unknown'),
                             (None, 'merge timing unknown')]:
            review = {**raw['pr']['reviews'][1], 'submittedAt': at}
            row, _ = self.collect(reviews=[review])
            self.assertEqual(row['merge_evidence']['exact_head_reviews'][0]['timing'], expected)

    def test_other_head_review_or_merge_commit_cannot_cover_source_head(self):
        raw, record = fixture()
        old = assessment(482, head='e' * 40, base=record['base'])
        review = {**raw['pr']['reviews'][1], 'commitOid': 'e' * 40}
        row, _ = self.collect(saved=[old], reviews=[review])
        self.assertTrue(row['merge_review_gap'])
        self.assertEqual(row['merge_evidence']['exact_head_reviews'], [])
        self.assertEqual(row['head'], record['head'])

    def test_complete_source_retains_omitted_criterion_but_reconstructed_excerpts_fail(self):
        ticket = requirements()
        self.assertEqual(round_report.requirement_gaps(ticket), [])
        row, _ = self.collect(ticket=ticket)
        self.assertIn('Keep C', row['history']['ticketEvidence']['source_snapshots'][0]['body'])
        self.assertIn('not extraction completeness', render([row], 'main'))
        ticket['requirements'][0]['acceptance_text'] = '- Keep A\n- Keep B'
        self.assertIn('requirements-section-mismatch:https://tracker.test/item', round_report.requirement_gaps(ticket))
        del ticket['source_snapshots']
        self.assertIn('requirements-original-source-not-retained:https://tracker.test/item', round_report.requirement_gaps(ticket))

    def test_source_hash_coverage_offsets_and_matrix_failures_remain_gaps(self):
        original = requirements()
        for mutation in ('hash', 'partial', 'metadata', 'offset', 'quote', 'matrix', 'empty'):
            ticket = copy.deepcopy(original)
            saved, source = ticket['source_snapshots'][0], ticket['requirements'][0]
            if mutation == 'hash': saved['body'] += 'changed'
            elif mutation == 'partial': saved['coverage'] = 'partial'
            elif mutation == 'metadata': del saved['revision']
            elif mutation == 'offset': source['section'] = [0, 5000]
            elif mutation == 'quote': source['criteria'][0]['quote'] = 'Invented'
            elif mutation == 'matrix': source['matrix'] = []
            elif mutation == 'empty': source['criteria'] = []
            with self.subTest(mutation=mutation):
                self.assertTrue(round_report.requirement_gaps(ticket))

    def test_comment_only_changes_invalidate_same_head_without_erasing_raw_owner_decision(self):
        ticket = requirements()
        first, _ = self.collect(ticket=ticket, merged=False)
        saved = assessment(482, head=first['head'], base=first['base'], evidence_inputs=first['evidence_inputs'])
        snapshot = ticket['source_snapshots'][0]
        body = json.loads(snapshot['body'])
        body['comments'].append({'body': 'A later owner decision'})
        snapshot['body'] = json.dumps(body)
        snapshot['sha256'] = hashlib.sha256(snapshot['body'].encode()).hexdigest()
        snapshot['revision'] = 'revision-2'
        ticket['requirements'][0]['snapshot_sha256'] = snapshot['sha256']
        second, _ = self.collect(ticket=ticket, saved=[saved], merged=False)
        self.assertNotEqual(first['evidence_inputs']['issues'], second['evidence_inputs']['issues'])
        self.assertFalse(ledger.assessment_current(saved, second['head'], second['base'], second['evidence_inputs']))
        self.assertIn('Owner decision remains limited to C', second['history']['ticketEvidence']['source_snapshots'][0]['body'])

    def test_independent_target_change_or_failed_read_invalidates_matching_pr_base(self):
        for target in ({**TARGET, 'sha': 'f' * 40}, {**TARGET, 'sha': None}):
            row, _ = self.collect(targets=[TARGET, target], merged=False)
            self.assertNotEqual(row['base'], target['sha'])
            self.assertIn('target-ref-changed-or-unavailable', row['history']['gaps'])
            self.assertEqual(row['handoffs']['coverage'], 'unknown')
            saved = assessment(482, head=row['head'], base=row['base'], evidence_inputs=row['evidence_inputs'])
            self.assertIn('Review again', render([row], 'main', assessments={'repository': row['repository'], 'assessments': [saved]}))

    def test_snapshot_cli_retains_exact_response_and_refuses_overwrite(self):
        script = Path(__file__).resolve().parents[1] / 'scripts/requirements.py'
        with tempfile.TemporaryDirectory() as tmp:
            raw, output = Path(tmp) / 'raw.json', Path(tmp) / 'snapshot.json'
            body = b'{"description":"Keep A, B and C","comments":[]}\r\n'
            raw.write_bytes(body)
            command = [sys.executable, '-B', str(script), str(raw), '--source', 'https://tracker.test/item',
                       '--retrieved-at', REVISION, '--revision', 'revision-1', '--coverage', 'complete', '--output', str(output)]
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            saved = json.loads(output.read_text())
            self.assertEqual(saved['body'].encode(), body)
            self.assertEqual(saved['sha256'], hashlib.sha256(body).hexdigest())
            before = output.read_bytes()
            self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)
            self.assertEqual(output.read_bytes(), before)
