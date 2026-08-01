"""Behavior tests for the Unix-socket 'show yourself' IPC channel."""

import socket
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from services import instance_ipc

POLL_TIMEOUT_SECONDS = 2.0
POLL_INTERVAL_SECONDS = 0.02


def _wait_until(predicate):
    deadline = time.monotonic() + POLL_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(POLL_INTERVAL_SECONDS)
    return False


class TestInstanceIpc(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.socket_file = Path(self._tmpdir.name) / "control.sock"
        patcher = patch.object(instance_ipc, "SOCKET_FILE", self.socket_file)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_request_with_no_running_server_returns_false(self):
        self.assertFalse(instance_ipc.request_show_existing_instance())

    def test_request_reaches_a_running_server_and_triggers_on_show(self):
        on_show = MagicMock()
        server = instance_ipc.InstanceControlServer(on_show=on_show)
        server.start()
        self.addCleanup(server.stop)
        self._wait_bound(server)

        self.assertTrue(instance_ipc.request_show_existing_instance())
        self.assertTrue(_wait_until(lambda: on_show.called), "on_show callback was never invoked")

    def test_stop_removes_the_socket_file(self):
        server = instance_ipc.InstanceControlServer(on_show=MagicMock())
        server.start()
        self._wait_bound(server)
        server.stop()
        self.assertFalse(self.socket_file.exists())

    def test_a_stale_leftover_socket_file_does_not_block_a_new_server(self):
        self.socket_file.parent.mkdir(parents=True, exist_ok=True)
        self.socket_file.write_text("", encoding="utf-8")

        on_show = MagicMock()
        server = instance_ipc.InstanceControlServer(on_show=on_show)
        server.start()
        self.addCleanup(server.stop)
        self._wait_bound(server)

        self.assertTrue(instance_ipc.request_show_existing_instance())
        self.assertTrue(_wait_until(lambda: on_show.called))

    def test_start_is_idempotent(self):
        server = instance_ipc.InstanceControlServer(on_show=MagicMock())
        server.start()
        self.addCleanup(server.stop)
        first_thread = server._thread
        server.start()
        self.assertIs(server._thread, first_thread)

    def _wait_bound(self, _server=None):
        # Probe with a real connection attempt rather than inferring readiness
        # from socket-file existence or internal state: a stale leftover file
        # (see the test below) already satisfies file-existence, and
        # _server_socket is assigned before bind()/listen() actually run, so
        # both are set too early to prove the server can really accept yet.
        def _can_connect():
            probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                probe.settimeout(0.1)
                probe.connect(str(self.socket_file))
                return True
            except OSError:
                return False
            finally:
                probe.close()

        self.assertTrue(_wait_until(_can_connect), "server never became connectable")


if __name__ == "__main__":
    unittest.main()
