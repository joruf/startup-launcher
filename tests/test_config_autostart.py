"""Behavior tests for writing/removing the login autostart .desktop entry."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from config import autostart


class AutostartTestCase(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.autostart_dir = Path(self._tmpdir.name) / "autostart"
        patcher = patch.object(autostart, "AUTOSTART_DIR", self.autostart_dir)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.desktop_file = self.autostart_dir / autostart.AUTOSTART_DESKTOP_FILENAME


class TestAutostart(AutostartTestCase):
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

    def test_desktop_entry_does_not_depend_on_the_login_environment(self):
        autostart.enable()
        content = self.desktop_file.read_text(encoding="utf-8")
        exec_line = next(line for line in content.splitlines() if line.startswith("Exec="))
        interpreter = exec_line[len("Exec=") :].split('" "')[0].lstrip('"')
        self.assertTrue(interpreter.startswith("/"), f"interpreter must be absolute: {interpreter}")
        self.assertIn(f"Path={autostart.PROJECT_ROOT}", content)

    def test_desktop_entry_waits_for_the_desktop_to_come_up(self):
        autostart.enable()
        content = self.desktop_file.read_text(encoding="utf-8")
        self.assertIn(f"X-GNOME-Autostart-Delay={autostart.AUTOSTART_DELAY_SECONDS}", content)
        self.assertGreaterEqual(autostart.AUTOSTART_DELAY_SECONDS, 5)

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


class TestAutostartRefresh(AutostartTestCase):
    def test_up_to_date_entry_is_left_alone(self):
        autostart.enable()
        self.assertFalse(autostart.is_outdated())
        self.assertFalse(autostart.refresh_if_enabled())

    def test_entry_from_an_older_version_is_rewritten(self):
        self.autostart_dir.mkdir(parents=True, exist_ok=True)
        self.desktop_file.write_text(
            "[Desktop Entry]\nType=Application\nExec=python3 /somewhere/run.py\nName=Startup Launcher\n",
            encoding="utf-8",
        )
        self.assertTrue(autostart.is_outdated())
        self.assertTrue(autostart.refresh_if_enabled())
        self.assertIn("--autostart", self.desktop_file.read_text(encoding="utf-8"))

    def test_refresh_does_not_enable_autostart_behind_the_users_back(self):
        self.assertFalse(autostart.is_outdated())
        self.assertFalse(autostart.refresh_if_enabled())
        self.assertFalse(autostart.is_enabled())


if __name__ == "__main__":
    unittest.main()
