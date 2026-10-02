"""External origin configuration must agree across API and web."""
import importlib
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'shared/rootfs/opt/nocturne-ha'))
settings = importlib.import_module('settings')


class PublicOriginTests(unittest.TestCase):
    def test_api_and_web_keep_external_authority_and_internal_listeners(self):
        cases = [('https://mynocturne.duckdns.org:8451', 'mynocturne.duckdns.org:8451'),
                 ('https://mynocturne.duckdns.org:443', 'mynocturne.duckdns.org:443'),
                 ('https://mynocturne.duckdns.org', 'mynocturne.duckdns.org')]
        default = settings.validate_options({})['public_url']
        cases.append((default, default.removeprefix('https://')))
        for url, authority in cases:
            with self.subTest(url=url):
                options = settings.validate_options({'public_url': url})
                passwords = {key: 'synthetic-value' for key in settings.SECRET_FIELDS}
                api, web = settings.service_environments(options, passwords)
                self.assertEqual(authority, api['BASE_DOMAIN'])
                self.assertEqual(authority, web['BASE_DOMAIN'])
                self.assertEqual(url, options['public_url'])
                self.assertEqual('http://127.0.0.1:8080', api['ASPNETCORE_URLS'])
                self.assertEqual('http://127.0.0.1:8000', api['WEB_URL'])
                self.assertEqual('8000', web['PORT'])
                for key in ('NOCTURNE_API_HTTP', 'NOCTURNE_API_URL', 'PUBLIC_API_URL'):
                    self.assertEqual('http://127.0.0.1:8080', web[key])

    def test_native_host_matching_uses_hostname_without_external_port(self):
        options = settings.validate_options({
            'public_url': 'https://mynocturne.duckdns.org:8451',
            'certificate': 'fullchain.pem', 'private_key': 'privkey.pem',
            'gateway_auth': False})
        config = settings.nginx_config(options, 'cert', 'key')
        self.assertEqual('mynocturne.duckdns.org', options['hostname'])
        self.assertIn('server_name mynocturne.duckdns.org;', config)
        self.assertNotIn('server_name mynocturne.duckdns.org:8451;', config)
        self.assertIn('mynocturne.duckdns.org 1;', config)
        self.assertIn('if ($ha_host_allowed = 0) { return 421; }', config)
        self.assertIn('listen 8448 ssl;', config)
        self.assertIn('X-Forwarded-Host $http_host', config)

