"""GUI regression tests for the Settings dialog's validation/save contract."""

import os
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import patch

from config import settings as settings_store
from ui.settings_dialog import SettingsDialog

requires_display = unittest.skipUnless(
    os.environ.get("DISPLAY"), "requires a DISPLAY (X11/Xvfb) to create Tk widgets"
)


@requires_display
class SettingsDialogTestCase(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        patcher = patch.object(settings_store, "SETTINGS_FILE", Path(self._tmpdir.name) / "settings.json")
        patcher.start()
        self.addCleanup(patcher.stop)

        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"no usable display: {exc}")
        self.root.withdraw()
        self.addCleanup(self.root.destroy)

    def _dialog(self):
        dialog = SettingsDialog(self.root)
        self.addCleanup(dialog.destroy)
        return dialog


@requires_display
class TestSettingsDialog(SettingsDialogTestCase):
    def test_dialog_is_pre_filled_from_current_settings(self):
        settings_store.save_settings(
            {
                "scan_enabled": False,
                "scan_interval_minutes": 30,
                "launch_at_login": False,
                "restore_on_startup": True,
            }
        )
        dialog = self._dialog()
        self.assertFalse(dialog.scan_enabled_var.get())
        self.assertEqual(dialog.interval_var.get(), "30")
        self.assertFalse(dialog.launch_at_login_var.get())
        self.assertTrue(dialog.restore_var.get())

    def test_save_produces_expected_result_shape(self):
        dialog = self._dialog()
        dialog.scan_enabled_var.set(True)
        dialog.interval_var.set("15")
        dialog.launch_at_login_var.set(True)
        dialog.restore_var.set(True)
        dialog._save()
        self.assertEqual(
            dialog.result,
            {
                "scan_enabled": True,
                "scan_interval_minutes": 15,
                "launch_at_login": True,
                "restore_on_startup": True,
            },
        )

    def test_invalid_interval_falls_back_to_ten_minutes(self):
        dialog = self._dialog()
        dialog.interval_var.set("not-a-number")
        dialog._save()
        self.assertEqual(dialog.result["scan_interval_minutes"], 10)

    def test_zero_or_negative_interval_is_clamped_to_at_least_one(self):
        dialog = self._dialog()
        dialog.interval_var.set("-5")
        dialog._save()
        self.assertEqual(dialog.result["scan_interval_minutes"], 1)


if __name__ == "__main__":
    unittest.main()
