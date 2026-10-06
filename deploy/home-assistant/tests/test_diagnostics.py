import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

BASE = Path(__file__).resolve().parents[1]
CLI_PATH = BASE / 'shared/rootfs/opt/nocturne-ha/diagnostic_cli.py'
spec = importlib.util.spec_from_file_location('diagnostic_cli', CLI_PATH)
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)


class DiagnosticTests(unittest.TestCase):
    def test_smoke_probe_reports_only_safe_failure_markers(self):
        spec = importlib.util.spec_from_file_location('smoke_probe', BASE / 'tools/smoke.py')
        smoke = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(smoke)
        marker = smoke.safe_failure_marker(
            'AssertionError: credential-value\n'
            'CI_PROBE_FAILED:HTTPError:LINE_12:STATUS_404')
        self.assertEqual('CI_PROBE_FAILED:HTTPError:LINE_12:STATUS_404', marker.group(0))
        self.assertIsNone(smoke.safe_failure_marker('credential-value'))

    def test_stable_and_main_image_include_read_only_diagnostics(self):
        root = BASE / 'shared'
        self.assertTrue((root / 'rootfs/usr/local/bin/nocturne-ha').is_file())
        self.assertIn('/usr/local/bin/nocturne-ha',
                      (root / 'Dockerfile.in').read_text())

    def test_fresh_instance_probe_uses_setup_independent_version_endpoint(self):
        probe = (BASE / 'tools/smoke.py').read_text()
        self.assertIn('http://127.0.0.1:8080/api/v3/version', probe)
        self.assertNotIn('http://127.0.0.1:8080/api/v1/status', probe)

    def test_cli_rejects_external_or_mutating_targets_before_connecting(self):
        for path in ('https://example.com/api/v3/version', '//example.com/api/v3/version',
                     '/api/../secret', '/status', '/api/status\r\nHost: example.com'):
            with self.subTest(path=path), \
                    patch.object(cli, 'checked_options') as options, \
                    patch.object(cli.http.client, 'HTTPConnection') as connection:
                with self.assertRaises(ValueError):
                    cli.api_request(path)
                options.assert_not_called()
                connection.assert_not_called()


if __name__ == '__main__':
    unittest.main()
