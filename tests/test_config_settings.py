"""Behavior tests for settings.json persistence and the clean-shutdown flag lifecycle."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from config import settings as settings_store


class TestSettings(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.settings_file = Path(self._tmpdir.name) / "settings.json"
        patcher = patch.object(settings_store, "SETTINGS_FILE", self.settings_file)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_missing_file_returns_defaults(self):
        self.assertEqual(settings_store.load_settings(), settings_store.DEFAULTS)

    def test_launching_entries_at_login_is_on_by_default(self):
        self.assertTrue(settings_store.load_settings()["launch_at_login"])

    def test_launching_entries_at_login_can_be_switched_off(self):
        settings_store.save_settings({"launch_at_login": False})
        self.assertFalse(settings_store.load_settings()["launch_at_login"])

    def test_partial_file_is_merged_over_defaults(self):
        settings_store.save_settings({"scan_interval_minutes": 30})
        loaded = settings_store.load_settings()
        self.assertEqual(loaded["scan_interval_minutes"], 30)
        self.assertEqual(loaded["scan_enabled"], settings_store.DEFAULTS["scan_enabled"])

    def test_save_round_trips_all_keys(self):
        settings_store.save_settings(
            {"scan_enabled": False, "scan_interval_minutes": 5, "restore_on_startup": True, "clean_shutdown": True}
        )
        loaded = settings_store.load_settings()
        self.assertFalse(loaded["scan_enabled"])
        self.assertEqual(loaded["scan_interval_minutes"], 5)
        self.assertTrue(loaded["restore_on_startup"])
        self.assertTrue(loaded["clean_shutdown"])

    def test_mark_session_started_clears_flag_and_returns_previous_value(self):
        settings_store.save_settings({"clean_shutdown": True})
        was_clean = settings_store.mark_session_started()
        self.assertTrue(was_clean)
        self.assertFalse(settings_store.load_settings()["clean_shutdown"])

    def test_mark_session_started_on_fresh_install_reports_not_clean(self):
        was_clean = settings_store.mark_session_started()
        self.assertFalse(was_clean)

    def test_mark_clean_shutdown_sets_flag(self):
        settings_store.mark_clean_shutdown()
        self.assertTrue(settings_store.load_settings()["clean_shutdown"])


if __name__ == "__main__":
    unittest.main()
