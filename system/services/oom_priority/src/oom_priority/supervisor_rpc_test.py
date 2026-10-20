"""Tests for the supervisord reader: the programs running now, over a fake control socket."""

import configparser
import socketserver
import tempfile
import threading
from pathlib import Path
from xmlrpc.server import SimpleXMLRPCDispatcher, SimpleXMLRPCRequestHandler

from oom_priority import supervisor_rpc


class _UnixRequestHandler(SimpleXMLRPCRequestHandler):
    # The stock handler sets a TCP-only socket option, which a Unix socket refuses.
    disable_nagle_algorithm = False


class _UnixXMLRPCServer(socketserver.UnixStreamServer, SimpleXMLRPCDispatcher):
    def __init__(self, path: str) -> None:
        SimpleXMLRPCDispatcher.__init__(self, allow_none=True)
        socketserver.UnixStreamServer.__init__(self, path, _UnixRequestHandler)
        self.logRequests = False


def test_running_programs_are_read_from_the_supervisor_socket() -> None:
    with tempfile.TemporaryDirectory(dir="/tmp") as short_dir:
        sock = Path(short_dir) / "s.sock"
        server = _UnixXMLRPCServer(str(sock))
        server.register_function(
            lambda: [
                {"name": "budget", "statename": "RUNNING", "pid": 40},
                {"name": "notes", "statename": "STOPPED", "pid": 0},
                {"name": "chat", "statename": "RUNNING", "pid": 25},
            ],
            "supervisor.getAllProcessInfo",
        )
        serving = threading.Thread(target=server.handle_request)
        serving.start()
        try:
            assert supervisor_rpc.supervised_pids(sock) == {"budget": 40, "chat": 25}
        finally:
            serving.join(timeout=5)
            server.server_close()
        # No supervisord to ask: no programs, and no error.
        assert supervisor_rpc.supervised_pids(Path(short_dir) / "missing.sock") == {}


def test_the_supervisor_socket_is_the_one_the_workspace_configures() -> None:
    conf = configparser.ConfigParser(interpolation=None, strict=False)
    conf.read(Path(__file__).parents[4] / "supervisord.conf")

    assert conf["unix_http_server"]["file"] == str(supervisor_rpc.SUPERVISOR_SOCKET)
