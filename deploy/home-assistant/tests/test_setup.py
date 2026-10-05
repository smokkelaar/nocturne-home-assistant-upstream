import http.server
import importlib
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import urllib.request
import urllib.error

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE / 'shared/rootfs/opt/nocturne-ha'))
sys.path.insert(0, str(BASE / 'tools'))
import help_ui
import run
from candidate import links, registry, paired_run, UpstreamNotReady
from check_locales import check


class SetupTests(unittest.TestCase):
    def test_error_specific_actions_are_prominent_in_every_language(self):
        for locale in help_ui.LANGUAGES:
            catalog = json.loads((BASE / 'shared/rootfs/opt/nocturne-ha/locales' / (locale + '.json')).read_text(encoding='utf-8'))
            for error in ('CERT_FILES', 'CERT_HOSTNAME', 'CERT_SAN', 'CERT_KEY_MISMATCH',
                          'CERT_EXPIRED', 'CERT_NOT_YET_VALID', 'SETUP_REQUIRED'):
                page = help_ui.render({'error': error}, locale)
                visible = page.split('<details>')[0]
                self.assertIn('role="alert"', visible)
                self.assertIn(error, visible)
                self.assertIn(catalog['error_' + error].split('\n')[0], visible)

    def test_ready_gateway_shows_username_and_help_does_not_leak_code_on_failure(self):
        page = help_ui.render({'ready': True, 'gateway': 'synthetic-code'})
        self.assertIn('Gateway username: nocturne', page)
        self.assertIn('synthetic-code', page)
        self.assertNotIn('synthetic-code', help_ui.render({'error': 'CERT_FILES', 'gateway': 'synthetic-code'}))

    def test_yaml_covers_dynamic_tenants_and_missing_invalid_domain_is_safe(self):
        page = help_ui.render({'public_url': 'https://example.duckdns.org:8448'})
        examples = page.split('<article id="wildcard-yaml">')[1].split('</article>')[0]
        self.assertIn('*.mynocturne.duckdns.org &gt; mynocturne.duckdns.org', examples)
        self.assertNotIn('example.duckdns.org', examples)
        self.assertIn('duckdns_token: YOUR_DUCKDNS_TOKEN', page)
        self.assertIn('CPU Percent', page)
        self.assertIn('Memory Percent', page)
        self.assertIn('mynocturne.duckdns.org', help_ui.render({'public_url': 'https://['}))

    def test_failed_native_guard_keeps_effective_gateway_without_changing_user_options(self):
        options = {'gateway_auth': False}
        with patch.object(run, 'verify_native_auth', side_effect=ValueError('GATEWAY_SETUP: test')):
            effective, code = run.effective_gateway(options)
        self.assertFalse(options['gateway_auth'])
        self.assertTrue(effective['gateway_auth'])
        self.assertEqual(code, 'GATEWAY_SETUP')
        for locale in help_ui.LANGUAGES:
            page = help_ui.render({'ready': True, 'gateway': 'fixture-code', 'gateway_issue': code, 'error': code}, locale)
            self.assertIn(code, page.split('<details>')[0])
            self.assertIn('fixture-code', page)

    def test_verified_native_mode_remains_off_and_unexpected_errors_are_not_hidden(self):
        with patch.object(run, 'verify_native_auth'):
            options, code = run.effective_gateway({'gateway_auth': False})
            self.assertFalse(options['gateway_auth'])
            self.assertEqual(code, '')
        with patch.object(run, 'verify_native_auth', side_effect=ValueError('unknown problem')):
            with self.assertRaises(ValueError):
                run.effective_gateway({'gateway_auth': False})

    def test_gateway_check_is_skipped_only_for_explicit_opt_in_with_gateway_off(self):
        with patch.object(run, 'verify_native_auth') as verify:
            effective, code = run.effective_gateway({'gateway_auth': False, 'skip_gateway_check': True})
            verify.assert_not_called()
            self.assertFalse(effective['gateway_auth'])
            self.assertEqual(code, 'GATEWAY_SKIPPED')
            effective, code = run.effective_gateway({'gateway_auth': True, 'skip_gateway_check': True})
            self.assertTrue(effective['gateway_auth'])
            self.assertEqual(code, '')
        spec = json.loads((BASE / 'shared/app-spec.json').read_text())
        self.assertFalse(spec['options']['skip_gateway_check'])
        for locale in help_ui.LANGUAGES:
            page = help_ui.render({'ready': True, 'error': 'GATEWAY_SKIPPED'}, locale)
            self.assertIn('GATEWAY_SKIPPED', page.split('<details>')[0])
        with self.assertRaisesRegex(ValueError, 'skip_gateway_check'):
            run.validate_options({'skip_gateway_check': 'true'})


    def test_share_permission_flag_is_not_a_substitute_for_actual_auth_denial(self):
        from unittest.mock import MagicMock
        for sharing in (True, False):
            for denial in (200, 401, 503):
                responses = []
                for status_code in (200, 401, denial):
                    connection = MagicMock()
                    response = connection.getresponse.return_value
                    response.status = status_code
                    response.read.return_value = json.dumps({'status': 'ok', 'runtimeState': 'loaded',
                        'anonymousReadAccess': sharing, 'isDemo': False}).encode()
                    responses.append(connection)
                with patch.object(run.http.client, 'HTTPConnection', side_effect=responses):
                    if denial == 401:
                        run.verify_native_auth({'authority': 'mynocturne.duckdns.org:8449'})
                    else:
                        with self.assertRaisesRegex(ValueError, 'GATEWAY_DENIAL'):
                            run.verify_native_auth({'authority': 'mynocturne.duckdns.org:8449'})
                responses[1].getresponse.return_value.read.assert_not_called()
                responses[2].getresponse.return_value.read.assert_not_called()

    def test_paired_run_rejects_success_for_other_source_revision(self):
        with patch('candidate.github', return_value={'workflow_runs': [
                {'head_sha': 'old', 'conclusion': 'success', 'id': 1}]}):
            with self.assertRaisesRegex(UpstreamNotReady, 'Upstream publication has not completed'):
                paired_run('current', 'main')

    def test_paired_run_requires_both_image_jobs_and_report(self):
        listing = {'workflow_runs': [{'head_sha': 'current', 'status': 'completed', 'conclusion': 'success', 'id': 1}]}
        for web_result in ['failure', 'success']:
            jobs = {'jobs': [{'name': name, 'conclusion': result} for name, result in
                    [('dotnet-images', 'success'), ('web-image', web_result), ('report', 'success')]]}
            with patch('candidate.github', side_effect=[listing, jobs]):
                if web_result == 'success':
                    self.assertEqual(paired_run('current', 'main'), 1)
                else:
                    with self.assertRaises(ValueError):
                        paired_run('current', 'main')

    def test_all_nocturne_languages_have_complete_rendered_help(self):
        check()
        for locale in help_ui.LANGUAGES:
            page = help_ui.render({'error': 'CERT_FILES'}, locale)
            self.assertIn(f'lang="{locale}"', page)
            self.assertIn('fullchain.pem', page)
            self.assertIn('privkey.pem', page)
            self.assertIn('CERT_FILES', page)
            self.assertNotIn('class="button"', page)

    def test_language_preference_and_browser_fallback(self):
        self.assertEqual(help_ui.language('', accepted='nl-NL,nl'), 'en')
        spec = json.loads((BASE / 'shared/app-spec.json').read_text())
        self.assertEqual(spec['options']['language'], 'en')
        self.assertEqual(help_ui.language('lang=fr', 'nl', 'de-DE,en'), 'fr')
        self.assertEqual(help_ui.language('lang=invalid', 'auto', 'de-DE,en'), 'de')
        self.assertEqual(help_ui.language('', 'ja', 'nl'), 'ja')
        self.assertEqual(help_ui.language('', 'auto', 'xx'), 'en')

    def test_ready_state_and_html_escaping(self):
        page = help_ui.render({'ready': True, 'public_url': 'https://nocturne.example.net', 'gateway': '<script>bad</script>'})
        self.assertIn('class="button"', page)
        self.assertIn('&lt;script&gt;', page)
        self.assertNotIn('<script>', page)
        self.assertNotIn('bad', help_ui.render({'ready': False, 'gateway': 'bad'}))

    def test_version_link_opens_upstream_tree_not_delivery_commit(self):
        result = links('a' * 40, 'v0.2.7', 'smokkelaar/nocturne-home-assistant-upstream', 'b' * 40, 123)
        self.assertEqual(result['source_url'], 'https://github.com/nightscout/nocturne/tree/' + 'a' * 40)
        self.assertIn('/releases/tag/v0.2.7', result['release_url'])
        self.assertIn('/tree/' + 'b' * 40 + '/deploy/home-assistant', result['wrapper_url'])
        main = links('a' * 40, None, 'smokkelaar/nocturne-home-assistant-upstream', 'b' * 40, 123)
        self.assertIsNone(main['release_url'])
        page = help_ui.render({'links': main, 'version': 'main@aaaaaaa'})
        self.assertNotIn('Release notes', page)

    def test_no_implicit_self_signed_certificate_in_production(self):
        with patch.dict('os.environ', {}, clear=True), tempfile.TemporaryDirectory() as tmp, patch.object(run, 'DATA', Path(tmp)):
            with self.assertRaisesRegex(ValueError, 'CERT_FILES'):
                run.prepare_tls({'certificate': '', 'hostname': 'example.net'})
            self.assertFalse((Path(tmp) / 'tls').exists())

    def test_direct_and_spoofed_ingress_clients_rejected(self):
        server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), help_ui.make_handler({'error': 'CERT_FILES'}))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            request = urllib.request.Request(f'http://127.0.0.1:{server.server_port}/', headers={'X-Forwarded-For': '172.30.32.2'})
            with self.assertRaises(urllib.error.HTTPError) as caught:
                urllib.request.urlopen(request)
            self.assertEqual(caught.exception.code, 403)
        finally:
            server.shutdown()
            server.server_close()

    def test_allowed_ingress_gets_help_during_setup_failure(self):
        class AllowedHandler(help_ui.make_handler({'error': 'CERT_FILES'})):
            def setup(self):
                super().setup()
                self.client_address = ('172.30.32.2', 1234)
        server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), AllowedHandler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{server.server_port}/?lang=nl') as response:
                page = response.read().decode('utf-8')
                self.assertIn('Nocturne installatiehulp', page)
                self.assertIn('CERT_FILES', page)
                self.assertEqual(response.headers['Cache-Control'], 'no-store')
        finally:
            server.shutdown()
            server.server_close()

    def test_wrong_platform_and_source_revision_refused(self):
        config = {'architecture': 'arm64', 'os': 'linux', 'config': {'Labels': {'org.opencontainers.image.revision': 'b' * 40}}}
        image = {'config': {'digest': 'sha256:config'}}
        with patch('candidate.fetch', side_effect=[({'token': 'synthetic'}, 't'), (image, 'm'), (config, 'sha256:config')]):
            with self.assertRaisesRegex(ValueError, 'platform'):
                registry('example/image', 'tag', 'amd64')
        with patch('candidate.fetch', side_effect=[({'token': 'synthetic'}, 't'), (image, 'm'), (config, 'sha256:config')]):
            with self.assertRaisesRegex(ValueError, 'revision'):
                registry('example/image', 'tag', 'arm64', 'a' * 40)


if __name__ == '__main__':
    unittest.main()
