"""GUI regression tests for the main application window.

These drive real Tk/ttk widgets, so they need a real or virtual (Xvfb) X11
display and are skipped entirely where DISPLAY isn't set (see ci.yml/os-matrix.yml,
which run the suite under xvfb-run).
"""

import json
import os
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from config import settings as settings_store
from models import entries as entry_model
from models import geometry as geometry_model
from services import instance_ipc
from ui import main_window

requires_display = unittest.skipUnless(
    os.environ.get("DISPLAY"), "requires a DISPLAY (X11/Xvfb) to create Tk widgets"
)


def _sample_entries():
    return [
        {
            "id": "standalone",
            "name": "Browser",
            "group": "",
            "command": "firefox",
            "window_mode": "normal",
            "match_mode": "class",
            "match_string": "Firefox",
            "delay_seconds": 0,
            "enabled": True,
        },
        {
            "id": "vscode-a",
            "name": "Editor A",
            "group": "VSCode",
            "command": "code -n /tmp/a",
            "window_mode": "maximized",
            "match_mode": "title",
            "match_string": "a - Visual Studio Code",
            "delay_seconds": 2,
            "enabled": True,
        },
        {
            "id": "vscode-b",
            "name": "Editor B",
            "group": "VSCode",
            "command": "code -n /tmp/b",
            "window_mode": "maximized",
            "match_mode": "title",
            "match_string": "b - Visual Studio Code",
            "delay_seconds": 2,
            "enabled": False,
        },
    ]


