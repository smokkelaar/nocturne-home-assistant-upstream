import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

BASE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('upstream_build_settings', BASE / 'shared/rootfs/opt/nocturne-ha/settings.py')
settings = importlib.util.module_from_spec(spec)
spec.loader.exec_module(settings)


class BuildMetadataTests(unittest.TestCase):
    def test_stable_and_main_keep_build_date_and_pinned_api_revision(self):
        for channel, commit in (('stable', '1' * 40), ('main', '2' * 40)):
            with self.subTest(channel=channel), tempfile.TemporaryDirectory() as directory:
                versions = {'source_commit': commit, 'channel': channel}
                result = settings.api_build_metadata(versions, Path(directory) / 'missing',
                    {'GIT_COMMIT': 'incorrect-parent', 'BUILD_DATE': '2026-10-05T18:00:00Z',
                     'SUPERVISOR_TOKEN': 'must-not-leak'})
                self.assertEqual({'GIT_COMMIT': commit, 'BUILD_DATE': '2026-10-05T18:00:00Z'}, result)

    def test_real_process_environment_exports_metadata_without_inheriting_secrets(self):
        with patch.dict(settings.os.environ, {'BUILD_DATE': '2026-10-05T18:00:00Z',
                                              'SUPERVISOR_TOKEN': 'must-not-leak'}, clear=True):
            api, web = settings.service_environments(settings.validate_options({}),
                {key: 'a' * 64 for key in settings.SECRET_FIELDS})
        self.assertEqual('2026-10-05T18:00:00Z', api['BUILD_DATE'])
        self.assertEqual(40, len(api['GIT_COMMIT']))
        self.assertNotIn('SUPERVISOR_TOKEN', api)
        self.assertNotIn('SUPERVISOR_TOKEN', web)
