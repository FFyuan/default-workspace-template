#!/usr/bin/env python3
"""Probe, and wait for, the GitHub access the publish flows need through latchkey.

Two kinds of access, each its own latchkey scope:

  - `api`: the GitHub REST API (`github-rest-api` with `github-read-user` +
    `github-write-all`) -- repo creation, settings, topics. Probed by reading
    `/user`; the gateway answers an unpermitted request with a 403, which
    `curl -f` turns into a non-zero exit.
  - `git-write`: a push through the gateway's git proxy (`github-git` with
    `github-git-write`). Probed from the gateway's own permission rules, where an
    approved grant is keyed `github-git:<account>` (never bare `github-git`) or
    by the catch-all `any`.

This only ever reads. The permission REQUESTS stay inline in the skill: the chat
builds its approval card from a request's own command line and echoed result, so a
request run from inside a script would leave the user with no button to press.

Usage:

    python3 github_access.py check [--need api] [--need git-write]
    python3 github_access.py wait [--need ...] [--timeout-seconds 300] [--interval-seconds 10]
    python3 github_access.py owner

`--need` defaults to both. `check` and `wait` print one line per kind and exit 0
only when all are permitted; `owner` prints the signed-in account's login.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time

_API_PROBE_URL = "https://api.github.com/user"
_PERMISSIONS_URL = "http://latchkey-self.invalid/permissions/self"
_GIT_SCOPE_PATTERN = re.compile(r"^github-git(:|$)")
_KINDS = ("api", "git-write")


class GitHubAccessError(Exception):
    """Raised when latchkey cannot be asked at all."""


def _latchkey_curl(*args: str) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["latchkey", "curl", *args], capture_output=True, text=True, check=False
        )
    except OSError as e:
        raise GitHubAccessError(f"cannot run latchkey: {e}") from e


def is_api_permitted() -> bool:
    return _latchkey_curl("-sf", _API_PROBE_URL).returncode == 0


def grants_git_write(rules: object) -> bool:
    """Whether the gateway's permission rules let this agent push."""
    if not isinstance(rules, list):
        return False
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        for scope, permissions in rule.items():
            if not isinstance(scope, str) or not (
                _GIT_SCOPE_PATTERN.match(scope) or scope == "any"
            ):
                continue
            if isinstance(permissions, list) and (
                "github-git-write" in permissions or "any" in permissions
            ):
                return True
    return False


def is_git_write_permitted() -> bool:
    completed = _latchkey_curl("-s", _PERMISSIONS_URL)
    if completed.returncode != 0:
        return False
    try:
        rules = json.loads(completed.stdout).get("rules")
    except (json.JSONDecodeError, AttributeError):
        return False
    return grants_git_write(rules)


_PROBES = {"api": is_api_permitted, "git-write": is_git_write_permitted}


def access_report(kinds: list[str]) -> dict[str, bool]:
    return {kind: _PROBES[kind]() for kind in kinds}


def _format(report: dict[str, bool]) -> str:
    return "\n".join(
        f"{kind}: {'permitted' if is_permitted else 'NOT permitted'}"
        for kind, is_permitted in report.items()
    )


def signed_in_login() -> str:
    completed = _latchkey_curl("-sf", _API_PROBE_URL)
    if completed.returncode != 0:
        raise GitHubAccessError(
            "GitHub API access is not permitted; request github-rest-api first"
        )
    login = json.loads(completed.stdout).get("login")
    if not isinstance(login, str) or not login:
        raise GitHubAccessError(f"GitHub returned no login: {completed.stdout[:200]}")
    return login


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Probe, and wait for, GitHub access through latchkey."
    )
    subcommands = parser.add_subparsers(dest="command", required=True)
    for name in ("check", "wait"):
        subcommand = subcommands.add_parser(name)
        subcommand.add_argument("--need", action="append", choices=_KINDS)
    wait = subcommands.choices["wait"]
    wait.add_argument("--timeout-seconds", type=float, default=300.0)
    wait.add_argument("--interval-seconds", type=float, default=10.0)
    subcommands.add_parser("owner")
    args = parser.parse_args(argv)

    try:
        if args.command == "owner":
            print(signed_in_login())
            return 0
        kinds = args.need or list(_KINDS)
        report = access_report(kinds)
        if args.command == "wait":
            deadline = time.monotonic() + args.timeout_seconds
            while not all(report.values()) and time.monotonic() < deadline:
                time.sleep(args.interval_seconds)
                report = access_report(kinds)
    except GitHubAccessError as e:
        print(f"github_access: {e}", file=sys.stderr)
        return 1

    if all(report.values()):
        print(_format(report))
        return 0
    # A wait that ran out is a failure the caller reports; a check is just an answer.
    print(_format(report), file=sys.stderr if args.command == "wait" else sys.stdout)
    return 1


if __name__ == "__main__":
    sys.exit(main())
