"""Test utilities shared across the gateway's test modules."""

import json
import subprocess
import threading
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from werkzeug.serving import make_server
from werkzeug.wrappers import Request
from werkzeug.wrappers import Response


def set_cookies_by_name(response: Response) -> dict[str, str]:
    """The response's rendered ``Set-Cookie`` headers, keyed by cookie name."""
    return {header.split("=", 1)[0]: header for header in response.headers.getlist("Set-Cookie")}


@contextmanager
def serve_json(body: object) -> Generator[str, None, None]:
    """Serve ``body`` as JSON at every path of a loopback server; yields the server's URL."""

    @Request.application
    def app(request: Request) -> Response:
        return Response(json.dumps(body), mimetype="application/json")

    server = make_server("127.0.0.1", 0, app)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/share/jwks.json"
    finally:
        server.shutdown()
        thread.join()


def _git_environ(repo: Path) -> dict[str, str]:
    """A fixed committer identity and a HOME inside the repo, so no user config leaks into the test history."""
    return {
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@x",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@x",
        "HOME": str(repo),
    }


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, env=_git_environ(repo), check=True, stdout=subprocess.DEVNULL)


def make_workspace_repo(root: Path, primer_template: str, invite_template: str) -> Path:
    """A small committed workspace checkout: two skills and the two visiting-agent reference files."""
    repo = root / "workspace"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    build_app = repo / ".agents" / "skills" / "build-app"
    build_app.mkdir(parents=True)
    (build_app / "SKILL.md").write_text('---\nname: build-app\ndescription: "Build an app, in quotes"\n---\n# Build\n')
    (build_app / "scripts").mkdir()
    (build_app / "scripts" / "run.py").write_text("print('hi')\n")
    notify = repo / ".agents" / "skills" / "notify-user"
    notify.mkdir()
    (notify / "SKILL.md").write_text("---\nname: notify-user\ndescription: Tell the user.\n---\n")
    references = repo / ".agents" / "shared" / "references"
    references.mkdir(parents=True)
    (references / "visiting-agents.md").write_text(primer_template)
    (references / "visiting-agents-invite.md").write_text(invite_template)
    commit_all(repo, "Initial workspace commit")
    return repo


def commit_all(repo: Path, message: str) -> None:
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", message)
