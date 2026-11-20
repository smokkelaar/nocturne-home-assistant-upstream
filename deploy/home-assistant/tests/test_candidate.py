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
            if path == 'actions/workflows/docker-publish.yml':
                return {'id': 123}
            if '/runs?' in path:
                return {'workflow_runs': runs}
            return {'jobs': [{'name': name, 'conclusion': result} for name, result in jobs]}
        return patch.object(candidate, 'github', side_effect=github)

    def test_publisher_lookup_uses_numeric_workflow_id(self):
        with self.paired([self.run_record()], [('build-and-push', 'success')]) as api:
            self.assertEqual(candidate.paired_run(MAIN, 'main'), 12)
            self.assertIn('actions/workflows/123/runs?per_page=50&head_sha=' + MAIN + '&branch=main',
                          [call.args[0] for call in api.call_args_list])

    def test_invalid_publisher_id_fails_closed(self):
        for value in (None, '123', True, 0):
            with self.subTest(value=value), patch.object(candidate, 'github', return_value={'id': value}):
                with self.assertRaises(ValueError):
                    candidate.paired_run(MAIN)

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
    def select(self, destination, paired, previous=None, registry_error=None, force=False, rollout=None):
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
            candidate.select(destination, 'example/wrapper', '0.2.101', WRAPPER, ['amd64'], force=force, main_rollout=rollout)
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

    def test_force_selects_unchanged_channels_for_validation(self):
        with tempfile.TemporaryDirectory() as root:
            previous = {'commit': STABLE, 'recipe': 'recipe', 'platforms': ['amd64'],
                        'image': 'ghcr.io/example/wrapper/nocturne-{arch}:0.2.100'}
            publisher = self.select(Path(root), [12, 13], previous, force=True)
            self.assertEqual(publisher.call_args_list[0].args, (STABLE, None))
            self.assertEqual(publisher.call_args_list[1].args, (MAIN, 'main'))
            matrix = json.loads((Path(root) / 'matrix.json').read_text())
            self.assertEqual([item['channel'] for item in matrix['include']], ['stable', 'main'])

    def test_unpinned_sources_describe_the_release_and_main_and_keep_the_bridge_entry(self):
        with tempfile.TemporaryDirectory() as root:
            output = Path(root)
            self.select(output, [12, 13])
            stable = json.loads((output / 'stable-amd64/rootfs/opt/nocturne-ha/version.json').read_text())
            main = json.loads((output / 'main-amd64/rootfs/opt/nocturne-ha/version.json').read_text())
            self.assertEqual(('0.2.4', 'Nocturne v0.2.4', '0.2.4'), (stable['nocturne'], stable['base'], stable['release']))
            self.assertEqual('https://github.com/nightscout/nocturne/releases/tag/v0.2.4', stable['release_url'])
            self.assertEqual(('main@' + MAIN[:7], 'Nocturne main', 'Official main ' + MAIN[:7]),
                             (main['nocturne'], main['base'], main['release']))
            self.assertEqual('https://github.com/nightscout/nocturne/tree/' + MAIN, main['release_url'])
            for channel in ('stable', 'main'):
                self.assertIn('bridge_entry.py', (output / f'{channel}-amd64/Dockerfile').read_text())

    def test_pinned_main_rollout_uses_verified_official_images_in_both_storage_slots(self):
        rollout = {'repository': 'nightscout/nocturne', 'commit': MAIN, 'commit_at': '2026-10-14T11:40:00Z'}
        with tempfile.TemporaryDirectory() as root:
            publisher = self.select(Path(root), [12, 13], rollout=rollout)
            self.assertEqual([(MAIN, 'main', rollout['repository'])] * 2,
                             [call.args for call in publisher.call_args_list])
            for channel in ('stable', 'main'):
                proof = json.loads((Path(root) / (channel + '.json')).read_text())
                self.assertEqual(MAIN, proof['commit'])
                self.assertEqual(rollout['repository'], proof['source_repository'])
                self.assertIsNone(proof['links']['release_url'])
                self.assertIn(rollout['repository'], proof['links']['source_url'])
                recipe = (Path(root) / (channel + '-amd64') / 'Dockerfile').read_text()
                self.assertIn('FROM ghcr.io/nightscout/nocturne/nocturne-api@sha256:', recipe)
                self.assertIn('FROM ghcr.io/nightscout/nocturne/nocturne-web@sha256:', recipe)
                runtime = json.loads((Path(root) / (channel + '-amd64') / 'rootfs/opt/nocturne-ha/version.json').read_text())
                self.assertEqual(rollout['repository'], runtime['repository'])
                self.assertEqual(rollout['commit_at'], runtime['commit_at'])
                self.assertEqual('Nocturne main', runtime['base'])
                self.assertEqual(proof['links']['source_url'], runtime['release_url'])
                self.assertNotIn('0.2.7', runtime['release'])
                self.assertEqual('NocturneStable_' if channel == 'stable' else 'NocturneMain_',
                                 runtime['cookie_namespace'])

    def test_v030_bridge_uses_exact_release_source_and_preserves_storage_slots(self):
        rollout = {'repository': 'nightscout/nocturne', 'commit': candidate.BRIDGE_COMMIT,
                   'commit_at': '2026-10-27T09:53:08Z', 'migration_bridge': 'v0.3.0'}
        with tempfile.TemporaryDirectory() as root:
            output = Path(root)
            publisher = self.select(output, [12, 13], rollout=rollout)
            self.assertEqual([(candidate.BRIDGE_COMMIT, 'main', rollout['repository'])] * 2,
                             [call.args for call in publisher.call_args_list])
            for channel in ('stable', 'main'):
                proof = json.loads((output / (channel + '.json')).read_text())
                self.assertEqual(candidate.BRIDGE_COMMIT, proof['commit'])
                self.assertEqual('0.3.0', proof['upstream_tag'])
                self.assertEqual('v0.3.0', proof['migration_bridge'])
                self.assertEqual('main-fe91be2', proof['image_tag'])
                self.assertTrue(proof['links']['release_url'].endswith('/v0.3.0'))
                context = output / (channel + '-amd64')
                self.assertIn('bridge_entry.py', (context / 'Dockerfile').read_text())
                runtime = json.loads((context / 'rootfs/opt/nocturne-ha/version.json').read_text())
                self.assertEqual('0.3.0', runtime['nocturne'])
                self.assertEqual('Nocturne 0.3.0 database bridge', runtime['release'])
                self.assertEqual('NocturneStable_' if channel == 'stable' else 'NocturneMain_',
                                 runtime['cookie_namespace'])

    def test_bridge_rejects_other_source_commits_and_releases(self):
        for release, commit in (('v0.3.0', MAIN), ('v0.3.2', candidate.BRIDGE_COMMIT)):
            rollout = {'repository': 'nightscout/nocturne', 'commit': commit,
                       'commit_at': '2026-10-27T09:53:08Z', 'migration_bridge': release}
            with self.subTest(release=release, commit=commit), tempfile.TemporaryDirectory() as root, \
                    self.assertRaises(ValueError):
                self.select(Path(root), [], rollout=rollout)

    def test_v032_release_uses_exact_source_for_both_existing_storage_slots(self):
        rollout = {'repository': 'nightscout/nocturne', 'commit': candidate.RELEASE_032_COMMIT,
                   'commit_at': '2026-11-15T01:21:28Z', 'release': 'v0.3.2'}
        with tempfile.TemporaryDirectory() as root:
            output = Path(root)
            self.select(output, [12, 13], rollout=rollout)
            for channel in ('stable', 'main'):
                proof = json.loads((output / (channel + '.json')).read_text())
                self.assertEqual(candidate.RELEASE_032_COMMIT, proof['commit'])
                self.assertEqual('0.3.2', proof['upstream_tag'])
                self.assertEqual('main-ea4e97c', proof['image_tag'])
                self.assertTrue(proof['links']['release_url'].endswith('/v0.3.2'))
                context = output / (channel + '-amd64')
                self.assertIn('bridge_entry.py', (context / 'Dockerfile').read_text())
                runtime = json.loads((context / 'rootfs/opt/nocturne-ha/version.json').read_text())
                self.assertEqual('0.3.2', runtime['nocturne'])
                self.assertEqual('NocturneStable_' if channel == 'stable' else 'NocturneMain_',
                                 runtime['cookie_namespace'])

    def test_v032_release_rejects_other_source_and_tag(self):
        for release, commit in (('v0.3.1', candidate.RELEASE_032_COMMIT), ('v0.3.2', MAIN)):
            rollout = {'repository': 'nightscout/nocturne', 'commit': commit,
                       'commit_at': '2026-11-15T01:21:28Z', 'release': release}
            with self.subTest(release=release, commit=commit), tempfile.TemporaryDirectory() as root, \
                    self.assertRaises(ValueError):
                self.select(Path(root), [], rollout=rollout)

    def test_main_rollout_rejects_unpinned_or_unexpected_source(self):
        for rollout in ({}, [], {'repository': 'smokkelaar/nocturne-personal', 'commit': 'main'},
                        {'repository': 'other/fork', 'commit': MAIN},
                        {'repository': 'smokkelaar/nocturne-personal', 'commit': MAIN, 'commit_at': '2026-10-14T11:40:00Z'}):
            with tempfile.TemporaryDirectory() as root, self.assertRaises(ValueError):
                self.select(Path(root), [], rollout=rollout)

    def test_pr_validation_requires_every_channel_and_platform(self):
        platforms = ['amd64', 'arm64']
        complete = {'include': [{'channel': channel, 'arch': arch}
                                for channel in ('stable', 'main') for arch in platforms]}
        candidate.require_complete_pr_matrix(complete, [], platforms)
        with self.assertRaisesRegex(ValueError, 'upstream publication pending for main'):
            candidate.require_complete_pr_matrix(
                {'include': [item for item in complete['include'] if item['channel'] == 'stable']},
                [{'channel': 'main'}], platforms)
        with self.assertRaisesRegex(ValueError, 'missing main/arm64'):
            candidate.require_complete_pr_matrix(
                {'include': [item for item in complete['include']
                             if (item['channel'], item['arch']) != ('main', 'arm64')]},
                [], platforms)

    def test_completed_failure_still_fails_selection(self):
        with tempfile.TemporaryDirectory() as root, self.assertRaisesRegex(ValueError, 'Failed publication'):
            self.select(Path(root), [ValueError('Failed publication')])

    def test_invalid_registry_metadata_still_fails_selection(self):
        with tempfile.TemporaryDirectory() as root, self.assertRaisesRegex(ValueError, 'Registry digest mismatch'):
            self.select(Path(root), [12], registry_error=ValueError('Registry digest mismatch'))
