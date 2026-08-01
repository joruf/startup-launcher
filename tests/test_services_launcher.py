"""Behavior tests for process launching and wmctrl-based window state (services/launcher.py)."""

import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from services import launcher


def _entry(**overrides):
    entry = {
        "id": "e1",
        "name": "Browser",
        "command": "firefox",
        "window_mode": "normal",
        "match_mode": "class",
        "match_string": "Firefox",
        "delay_seconds": 0,
        "enabled": True,
    }
    entry.update(overrides)
    return entry


class TestFlattenCommand(unittest.TestCase):
    def test_joins_multiline_command_into_one_line(self):
        command = "code -n\n  /home/user/project-a\n  /home/user/project-b\n"
        self.assertEqual(launcher._flatten_command(command), "code -n /home/user/project-a /home/user/project-b")

    def test_ignores_blank_lines(self):
        self.assertEqual(launcher._flatten_command("firefox\n\n\n"), "firefox")

    def test_single_line_is_unchanged(self):
        self.assertEqual(launcher._flatten_command("firefox --new-window"), "firefox --new-window")


class TestLaunchEntry(unittest.TestCase):
    def setUp(self):
        self.log = MagicMock()

    @patch("services.launcher.subprocess.Popen")
    def test_starts_process_with_parsed_args_in_home_directory(self, mock_popen):
        launcher.launch_entry(_entry(command="firefox --new-window"), log=self.log)
        args, kwargs = mock_popen.call_args
        self.assertEqual(args[0], ["firefox", "--new-window"])
        self.assertEqual(kwargs["cwd"], str(Path.home()))
        self.log.assert_any_call("Browser: started.")

    @patch("services.launcher.subprocess.Popen")
    def test_unparseable_command_is_not_launched(self, mock_popen):
        launcher.launch_entry(_entry(command='"unterminated'), log=self.log)
        mock_popen.assert_not_called()
        self.assertTrue(any("could not parse" in call.args[0] for call in self.log.call_args_list))

    @patch("services.launcher.subprocess.Popen")
    def test_blank_command_is_not_launched(self, mock_popen):
        launcher.launch_entry(_entry(command="   "), log=self.log)
        mock_popen.assert_not_called()
        self.assertTrue(any("no command configured" in call.args[0] for call in self.log.call_args_list))

    @patch("services.launcher.subprocess.Popen", side_effect=OSError("not found"))
    def test_popen_failure_is_logged_not_raised(self, mock_popen):
        launcher.launch_entry(_entry(), log=self.log)
        self.assertTrue(any("failed to start" in call.args[0] for call in self.log.call_args_list))

    @patch("services.launcher.threading.Thread")
    @patch("services.launcher.subprocess.Popen")
    def test_normal_window_mode_without_geometry_restore_starts_no_background_thread(
        self, mock_popen, mock_thread
    ):
        launcher.launch_entry(_entry(window_mode="normal"), log=self.log)
        mock_thread.assert_not_called()

    @patch("services.launcher.threading.Thread")
    @patch("services.launcher.subprocess.Popen")
    def test_non_normal_window_mode_applies_window_state_in_background_thread(self, mock_popen, mock_thread):
        launcher.launch_entry(_entry(window_mode="maximized"), log=self.log)
        mock_thread.assert_called_once()
        _args, kwargs = mock_thread.call_args
        self.assertIs(kwargs["target"], launcher._apply_window_state)
        mock_thread.return_value.start.assert_called_once()

    @patch("services.launcher.threading.Thread")
    @patch("services.launcher.subprocess.Popen")
    def test_geometry_restore_callback_runs_instead_of_window_state(self, mock_popen, mock_thread):
        restore = MagicMock()
        launcher.launch_entry(_entry(window_mode="maximized"), log=self.log, geometry_restore=restore)
        _args, kwargs = mock_thread.call_args
        self.assertIs(kwargs["target"], restore)


