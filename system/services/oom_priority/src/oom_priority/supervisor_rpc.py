"""The programs supervisord runs right now, asked over its control socket.

Asked directly over XML-RPC as ``supervisorctl`` itself does: starting a
``supervisorctl`` process each time costs about 80 ms of CPU, most of a
reading's cost. Stdlib-only (see ``paths``): the resource sampler runs under a
plain ``python3``.
"""

import http.client
import logging
import socket
import xmlrpc.client
from pathlib import Path
from typing import Any, Final, cast

# supervisord's control socket (system/supervisord.conf's [unix_http_server]).
SUPERVISOR_SOCKET: Final[Path] = Path("/var/run/supervisor.sock")
_TIMEOUT_SECONDS: Final[float] = 2.0
_logger = logging.getLogger(__name__)


class _UnixHTTPConnection(http.client.HTTPConnection):
    def __init__(self, path: Path) -> None:
        super().__init__("localhost", timeout=_TIMEOUT_SECONDS)
        self._path = path

    def connect(self) -> None:
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(str(self._path))


class _UnixTransport(xmlrpc.client.Transport):
    def __init__(self, path: Path) -> None:
        super().__init__()
        self._path = path

    def make_connection(self, host: Any) -> http.client.HTTPConnection:
        return _UnixHTTPConnection(self._path)


def _proxy(sock: Path) -> xmlrpc.client.ServerProxy:
    return xmlrpc.client.ServerProxy("http://localhost", transport=_UnixTransport(sock))


def supervised_pids(sock: Path = SUPERVISOR_SOCKET) -> dict[str, int]:
    """supervisord program -> pid, for the programs running now; empty when supervisord cannot be asked."""
    proxy = _proxy(sock)
    try:
        infos = proxy.supervisor.getAllProcessInfo()
    except (OSError, xmlrpc.client.Error, http.client.HTTPException) as error:
        _logger.debug(
            "Could not ask supervisord at %s for its programs: %s", sock, error
        )
        return {}
    pids: dict[str, int] = {}
    for info in infos if isinstance(infos, list) else []:
        # One dict per program: name, statename, pid, and more (supervisor's getProcessInfo).
        entry = cast(dict[str, Any], info) if isinstance(info, dict) else {}
        name, pid = entry.get("name"), entry.get("pid")
        if (
            entry.get("statename") == "RUNNING"
            and isinstance(name, str)
            and isinstance(pid, int)
            and pid
        ):
            pids[name] = pid
    return pids


def stop_program(name: str, sock: Path = SUPERVISOR_SOCKET) -> bool:
    """Ask supervisord to stop ``name``, without waiting for it to exit; whether it agreed (False when
    supervisord cannot be asked, knows no such program, or the program was not running)."""
    proxy = _proxy(sock)
    try:
        return bool(proxy.supervisor.stopProcess(name, False))
    except (OSError, xmlrpc.client.Error, http.client.HTTPException) as error:
        _logger.debug(
            "Could not ask supervisord at %s to stop %s: %s", sock, name, error
        )
        return False
