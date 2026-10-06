from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

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

    def test_fresh_and_configured_probes_check_runtime_metadata(self):
        spec = importlib.util.spec_from_file_location('smoke_probe', BASE / 'tools/smoke.py')
        smoke = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(smoke)
        probe = smoke.PROBE
        configured_probe = (BASE / 'tools/configured_native_probe.py').read_text()
        self.assertLess(configured_probe.index("phase = 'VERSION_METADATA'"),
                        configured_probe.index("version_request = urllib.request.Request("))
        self.assertIn("execute(name, API_ENV_PROBE, user='app')",
                      (BASE / 'tools/smoke.py').read_text())
        self.assertIn("process_environment.get(b'ASPNETCORE_URLS')", smoke.API_ENV_PROBE)
        self.assertIn('/api/v3/version', configured_probe)
        self.assertIn("version['head'] == expected_metadata['GIT_COMMIT']", configured_probe)
        self.assertIn("version['build'] == expected_metadata['BUILD_DATE']", configured_probe)
        self.assertIn("raise ConnectionError('Web service is not ready')", probe)
        self.assertNotIn('/api/v1/status', probe)
        self.assertIn("socket.create_connection(('127.0.0.1', 8080)", probe)
        self.assertIn("options['hostname'] + ':8448'", probe)
        self.assertNotIn('run.api_reachable(', probe)

    def test_cli_rejects_external_or_mutating_targets_before_connecting(self):
        for path in ('https://example.com/api/v3/version', '//example.com/api/v3/version',
                     '/api/../secret', '/api/%2e%2e/secret',
                     '/api/nested%2f..%2fsecret', '/status',
                     '/api/status\r\nHost: example.com'):
            with self.subTest(path=path), \
                    patch.object(cli, 'checked_options') as options, \
                    patch.object(cli.http.client, 'HTTPConnection') as connection:
                with self.assertRaises(ValueError):
                    cli.api_request(path)
                options.assert_not_called()
                connection.assert_not_called()

    def test_checked_options_rejects_non_object_json(self):
        validator = Mock()
        with patch.object(cli, 'DATA', Path('/mock')), \
                patch.object(Path, 'read_text', return_value='[]'), \
                patch.dict('sys.modules', {'settings': SimpleNamespace(validate_options=validator)}):
            with self.assertRaisesRegex(ValueError, 'JSON object'):
                cli.checked_options()
        validator.assert_not_called()

    def test_doctor_reports_configuration_dns_certificate_and_api(self):
        options = {'hostname': 'nocturne.example', 'authority': 'nocturne.example:8448',
                   'public_url': 'https://nocturne.example', 'certificate': 'cert.pem',
                   'private_key': 'key.pem'}
        response = SimpleNamespace(status=200, read=lambda _: b'{}')
        connection = SimpleNamespace(request=lambda *args, **kwargs: None,
                                     getresponse=lambda: response, close=lambda: None)
        inspect_pair = Mock()
        with patch.object(cli, 'checked_options', return_value=options), \
                patch.object(cli.socket, 'getaddrinfo', return_value=[]), \
                patch.dict('sys.modules', {'tls': SimpleNamespace(inspect_pair=inspect_pair)}), \
                patch.object(cli.http.client, 'HTTPConnection', return_value=connection) as http:
            result = cli.doctor()
        self.assertEqual('valid', result['configuration'])
        self.assertIn('resolves', result['dns'])
        self.assertEqual('configured certificate checked', result['certificate'])
        self.assertEqual('responding (HTTP 200)', result['api'])
        inspect_pair.assert_called_once()
        http.assert_called_once_with('127.0.0.1', 8080, timeout=3)

    def test_doctor_handles_bad_configuration_and_unreachable_services(self):
        for error in (ValueError('invalid'), TypeError('invalid'), AttributeError('invalid')):
            with self.subTest(error=type(error).__name__), \
                    patch.object(cli, 'checked_options', side_effect=error), \
                    patch.object(cli.socket, 'getaddrinfo') as dns, \
                    patch.object(cli.http.client, 'HTTPConnection') as http:
                invalid = cli.doctor()
            self.assertEqual('invalid', invalid['configuration'])
            dns.assert_not_called()
            http.assert_not_called()

        options = {'hostname': 'nocturne.example', 'authority': 'nocturne.example:8448',
                   'public_url': 'https://nocturne.example', 'certificate': '',
                   'private_key': ''}
        with patch.object(cli, 'checked_options', return_value=options), \
                patch.object(cli.socket, 'getaddrinfo', side_effect=OSError), \
                patch.object(cli.http.client, 'HTTPConnection', side_effect=OSError):
            unavailable = cli.doctor()
        self.assertEqual('does not resolve from this container', unavailable['dns'])
        self.assertIn('local test certificate', unavailable['certificate'])
        self.assertEqual('not reachable', unavailable['api'])

    def test_cli_emits_doctor_json_and_returns_api_failure_status(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(cli, 'doctor', return_value={'configuration': 'valid'}), \
                redirect_stdout(stdout):
            self.assertEqual(0, cli.main(['doctor']))
        self.assertEqual({'configuration': 'valid'}, json.loads(stdout.getvalue()))

        with patch.object(cli, 'api_request', side_effect=OSError('offline')), \
                redirect_stderr(stderr):
            self.assertEqual(1, cli.main(['api', '/api/v3/version']))
        self.assertIn('Diagnostics failed: offline', stderr.getvalue())

        for error in (TypeError('malformed'), AttributeError('malformed')):
            with self.subTest(error=type(error).__name__), \
                    patch.object(cli, 'checked_options', side_effect=error), \
                    redirect_stderr(stderr):
                self.assertEqual(1, cli.main(['api', '/api/v3/version']))
            self.assertIn('Diagnostics failed: malformed', stderr.getvalue())


if __name__ == '__main__':
    unittest.main()
