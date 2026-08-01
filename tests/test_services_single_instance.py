"""Behavior tests for the fcntl.flock-based single-instance guard."""

import fcntl
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from services import single_instance


class TestSingleInstanceGuard(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.lock_dir = Path(self._tmpdir.name) / "runtime"
        self.lock_file = self.lock_dir / "instance.lock"
        patcher_dir = patch.object(single_instance, "LOCK_DIR", self.lock_dir)
        patcher_file = patch.object(single_instance, "LOCK_FILE", self.lock_file)
        patcher_dir.start()
        patcher_file.start()
        self.addCleanup(patcher_dir.stop)
        self.addCleanup(patcher_file.stop)

    def test_first_guard_acquires_the_lock(self):
        guard = single_instance.SingleInstanceGuard()
        self.assertTrue(guard.acquire())
        guard.release()

    def test_second_guard_cannot_acquire_while_first_holds_it(self):
        first = single_instance.SingleInstanceGuard()
        second = single_instance.SingleInstanceGuard()
        self.assertTrue(first.acquire())
        self.assertFalse(second.acquire())
        first.release()

    def test_lock_becomes_available_again_after_release(self):
        first = single_instance.SingleInstanceGuard()
        second = single_instance.SingleInstanceGuard()
        first.acquire()
        first.release()
        self.assertTrue(second.acquire())
        second.release()

    def test_lock_file_records_the_holding_pid(self):
        import os

        guard = single_instance.SingleInstanceGuard()
        guard.acquire()
        self.assertEqual(self.lock_file.read_text(encoding="utf-8"), str(os.getpid()))
        guard.release()

    def test_release_without_acquire_does_not_raise(self):
        guard = single_instance.SingleInstanceGuard()
        guard.release()

    def test_release_is_idempotent(self):
        guard = single_instance.SingleInstanceGuard()
        guard.acquire()
        guard.release()
        guard.release()


class TestEnforceSingleInstance(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.lock_dir = Path(self._tmpdir.name) / "runtime"
        self.lock_file = self.lock_dir / "instance.lock"
        patcher_dir = patch.object(single_instance, "LOCK_DIR", self.lock_dir)
        patcher_file = patch.object(single_instance, "LOCK_FILE", self.lock_file)
        patcher_dir.start()
        patcher_file.start()
        self.addCleanup(patcher_dir.stop)
        self.addCleanup(patcher_file.stop)

    def _hold_lock_externally(self):
        self.lock_dir.mkdir(parents=True, exist_ok=True)
        handle = self.lock_file.open("w", encoding="utf-8")
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        self.addCleanup(handle.close)
        return handle

    def test_first_instance_may_continue(self):
        may_continue, guard = single_instance.enforce_single_instance(quiet=True)
        self.assertTrue(may_continue)
        guard.release()

    @patch("services.single_instance.request_show_existing_instance")
    @patch("services.single_instance.show_already_running_message")
    def test_quiet_mode_skips_focusing_and_dialog(self, mock_dialog, mock_request_show):
        self._hold_lock_externally()
        may_continue, _guard = single_instance.enforce_single_instance(quiet=True)
        self.assertFalse(may_continue)
        mock_request_show.assert_not_called()
        mock_dialog.assert_not_called()

    @patch("services.single_instance.request_show_existing_instance", return_value=True)
    @patch("services.single_instance.show_already_running_message")
    def test_non_quiet_mode_focuses_existing_instance_and_shows_dialog(self, mock_dialog, mock_request_show):
        self._hold_lock_externally()
        may_continue, _guard = single_instance.enforce_single_instance(quiet=False)
        self.assertFalse(may_continue)
        mock_request_show.assert_called_once()
        mock_dialog.assert_called_once_with(focused_existing=True)


if __name__ == "__main__":
    unittest.main()
