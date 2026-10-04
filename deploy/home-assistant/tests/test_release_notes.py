import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from candidate import links
from publish_store import publish


class ReleaseNotesTests(unittest.TestCase):
    def publish_notes(self, channel):
        source = 'a' * 40
        candidate = {'channel': channel, 'version': '0.2.2701',
                     'repository': 'example/nocturne-ha', 'commit': source,
                     'upstream_tag': '0.2.7' if channel == 'stable' else 'main-aaaaaaa',
                     'platforms': ['amd64', 'arm64'],
                     'links': links(source, 'v0.2.7' if channel == 'stable' else None,
                                    'example/nocturne-ha', 'b' * 40, 123)}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / 'candidate.json'
            path.write_text(json.dumps(candidate))
            with patch('publish_store.previous_package', return_value={'version': '0.2.2601'}), \
                    patch('publish_store.registry', return_value='sha256:' + 'c' * 64):
                publish(path, root / 'store')
            folder = root / 'store' / channel
            config = json.loads((folder / 'config.json').read_text())
            self.assertEqual(config['arch'], ['amd64', 'aarch64'])
            return (folder / 'CHANGELOG.md').read_text(encoding='utf-8')

    def test_stable_notes_link_exact_upstream_release_and_paired_sources(self):
        notes = self.publish_notes('stable')
        self.assertIn('https://github.com/nightscout/nocturne/releases/tag/v0.2.7', notes)
        self.assertIn('HA package 0.2.2701', notes)
        self.assertIn('Published architectures: amd64, aarch64', notes)
        self.assertIn('https://github.com/nightscout/nocturne/tree/' + 'a' * 40, notes)
        self.assertIn('https://github.com/example/nocturne-ha/tree/' + 'b' * 40, notes)

    def test_main_notes_link_published_snapshot_history_without_invented_release(self):
        notes = self.publish_notes('main')
        self.assertIn('https://github.com/nightscout/nocturne/commits/' + 'a' * 40 + '/', notes)
        self.assertNotIn('/releases/tag/', notes)
        self.assertIn('Main is a source snapshot', notes)
