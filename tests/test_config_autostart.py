"""Behavior tests for writing/removing the login autostart .desktop entry."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from config import autostart


class TestAutostart(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.autostart_dir = Path(self._tmpdir.name) / "autostart"
        patcher = patch.object(autostart, "AUTOSTART_DIR", self.autostart_dir)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.desktop_file = self.autostart_dir / autostart.AUTOSTART_DESKTOP_FILENAME

    def test_disabled_by_default(self):
        self.assertFalse(autostart.is_enabled())

    def test_enable_creates_desktop_entry_directory_and_file(self):
        autostart.enable()
        self.assertTrue(autostart.is_enabled())
        self.assertTrue(self.desktop_file.is_file())

    def test_enabled_desktop_entry_launches_with_autostart_flag(self):
        autostart.enable()
        content = self.desktop_file.read_text(encoding="utf-8")
        self.assertIn("--autostart", content)
        self.assertIn("Type=Application", content)

    def test_disable_removes_the_file(self):
        autostart.enable()
        autostart.disable()
        self.assertFalse(autostart.is_enabled())

    def test_disable_without_prior_enable_does_not_raise(self):
        autostart.disable()
        self.assertFalse(autostart.is_enabled())

    def test_enable_is_idempotent(self):
        autostart.enable()
        autostart.enable()
        self.assertTrue(autostart.is_enabled())


if __name__ == "__main__":
    unittest.main()