@requires_display
class MainWindowTestCase(unittest.TestCase):
    """Builds an isolated StartupLauncherApp against temp data files for each test."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        tmp = Path(self._tmpdir.name)

        self.entries_file = tmp / "entries.json"
        self.geometry_file = tmp / "window_geometry.json"
        self.settings_file = tmp / "settings.json"
        self.socket_file = tmp / "control.sock"

        self.entries_file.write_text(json.dumps(_sample_entries()), encoding="utf-8")

        patches = [
            patch.object(entry_model, "ENTRIES_FILE", self.entries_file),
            patch.object(entry_model, "EXAMPLE_ENTRIES_FILE", tmp / "entries.example.json"),
            patch.object(main_window, "ENTRIES_FILE", self.entries_file),
            patch.object(geometry_model, "GEOMETRY_FILE", self.geometry_file),
            patch.object(settings_store, "SETTINGS_FILE", self.settings_file),
            patch.object(instance_ipc, "SOCKET_FILE", self.socket_file),
            patch.object(main_window.StartupLauncherApp, "_start_tray_icon", lambda self: None),
            patch.object(main_window.StartupLauncherApp, "_start_control_server", lambda self: None),
        ]
        for patcher in patches:
            patcher.start()
            self.addCleanup(patcher.stop)

        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"no usable display: {exc}")
        self.addCleanup(self._destroy_root)

        self.app = main_window.StartupLauncherApp(self.root, auto_run=False)
        self.root.deiconify()
        self._pump()

    def _destroy_root(self):
        try:
            for job_id in self.root.tk.call("after", "info"):
                self.root.after_cancel(job_id)
            self.root.destroy()
        except tk.TclError:
            pass

    def _pump(self):
        for _ in range(5):
            self.root.update()

    def _click(self, widget, x, y):
        widget.event_generate("<ButtonPress-1>", x=x, y=y)
        widget.event_generate("<ButtonRelease-1>", x=x, y=y)
        self._pump()

    def _double_click(self, widget, x, y):
        self._click(widget, x, y)
        self._click(widget, x, y)

    def _entries_on_disk(self):
        return json.loads(self.entries_file.read_text(encoding="utf-8"))


@requires_display
class TestInlineEditOpening(MainWindowTestCase):
    def test_single_click_on_name_does_not_open_the_editor(self):
        bbox = self.app.tree.bbox("e0")
        self._click(self.app.tree, 10, bbox[1] + bbox[3] // 2)
        self.assertIsNone(self.app._active_edit)

    def test_double_click_on_name_opens_editor_with_current_text(self):
        bbox = self.app.tree.bbox("e0")
        self._double_click(self.app.tree, 10, bbox[1] + bbox[3] // 2)
        self.assertIsNotNone(self.app._active_edit)
        self.assertEqual(self.app._active_edit["widget"].get(), "Browser")

    def test_editor_survives_the_double_clicks_own_dispatch(self):
        # Regression guard: opening takes two raw Button-1 presses, both of which
        # also reach the global click-outside-closes-the-editor handler right
        # after. If the suppress counter only covered one of them, the editor
        # would immediately destroy itself the instant it opened.
        bbox = self.app.tree.bbox("e0")
        self._double_click(self.app.tree, 10, bbox[1] + bbox[3] // 2)
        self._pump()
        self.assertIsNotNone(self.app._active_edit)

    def test_double_click_on_a_group_row_does_not_open_an_editor(self):
        bbox = self.app.tree.bbox("g:VSCode")
        self._double_click(self.app.tree, 10, bbox[1] + bbox[3] // 2)
        self.assertIsNone(self.app._active_edit)


@requires_display
class TestInlineEditCommitCancel(MainWindowTestCase):
    def _open_name_editor(self, iid="e0"):
        bbox = self.app.tree.bbox(iid)
        self._double_click(self.app.tree, 10, bbox[1] + bbox[3] // 2)
        self.assertIsNotNone(self.app._active_edit)

    def test_a_later_click_elsewhere_commits_the_edit(self):
        self._open_name_editor()
        self.app._active_edit["var"].set("Renamed Browser")
        # A real click in the tree's empty body area (below the header and all
        # rows, so it neither triggers a header-click sort nor selects another
        # row) - exercises the actual global-click-closes-the-editor path,
        # rather than calling _commit_inline_edit() directly.
        self._click(self.app.tree, 5, 500)
        self.assertIsNone(self.app._active_edit)
        self.assertEqual(self.app.entries[0]["name"], "Renamed Browser")
        self.assertEqual(self._entries_on_disk()[0]["name"], "Renamed Browser")

    def test_escape_cancels_without_saving(self):
        self._open_name_editor()
        self.app._active_edit["var"].set("Should Not Be Saved")
        self.app._cancel_inline_edit()
        self.assertIsNone(self.app._active_edit)
        self.assertEqual(self.app.entries[0]["name"], "Browser")

    def test_blank_name_is_rejected_and_keeps_the_old_value(self):
        self._open_name_editor()
        self.app._active_edit["var"].set("   ")
        self.app._commit_inline_edit()
        self.assertEqual(self.app.entries[0]["name"], "Browser")

    def test_command_quick_edit_commits_flattened_text(self):
        bbox = self.app.tree.bbox("e0", column="command")
        self._double_click(self.app.tree, bbox[0] + 5, bbox[1] + bbox[3] // 2)
        self.assertEqual(self.app._active_edit["field"], "command")
        self.app._active_edit["var"].set("firefox --private-window")
        self.app._commit_inline_edit()
        self.assertEqual(self.app.entries[0]["command"], "firefox --private-window")

    def test_delay_edit_clamps_out_of_range_value(self):
        bbox = self.app.tree.bbox("e0", column="delay")
        self._double_click(self.app.tree, bbox[0] + 5, bbox[1] + bbox[3] // 2)
        self.app._active_edit["var"].set("999")
        self.app._commit_inline_edit()
        self.assertEqual(self.app.entries[0]["delay_seconds"], entry_model.MAX_DELAY_SECONDS)

    def test_delay_edit_rejects_non_numeric_value(self):
        self.app.entries[0]["delay_seconds"] = 3
        bbox = self.app.tree.bbox("e0", column="delay")
        self._double_click(self.app.tree, bbox[0] + 5, bbox[1] + bbox[3] // 2)
        self.app._active_edit["var"].set("abc")
        self.app._commit_inline_edit()
        self.assertEqual(self.app.entries[0]["delay_seconds"], 3)

    def test_xy_edit_writes_valid_position_to_geometry_store(self):
        bbox = self.app.tree.bbox("e0", column="xy")
        self._double_click(self.app.tree, bbox[0] + 5, bbox[1] + bbox[3] // 2)
        self.app._active_edit["var"].set("100, 200")
        self.app._commit_inline_edit()
        saved = geometry_model.load_geometry()["standalone"]
        self.assertEqual((saved["x"], saved["y"]), (100, 200))

    def test_size_edit_writes_valid_size_to_geometry_store(self):
        bbox = self.app.tree.bbox("e0", column="size")
        self._double_click(self.app.tree, bbox[0] + 5, bbox[1] + bbox[3] // 2)
        self.app._active_edit["var"].set("1920x1080")
        self.app._commit_inline_edit()
        saved = geometry_model.load_geometry()["standalone"]
        self.assertEqual((saved["width"], saved["height"]), (1920, 1080))

    def test_invalid_xy_format_is_rejected_without_crashing(self):
        bbox = self.app.tree.bbox("e0", column="xy")
        self._double_click(self.app.tree, bbox[0] + 5, bbox[1] + bbox[3] // 2)
        self.app._active_edit["var"].set("not-a-position")
        self.app._commit_inline_edit()
        self.assertNotIn("standalone", geometry_model.load_geometry())


@requires_display
class TestCheckboxToggling(MainWindowTestCase):
    def test_clicking_a_single_entrys_checkbox_toggles_it(self):
        self.app._checkbox_labels["e0"].event_generate("<Button-1>")
        self._pump()
        self.assertFalse(self.app.entries[0]["enabled"])
        self.assertFalse(self._entries_on_disk()[0]["enabled"])

    def test_group_checkbox_shows_partial_when_members_disagree(self):
        # vscode-a is enabled, vscode-b is not -> group should render mixed.
        self.assertEqual(self.app.tree.set("g:VSCode", "enabled"), main_window.PARTIAL)

    def test_clicking_the_group_checkbox_enables_all_members(self):
        self.app._checkbox_labels["g:VSCode"].event_generate("<Button-1>")
        self._pump()
        self.assertTrue(self.app.entries[1]["enabled"])
        self.assertTrue(self.app.entries[2]["enabled"])
        self.assertEqual(self.app.tree.set("g:VSCode", "enabled"), main_window.CHECKED)

    def test_clicking_an_already_all_enabled_group_disables_all_members(self):
        self.app._toggle_group("VSCode")  # first click: mixed -> all enabled
        self.app._checkbox_labels["g:VSCode"].event_generate("<Button-1>")
        self._pump()
        self.assertFalse(self.app.entries[1]["enabled"])
        self.assertFalse(self.app.entries[2]["enabled"])


@requires_display
class TestLaunchButton(MainWindowTestCase):
    @patch("ui.main_window.launcher.launch_entry")
    def test_clicking_launch_on_an_entry_row_starts_only_that_entry(self, mock_launch):
        self.app._launch_labels["e0"].event_generate("<Button-1>")
        self._pump()
        mock_launch.assert_called_once()
        self.assertEqual(mock_launch.call_args.args[0]["id"], "standalone")

    @patch("ui.main_window.launcher.launch_entry")
    def test_clicking_launch_on_a_group_row_starts_every_member(self, mock_launch):
        self.app._launch_labels["g:VSCode"].event_generate("<Button-1>")
        self._pump()
        started_ids = {call.args[0]["id"] for call in mock_launch.call_args_list}
        self.assertEqual(started_ids, {"vscode-a", "vscode-b"})


@requires_display
class TestSorting(MainWindowTestCase):
    def test_sort_by_name_orders_entries_ascending_then_toggles_to_descending(self):
        self.app._sort_by("#0")
        self.assertEqual([e["name"] for e in self.app.entries], ["Browser", "Editor A", "Editor B"])

        self.app._sort_by("#0")
        self.assertEqual([e["name"] for e in self.app.entries], ["Editor B", "Editor A", "Browser"])

    def test_sort_order_is_persisted_to_disk(self):
        self.app._sort_by("#0")
        self.assertEqual([e["name"] for e in self._entries_on_disk()], ["Browser", "Editor A", "Editor B"])

    def test_sort_by_delay_groups_by_delay_value(self):
        self.app._sort_by("delay")
        self.assertEqual([e["delay_seconds"] for e in self.app.entries], [0, 2, 2])


@requires_display
class TestMoveUpDown(MainWindowTestCase):
    def test_move_down_swaps_with_the_next_entry(self):
        self.app.tree.selection_set("e0")
        self.app._move_selected(1)
        self.assertEqual(self.app.entries[0]["id"], "vscode-a")
        self.assertEqual(self.app.entries[1]["id"], "standalone")

    def test_move_up_at_the_top_is_a_no_op(self):
        self.app.tree.selection_set("e0")
        self.app._move_selected(-1)
        self.assertEqual(self.app.entries[0]["id"], "standalone")

    def test_move_selected_on_a_group_row_is_a_no_op(self):
        self.app.tree.selection_set("g:VSCode")
        self.app._move_selected(1)
        self.assertEqual([e["id"] for e in self.app.entries], ["standalone", "vscode-a", "vscode-b"])


@requires_display
class TestDeleteEntry(MainWindowTestCase):
    @patch("ui.main_window.messagebox.askyesno", return_value=True)
    def test_confirmed_delete_removes_the_entry_and_forgets_its_geometry(self, _mock_confirm):
        geometry_model.save_geometry({"standalone": {"x": 1, "y": 1, "width": 1, "height": 1}})
        self.app.tree.selection_set("e0")
        self.app._delete_selected()
        self.assertNotIn("standalone", [e["id"] for e in self.app.entries])
        self.assertNotIn("standalone", geometry_model.load_geometry())

    @patch("ui.main_window.messagebox.askyesno", return_value=False)
    def test_declined_delete_keeps_the_entry(self, _mock_confirm):
        self.app.tree.selection_set("e0")
        self.app._delete_selected()
        self.assertIn("standalone", [e["id"] for e in self.app.entries])

    @patch("ui.main_window.messagebox.askyesno", return_value=True)
    def test_confirmed_group_delete_removes_every_member(self, _mock_confirm):
        self.app.tree.selection_set("g:VSCode")
        self.app._delete_selected()
        remaining_ids = [e["id"] for e in self.app.entries]
        self.assertEqual(remaining_ids, ["standalone"])


@requires_display
class TestExternalEntriesFileChange(MainWindowTestCase):
    def test_external_change_is_picked_up_and_reloads_the_table(self):
        new_entries = _sample_entries()
        new_entries[0]["name"] = "Changed On Disk"
        # Force a distinguishable mtime even on coarse-grained filesystems.
        os.utime(self.entries_file, ns=(0, 0))
        self.entries_file.write_text(json.dumps(new_entries), encoding="utf-8")

        self.app._check_entries_file_changed()

        self.assertEqual(self.app.entries[0]["name"], "Changed On Disk")

    def test_no_change_does_not_reload(self):
        original_entries_object = self.app.entries
        self.app._check_entries_file_changed()
        self.assertIs(self.app.entries, original_entries_object)


if __name__ == "__main__":
    unittest.main()
