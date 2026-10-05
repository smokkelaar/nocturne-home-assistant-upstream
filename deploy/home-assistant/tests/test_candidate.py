import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import candidate

STABLE = '1' * 40
MAIN = '2' * 40
WRAPPER = '3' * 40


class PublicationReadinessTests(unittest.TestCase):
    def run_record(self, status='completed', conclusion='success', commit=MAIN):
        return {'id': 12, 'head_sha': commit, 'status': status, 'conclusion': conclusion}

    def paired(self, runs, jobs=()):
        def github(path):
            if '/runs?' in path:
                return {'workflow_runs': runs}
            return {'jobs': [{'name': name, 'conclusion': result} for name, result in jobs]}
        return patch.object(candidate, 'github', side_effect=github)

    def test_missing_or_unrelated_run_is_deferred(self):
        for runs in ([], [self.run_record(commit=STABLE)]):
            with self.subTest(runs=runs), self.paired(runs):
                with self.assertRaises(candidate.UpstreamNotReady):
                    candidate.paired_run(MAIN, 'main')

    def test_queued_or_running_publication_is_deferred(self):
        for status in ('queued', 'in_progress'):
            with self.subTest(status=status), self.paired([self.run_record(status, None)]):
                with self.assertRaises(candidate.UpstreamNotReady):
                    candidate.paired_run(MAIN)

    def test_successful_legacy_and_split_publishers_are_accepted(self):
        for jobs in ([('build-and-push', 'success')],
                     [('dotnet-images', 'success'), ('web-image', 'success'), ('report', 'success')]):
            with self.subTest(jobs=jobs), self.paired([self.run_record()], jobs):
                self.assertEqual(candidate.paired_run(MAIN), 12)

    def test_completed_failure_is_not_hidden(self):
        for conclusion in ('failure', 'timed_out', 'cancelled'):
            with self.subTest(conclusion=conclusion), self.paired([self.run_record(conclusion=conclusion)]):
                with self.assertRaises(ValueError):
                    candidate.paired_run(MAIN)

    def test_success_without_both_published_images_is_an_error(self):
        with self.paired([self.run_record()], [('dotnet-images', 'success'), ('web-image', 'failure')]):
            with self.assertRaises(ValueError):
                candidate.paired_run(MAIN)

    def test_pending_retry_after_failure_is_deferred(self):
        with self.paired([self.run_record('in_progress', None), self.run_record(conclusion='failure')]):
            with self.assertRaises(candidate.UpstreamNotReady):
                candidate.paired_run(MAIN)

    def test_pending_retry_does_not_discard_a_complete_publication(self):
        with self.paired([self.run_record('in_progress', None), self.run_record()],
                         [('build-and-push', 'success')]):
            self.assertEqual(candidate.paired_run(MAIN), 12)

    def test_new_failure_is_not_hidden_by_an_older_pending_run(self):
        with self.paired([self.run_record(conclusion='failure'), self.run_record('in_progress', None)]):
            with self.assertRaises(ValueError):
                candidate.paired_run(MAIN)


class CandidateSelectionTests(unittest.TestCase):
    def select(self, destination, paired, previous=None, registry_error=None):
        def github(path):
            return {
                'releases/latest': {'draft': False, 'prerelease': False, 'tag_name': 'v0.2.4'},
                'commits/v0.2.4': {'sha': STABLE},
                'commits/main': {'sha': MAIN},
            }[path]

        def fetch(url):
            if previous is not None:
                return previous, ''
            raise urllib.error.HTTPError(url, 404, 'Not found', {}, None)

        with patch.object(candidate, 'github', side_effect=github), \
                patch.object(candidate, 'fetch', side_effect=fetch), \
                patch.object(candidate, 'recipe_hash', return_value='recipe'), \
                patch.object(candidate, 'paired_run', side_effect=paired) as publisher, \
                patch.object(candidate, 'previous_package', return_value=None), \
                patch.object(candidate, 'registry', return_value='sha256:' + '4' * 64,
                             side_effect=registry_error), \
                patch.object(candidate.urllib.request, 'urlopen',
                             side_effect=lambda *args, **kwargs: io.BytesIO(b'PNPM_VERSION: 10.13.1')):
            candidate.select(destination, 'example/wrapper', '0.2.101', WRAPPER, ['amd64'])
            return publisher

    def test_main_pending_does_not_block_ready_stable(self):
        with tempfile.TemporaryDirectory() as root:
            output = Path(root)
            self.select(output, [12, candidate.UpstreamNotReady('Main publisher running')])
            matrix = json.loads((output / 'matrix.json').read_text())
            self.assertEqual([item['channel'] for item in matrix['include']], ['stable'])
            self.assertTrue((output / 'stable.json').exists())
            self.assertFalse((output / 'main.json').exists())
            self.assertEqual(json.loads((output / 'deferred.json').read_text()),
                             [{'channel': 'main', 'commit': MAIN, 'reason': 'Main publisher running'}])

    def test_both_pending_produces_empty_build_matrix(self):
        with tempfile.TemporaryDirectory() as root:
            output = Path(root)
            self.select(output, [candidate.UpstreamNotReady('Pending')] * 2)
            self.assertEqual(json.loads((output / 'matrix.json').read_text()), {'include': []})
            self.assertEqual(len(json.loads((output / 'deferred.json').read_text())), 2)
            self.assertFalse((output / 'main.json').exists())
            self.assertFalse((output / 'stable.json').exists())

    def test_unchanged_channel_does_not_need_historical_publisher(self):
        with tempfile.TemporaryDirectory() as root:
            previous = {'commit': STABLE, 'recipe': 'recipe', 'platforms': ['amd64']}
            publisher = self.select(Path(root), [candidate.UpstreamNotReady('Pending')], previous)
            publisher.assert_called_once_with(MAIN, 'main')

    def test_completed_failure_still_fails_selection(self):
        with tempfile.TemporaryDirectory() as root, self.assertRaisesRegex(ValueError, 'Failed publication'):
            self.select(Path(root), [ValueError('Failed publication')])

    def test_invalid_registry_metadata_still_fails_selection(self):
        with tempfile.TemporaryDirectory() as root, self.assertRaisesRegex(ValueError, 'Registry digest mismatch'):
            self.select(Path(root), [12], registry_error=ValueError('Registry digest mismatch'))
