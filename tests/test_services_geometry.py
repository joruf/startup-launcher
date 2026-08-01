"""Behavior tests for wmctrl-based window scanning/restoring (services/geometry.py)."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from models import geometry as geometry_model
from services import geometry as geometry_service

WMCTRL_LG_OUTPUT = (
    "0x02600007  0 100  200  1280 800  host Mozilla Firefox\n"
    "0x02a00003  0 -8   -8   1936 1096 host github desktop.GitHub Desktop\n"
    "not a matching line at all\n"
)


def _entry(**overrides):
    entry = {
        "id": "e1",
        "name": "Browser",
        "match_mode": "class",
        "match_string": "Firefox",
    }
    entry.update(overrides)
    return entry


class TestListWindows(unittest.TestCase):
    @patch("services.geometry.subprocess.run")
    def test_parses_wmctrl_lg_output_into_structured_windows(self, mock_run):
        mock_run.return_value = MagicMock(stdout=WMCTRL_LG_OUTPUT)
        windows = geometry_service._list_windows()
        self.assertEqual(len(windows), 2)
        self.assertEqual(windows[0], {"id": "0x02600007", "x": 100, "y": 200, "width": 1280, "height": 800, "title": "Mozilla Firefox"})
        self.assertEqual(windows[1]["title"], "github desktop.GitHub Desktop")
        self.assertEqual(windows[1]["x"], -8)

    @patch("services.geometry.subprocess.run", side_effect=OSError("wmctrl not found"))
    def test_missing_wmctrl_returns_empty_list(self, mock_run):
        self.assertEqual(geometry_service._list_windows(), [])


class TestWindowClass(unittest.TestCase):
    @patch("services.geometry.subprocess.run")
    def test_returns_xprop_stdout(self, mock_run):
        mock_run.return_value = MagicMock(stdout='WM_CLASS(STRING) = "Navigator", "Firefox"\n')
        self.assertIn("Firefox", geometry_service._window_class("0x1"))

    @patch("services.geometry.subprocess.run", side_effect=OSError("xprop not found"))
    def test_missing_xprop_returns_empty_string(self, mock_run):
        self.assertEqual(geometry_service._window_class("0x1"), "")


class TestFindWindow(unittest.TestCase):
    def setUp(self):
        self.windows = [
            {"id": "0x1", "x": 0, "y": 0, "width": 100, "height": 100, "title": "project-a - Visual Studio Code"},
            {"id": "0x2", "x": 0, "y": 0, "width": 100, "height": 100, "title": "project-b - Visual Studio Code"},
        ]

    def test_empty_match_string_finds_nothing(self):
        self.assertIsNone(geometry_service._find_window(_entry(match_string=""), self.windows))

    def test_title_match_is_case_insensitive_substring(self):
        found = geometry_service._find_window(
            _entry(match_mode="title", match_string="PROJECT-B"), self.windows
        )
        self.assertEqual(found["id"], "0x2")

    def test_title_match_returns_none_when_no_window_matches(self):
        found = geometry_service._find_window(_entry(match_mode="title", match_string="project-z"), self.windows)
        self.assertIsNone(found)

    @patch("services.geometry._window_class")
    def test_class_match_checks_wm_class_via_xprop(self, mock_window_class):
        mock_window_class.side_effect = lambda window_id: "Firefox" if window_id == "0x2" else "Code"
        found = geometry_service._find_window(_entry(match_mode="class", match_string="firefox"), self.windows)
        self.assertEqual(found["id"], "0x2")


class TestClearAndApplyGeometry(unittest.TestCase):
    @patch("services.geometry.subprocess.run")
    def test_unmaximizes_then_moves_by_title(self, mock_run):
        log = MagicMock()
        geometry_service._clear_and_apply_geometry(
            _entry(match_mode="title", match_string="project-a"),
            {"x": 10, "y": 20, "width": 800, "height": 600},
            log,
        )
        unmaximize_call, move_call = mock_run.call_args_list
        self.assertEqual(
            unmaximize_call.args[0],
            ["wmctrl", "-r", "project-a", "-b", "remove,maximized_vert,maximized_horz,fullscreen"],
        )
        self.assertEqual(move_call.args[0], ["wmctrl", "-r", "project-a", "-e", "0,10,20,800,600"])
        log.assert_called_once_with("Browser: position restored.")

    @patch("services.geometry.subprocess.run")
    def test_class_match_passes_dash_x_to_wmctrl(self, mock_run):
        geometry_service._clear_and_apply_geometry(
            _entry(match_mode="class", match_string="Firefox"),
            {"x": 0, "y": 0, "width": 100, "height": 100},
            MagicMock(),
        )
        for call in mock_run.call_args_list:
            self.assertEqual(call.args[0][:2], ["wmctrl", "-x"])


class TestScanAndStoreRestoreForget(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.geometry_file = Path(self._tmpdir.name) / "window_geometry.json"
        patcher = patch.object(geometry_model, "GEOMETRY_FILE", self.geometry_file)
        patcher.start()
        self.addCleanup(patcher.stop)

    @patch("services.geometry._list_windows", return_value=[])
    def test_scan_with_no_open_windows_logs_and_stores_nothing(self, mock_list):
        log = MagicMock()
        geometry_service.scan_and_store([_entry()], log=log)
        self.assertEqual(geometry_model.load_geometry(), {})
        self.assertTrue(any("no windows found" in call.args[0] for call in log.call_args_list))

    @patch("services.geometry._list_windows")
    def test_scan_skips_entries_without_a_match_string(self, mock_list):
        mock_list.return_value = [{"id": "0x1", "x": 1, "y": 1, "width": 1, "height": 1, "title": "x"}]
        geometry_service.scan_and_store([_entry(match_string="")])
        self.assertEqual(geometry_model.load_geometry(), {})

    @patch("services.geometry._window_class", return_value="Firefox")
    @patch("services.geometry._list_windows")
    def test_scan_stores_position_for_matched_entry(self, mock_list, mock_class):
        mock_list.return_value = [{"id": "0x1", "x": 10, "y": 20, "width": 800, "height": 600, "title": "x"}]
        log = MagicMock()
        geometry_service.scan_and_store([_entry()], log=log)
        self.assertEqual(
            geometry_model.load_geometry()["e1"], {"x": 10, "y": 20, "width": 800, "height": 600}
        )
        self.assertTrue(any("1 position(s) saved" in call.args[0] for call in log.call_args_list))

    def test_restore_without_saved_position_logs_and_does_nothing(self):
        log = MagicMock()
        geometry_service.restore_geometry(_entry(), log=log)
        self.assertTrue(any("no saved position yet" in call.args[0] for call in log.call_args_list))

    def test_restore_without_match_string_logs_and_does_nothing(self):
        geometry_model.save_geometry({"e1": {"x": 0, "y": 0, "width": 1, "height": 1}})
        log = MagicMock()
        geometry_service.restore_geometry(_entry(match_string=""), log=log)
        self.assertTrue(any("no window match configured" in call.args[0] for call in log.call_args_list))

    @patch("services.geometry._list_windows", return_value=[])
    def test_restore_when_window_not_open_logs_and_does_nothing(self, mock_list):
        geometry_model.save_geometry({"e1": {"x": 0, "y": 0, "width": 1, "height": 1}})
        log = MagicMock()
        geometry_service.restore_geometry(_entry(), log=log)
        self.assertTrue(any("is not currently open" in call.args[0] for call in log.call_args_list))

    @patch("services.geometry._clear_and_apply_geometry")
    @patch("services.geometry._window_class", return_value="Firefox")
    @patch("services.geometry._list_windows")
    def test_restore_applies_geometry_when_window_is_open(self, mock_list, mock_class, mock_apply):
        mock_list.return_value = [{"id": "0x1", "x": 0, "y": 0, "width": 1, "height": 1, "title": "x"}]
        geometry_model.save_geometry({"e1": {"x": 5, "y": 5, "width": 300, "height": 200}})
        geometry_service.restore_geometry(_entry(), log=MagicMock())
        mock_apply.assert_called_once()

    @patch("services.geometry.time.sleep")
    def test_wait_and_restore_without_saved_position_returns_immediately(self, mock_sleep):
        geometry_service.wait_and_restore_geometry(_entry(), log=MagicMock())
        mock_sleep.assert_not_called()

    @patch("services.geometry._clear_and_apply_geometry")
    @patch("services.geometry._window_class", return_value="Firefox")
    @patch("services.geometry._list_windows")
    def test_wait_and_restore_applies_geometry_once_window_appears(self, mock_list, mock_class, mock_apply):
        mock_list.return_value = [{"id": "0x1", "x": 0, "y": 0, "width": 1, "height": 1, "title": "x"}]
        geometry_model.save_geometry({"e1": {"x": 5, "y": 5, "width": 300, "height": 200}})
        geometry_service.wait_and_restore_geometry(_entry(), log=MagicMock())
        mock_apply.assert_called_once()

    @patch("services.geometry.time.sleep")
    @patch("services.geometry._list_windows", return_value=[])
    def test_wait_and_restore_times_out_and_logs(self, mock_list, mock_sleep):
        geometry_model.save_geometry({"e1": {"x": 5, "y": 5, "width": 300, "height": 200}})
        log = MagicMock()
        with patch.object(geometry_service, "WAIT_TIMEOUT_SECONDS", 0):
            geometry_service.wait_and_restore_geometry(_entry(), log=log)
        self.assertTrue(any("could not restore position" in call.args[0] for call in log.call_args_list))

    def test_forget_removes_only_the_given_ids(self):
        geometry_model.save_geometry({"keep": {"x": 0, "y": 0, "width": 1, "height": 1}, "drop": {"x": 0, "y": 0, "width": 1, "height": 1}})
        geometry_service.forget(["drop", "unknown-id"])
        self.assertEqual(list(geometry_model.load_geometry().keys()), ["keep"])

    def test_forget_with_no_matching_ids_does_not_rewrite_file(self):
        geometry_model.save_geometry({"keep": {"x": 0, "y": 0, "width": 1, "height": 1}})
        before = self.geometry_file.stat().st_mtime_ns
        geometry_service.forget(["unrelated"])
        after = self.geometry_file.stat().st_mtime_ns
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
