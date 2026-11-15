"""A working database migration keeps the API startup wait open."""
import importlib
from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'shared/rootfs/opt/nocturne-ha'))
runtime = importlib.import_module('run')


class Clock:
    now = 0.0

    def monotonic(self):
        return self.now


class MigrationWaitTests(unittest.TestCase):
    def supervisor(self, clock):
        supervisor = runtime.Supervisor.__new__(runtime.Supervisor)
        supervisor.children, supervisor.status = [], {}
        supervisor.stop = threading.Event()
        supervisor.stop.wait = lambda seconds: setattr(clock, 'now', clock.now + seconds)
        return supervisor

    def test_active_migration_can_complete_after_base_timeout(self):
        clock = Clock()
        supervisor = self.supervisor(clock)
        with patch.object(runtime.time, 'monotonic', clock.monotonic), patch.object(runtime, 'log'):
            supervisor.wait_for('API', lambda: clock.now >= 5000, 3600,
                                lambda: (True, ['database migration active']))
        self.assertGreaterEqual(clock.now, 5000)

    def test_idle_migration_wait_times_out(self):
        clock = Clock()
        supervisor = self.supervisor(clock)
        with patch.object(runtime.time, 'monotonic', clock.monotonic), patch.object(runtime, 'log'), \
                self.assertRaises(RuntimeError):
            supervisor.wait_for('API', lambda: False, 3600, lambda: (False, []))
        self.assertLessEqual(clock.now, 3601)

    def test_progress_has_no_query_text(self):
        with patch.object(runtime, 'psql', side_effect=['312|Lock/transactionid|1', '2104 MB']):
            busy, lines = runtime.database_progress()
        self.assertTrue(busy)
        self.assertEqual('database 2104 MB', lines[0])
        self.assertIn('312 s active (Lock/transactionid, blocked by 1', lines[1])


if __name__ == '__main__':
    unittest.main()
