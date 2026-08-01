"""GUI regression tests for the New/Edit entry dialog's validation and save contract."""

import os
import tkinter as tk
import unittest

from tkinter import messagebox
from unittest.mock import patch

from ui.entry_dialog import EntryDialog

requires_display = unittest.skipUnless(
    os.environ.get("DISPLAY"), "requires a DISPLAY (X11/Xvfb) to create Tk widgets"
)


@requires_display
class EntryDialogTestCase(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"no usable display: {exc}")
        self.root.withdraw()
        self.addCleanup(self.root.destroy)

    def _dialog(self, entry=None):
        dialog = EntryDialog(self.root, entry=entry, existing_groups=["VSCode"])
        self.addCleanup(dialog.destroy)
        return dialog


@requires_display
class TestNewEntryDefaults(EntryDialogTestCase):
    def test_new_entry_defaults_to_normal_mode_and_enabled(self):
        dialog = self._dialog()
        self.assertEqual(dialog.mode_var.get(), "Normal")
        self.assertTrue(dialog._enabled)
        self.assertEqual(dialog.delay_var.get(), "0")


@requires_display
class TestEntryDialogValidation(EntryDialogTestCase):
    @patch("ui.entry_dialog.messagebox.showerror")
    def test_missing_name_is_rejected(self, mock_error):
        dialog = self._dialog()
        dialog.name_var.set("")
        dialog.command_text.delete("1.0", "end")
        dialog.command_text.insert("1.0", "firefox")
        dialog._save()
        mock_error.assert_called_once()
        self.assertIsNone(dialog.result)

    @patch("ui.entry_dialog.messagebox.showerror")
    def test_missing_command_is_rejected(self, mock_error):
        dialog = self._dialog()
        dialog.name_var.set("Browser")
        dialog._save()
        mock_error.assert_called_once()
        self.assertIsNone(dialog.result)

    @patch("ui.entry_dialog.messagebox.showerror")
    def test_non_normal_mode_without_match_string_is_rejected(self, mock_error):
        dialog = self._dialog()
        dialog.name_var.set("Browser")
        dialog.command_text.insert("1.0", "firefox")
        dialog.mode_var.set("Maximized")
        dialog.match_string_var.set("")
        dialog._save()
        mock_error.assert_called_once()
        self.assertIsNone(dialog.result)

    def test_valid_entry_produces_expected_result_shape(self):
        dialog = self._dialog()
        dialog.name_var.set("Browser")
        dialog.command_text.insert("1.0", "firefox --new-window")
        dialog.group_var.set("Browsers")
        dialog.mode_var.set("Maximized")
        dialog.match_mode_var.set("Window Class (WM_CLASS)")
        dialog.match_string_var.set("Firefox")
        dialog.delay_var.set("5")

        dialog._save()

        self.assertEqual(
            dialog.result,
            {
                "name": "Browser",
                "group": "Browsers",
                "command": "firefox --new-window",
                "window_mode": "maximized",
                "match_mode": "class",
                "match_string": "Firefox",
                "delay_seconds": 5,
                "enabled": True,
            },
        )

    def test_out_of_range_delay_falls_back_to_zero_instead_of_raising(self):
        dialog = self._dialog()
        dialog.name_var.set("Browser")
        dialog.command_text.insert("1.0", "firefox")
        dialog.delay_var.set("not-a-number")

        dialog._save()

        self.assertEqual(dialog.result["delay_seconds"], 0)

    def test_multiline_command_is_preserved_as_typed_not_flattened(self):
        dialog = self._dialog()
        dialog.name_var.set("Editor")
        dialog.command_text.insert("1.0", "code -n\n/home/user/project-a")

        dialog._save()

        self.assertEqual(dialog.result["command"], "code -n\n/home/user/project-a")


@requires_display
class TestEditingExistingEntry(EntryDialogTestCase):
    def test_dialog_is_pre_filled_from_the_given_entry(self):
        entry = {
            "name": "Editor A",
            "group": "VSCode",
            "command": "code -n /tmp/a",
            "window_mode": "maximized",
            "match_mode": "title",
            "match_string": "a - Visual Studio Code",
            "delay_seconds": 2,
            "enabled": False,
        }
        dialog = self._dialog(entry=entry)

        self.assertEqual(dialog.name_var.get(), "Editor A")
        self.assertEqual(dialog.group_var.get(), "VSCode")
        self.assertEqual(dialog.command_text.get("1.0", "end").strip(), "code -n /tmp/a")
        self.assertEqual(dialog.mode_var.get(), "Maximized")
        self.assertEqual(dialog.delay_var.get(), "2")
        self.assertFalse(dialog._enabled)

    def test_saving_an_edited_entry_preserves_its_enabled_state(self):
        entry = {"name": "Editor A", "command": "code", "window_mode": "normal", "enabled": False}
        dialog = self._dialog(entry=entry)
        dialog._save()
        self.assertFalse(dialog.result["enabled"])


if __name__ == "__main__":
    unittest.main()