class TestLaunchEntries(unittest.TestCase):
    def setUp(self):
        self.log = MagicMock()

    @patch("services.launcher.launch_entry")
    def test_disabled_entries_are_skipped(self, mock_launch_entry):
        launcher.launch_entries([_entry(enabled=False)], log=self.log)
        mock_launch_entry.assert_not_called()

    @patch("services.launcher.launch_entry")
    def test_entries_missing_enabled_key_default_to_enabled(self, mock_launch_entry):
        entry = _entry()
        del entry["enabled"]
        launcher.launch_entries([entry], log=self.log)
        mock_launch_entry.assert_called_once()

    @patch("services.launcher.launch_entry")
    def test_zero_delay_launches_immediately(self, mock_launch_entry):
        launcher.launch_entries([_entry(delay_seconds=0)], log=self.log)
        mock_launch_entry.assert_called_once_with(_entry(delay_seconds=0), log=self.log, geometry_restore=None)

    @patch("services.launcher.threading.Timer")
    @patch("services.launcher.launch_entry")
    def test_positive_delay_schedules_a_timer_instead_of_launching_immediately(
        self, mock_launch_entry, mock_timer
    ):
        entry = _entry(delay_seconds=7)
        launcher.launch_entries([entry], log=self.log)

        mock_launch_entry.assert_not_called()
        args, kwargs = mock_timer.call_args
        self.assertEqual(args[0], 7)
        self.assertIs(args[1], launcher.launch_entry)
        self.assertEqual(kwargs["kwargs"], {"entry": entry, "log": self.log, "geometry_restore": None})
        mock_timer.return_value.start.assert_called_once()
        self.assertTrue(mock_timer.return_value.daemon)


class TestApplyWindowState(unittest.TestCase):
    def setUp(self):
        self.log = MagicMock()

    @patch("services.launcher.subprocess.run")
    def test_normal_mode_does_nothing(self, mock_run):
        launcher._apply_window_state(_entry(window_mode="normal"), self.log)
        mock_run.assert_not_called()

    @patch("services.launcher.subprocess.run")
    def test_no_match_string_does_nothing(self, mock_run):
        launcher._apply_window_state(_entry(window_mode="maximized", match_string=""), self.log)
        mock_run.assert_not_called()

    @patch("services.launcher.subprocess.run")
    def test_wmctrl_unavailable_logs_and_returns(self, mock_run):
        mock_run.side_effect = OSError("wmctrl: not found")
        launcher._apply_window_state(_entry(window_mode="maximized"), self.log)
        self.assertTrue(any("wmctrl not available" in call.args[0] for call in self.log.call_args_list))

    @patch("services.launcher.subprocess.run")
    def test_matching_window_gets_wmctrl_state_applied(self, mock_run):
        list_result = MagicMock(stdout="0x1 0 firefox.Firefox  Mozilla Firefox\n")
        mock_run.side_effect = [list_result, MagicMock()]

        launcher._apply_window_state(_entry(window_mode="maximized", match_mode="class"), self.log)

        apply_call = mock_run.call_args_list[1]
        self.assertEqual(
            apply_call.args[0], ["wmctrl", "-x", "-r", "Firefox", "-b", "add,maximized_vert,maximized_horz"]
        )
        self.assertTrue(any("applied 'maximized' mode" in call.args[0] for call in self.log.call_args_list))

    @patch("services.launcher.time.sleep")
    @patch("services.launcher.subprocess.run")
    def test_window_never_found_times_out_and_logs(self, mock_run, mock_sleep):
        mock_run.return_value = MagicMock(stdout="no matching window here\n")
        with patch.object(launcher, "WAIT_TIMEOUT_SECONDS", 0):
            launcher._apply_window_state(_entry(window_mode="maximized"), self.log)
        self.assertTrue(any("timed out" in call.args[0] for call in self.log.call_args_list))


if __name__ == "__main__":
    unittest.main()
