"""Behavior tests for the append-only startup log (services/session_log.py)."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from services import session_log


class TestSessionLog(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.log_file = Path(self._tmpdir.name) / "state" / "session.log"
        patcher = patch.object(session_log, "SESSION_LOG_FILE", self.log_file)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_first_write_creates_the_directory_and_file(self):
        session_log.write("autostart start.")
        self.assertTrue(self.log_file.is_file())
        self.assertIn("autostart start.", self.log_file.read_text(encoding="utf-8"))

    def test_lines_are_timestamped_and_appended(self):
        session_log.write("first")
        session_log.write("second")
        lines = self.log_file.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 2)
        self.assertTrue(lines[0].endswith("first"))
        self.assertTrue(lines[1].endswith("second"))
        self.assertRegex(lines[0], r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} ")

    def test_multiline_message_stays_in_one_entry(self):
        session_log.write("failed:\nTraceback ...")
        self.assertIn("failed:\nTraceback ...", self.log_file.read_text(encoding="utf-8"))

    def test_oversized_log_is_rotated_instead_of_growing_forever(self):
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        self.log_file.write_text("x" * (session_log.MAX_BYTES + 1), encoding="utf-8")

        session_log.write("after rotation")

        self.assertTrue(self.log_file.with_suffix(".log.1").is_file())
        self.assertEqual(len(self.log_file.read_text(encoding="utf-8").splitlines()), 1)

    def test_unwritable_location_is_ignored(self):
        with patch.object(session_log, "SESSION_LOG_FILE", Path("/proc/definitely-not-writable/session.log")):
            session_log.write("must not raise")


if __name__ == "__main__":
    unittest.main()
