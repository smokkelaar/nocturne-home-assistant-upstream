import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from candidate import baseline_for_arch


class ArchitectureTests(unittest.TestCase):
    def test_adding_arm64_preserves_amd64_upgrade_test(self):
        previous = {'platforms': ['amd64'], 'image': 'ghcr.io/example/nocturne-{arch}:0.2.1701'}
        self.assertEqual(baseline_for_arch(previous, 'arm64'), '')
        self.assertEqual(baseline_for_arch(previous, 'amd64'),
                         'ghcr.io/example/nocturne-amd64:0.2.1701')

    def test_later_arm64_publication_uses_previous_aarch64_image(self):
        previous = {'platforms': ['amd64', 'arm64'], 'image': 'ghcr.io/example/nocturne-{arch}:0.2.2501'}
        self.assertEqual(baseline_for_arch(previous, 'arm64'),
                         'ghcr.io/example/nocturne-aarch64:0.2.2501')

    def test_first_publication_uses_candidate_restore_for_each_architecture(self):
        for arch in ('amd64', 'arm64'):
            with self.subTest(arch=arch):
                self.assertEqual(baseline_for_arch(None, arch), '')
