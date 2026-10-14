import importlib
from pathlib import Path
import subprocess
import sys
import unittest

BASE = Path(__file__).resolve().parents[1]
RUNTIME = BASE / 'shared/rootfs/opt/nocturne-ha'
sys.path.insert(0, str(RUNTIME))
settings = importlib.import_module('settings')


class CookieIsolationTests(unittest.TestCase):
    def test_shared_browser_jar_keeps_main_and_stable_separate_from_all_other_apps(self):
        script = '''
import assert from 'node:assert/strict';
const {default: adapter} = await import(process.argv[1]);
const namespaces = ['NocturneMain_', 'NocturneStable_', 'NocturneOfficial_',
  'NocturneLatest_', 'NocturnePersonal_', 'NocturneTestA_', 'NocturneTestB_', 'NocturneTestC_'];
const jar = namespaces.map((name, i) => name + '.Nocturne.RefreshToken=fixture-' + i).join('; ');
const attrs = '; Path=/; Domain=.example.net; Secure; HttpOnly; SameSite=Lax; Max-Age=604800';
for (const [i, namespace] of namespaces.entries()) {
  if (i > 1) continue;
  assert.equal(adapter.decode(jar, namespace), '.Nocturne.RefreshToken=fixture-' + i);
  assert.equal(adapter.decode('NocturneLatest_.Nocturne.RefreshToken=foreign; NocturneOfficial_.Nocturne.RefreshToken=foreign', namespace), '');
  const headers = adapter.encode(['.Nocturne.RefreshToken=rotated' + attrs], namespace, false);
  assert.equal(headers[0], namespace + '.Nocturne.RefreshToken=rotated' + attrs);
  const deletion = adapter.encode(['.Nocturne.RefreshToken=; Path=/; Max-Age=0'], namespace, false);
  assert.equal(deletion[0], namespace + '.Nocturne.RefreshToken=; Path=/; Max-Age=0');
}
'''
        subprocess.run(['node', '--input-type=module', '-e', script,
                        (RUNTIME / 'cookies.mjs').as_uri()], check=True, capture_output=True, text=True)

    def test_nginx_rejects_legacy_namespaces_and_uses_the_selected_app_namespace(self):
        for namespace in ('NocturneMain_', 'NocturneStable_'):
            options = settings.validate_options({})
            options['cookie_namespace'] = namespace
            self.assertIn(f'set $ha_cookie_namespace "{namespace}";',
                          settings.nginx_config(options, 'cert', 'key'))
        for namespace in ('NocturneLatest_', 'NocturneOfficial_'):
            options['cookie_namespace'] = namespace
            with self.assertRaises(ValueError):
                settings.nginx_config(options, 'cert', 'key')
