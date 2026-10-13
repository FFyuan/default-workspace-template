#!/usr/bin/env bash
# Installs everything datalib needs to run, the first time the datalib skill
# is used: the binaries (datalib-http for the Datalib app, datalib-dag and the
# rest for the skill), one pinned release for both so the UI and the agent's
# tools never disagree about the store format, and the Node runtime a sync
# shells out to. Nothing here runs at boot, so a workspace that never uses
# datalib downloads nothing.
#
# Safe to run every time: each half checks what is already in place first.
#
# The release lands in a directory named after the pin, under the persistent
# home, and ~/.local/bin gets one symlink per binary, so a pin bump installs
# beside the old release and relinks. datalib-http finds its sibling binaries
# through the resolved executable path, which is why the binaries themselves
# stay together in that directory.
set -euo pipefail

# The skill (../SKILL.md) names the same version;
# system/apps/datalib/test_datalib_pin.py fails when the two disagree.
readonly PINNED_VERSION="v0.42.0"

readonly INSTALL_ROOT="${DATALIB_INSTALL_ROOT:-$HOME/.local/share/datalib}"
readonly BIN_DIR="${DATALIB_BIN_DIR:-$HOME/.local/bin}"
readonly RELEASE_DIR="$INSTALL_ROOT/$PINNED_VERSION"

_log() {
    printf '[install_datalib] %s\n' "$*"
}

_link_binaries() {
    local binary name
    mkdir -p "$BIN_DIR"
    for binary in "$RELEASE_DIR"/*; do
        [ -f "$binary" ] || continue
        name="$(basename "$binary")"
        ln -sfn "$binary" "$BIN_DIR/$name"
    done
}

if [ -x "$RELEASE_DIR/datalib-http" ]; then
    _log "datalib $PINNED_VERSION already installed at $RELEASE_DIR"
else
    # datalib's own installer (the fully-static musl build runs as-is on any
    # Linux). It downloads the release tarball for this architecture, verifies
    # the published sha256, and drops the binaries into DATALIB_INSTALL_DIR.
    _log "installing datalib $PINNED_VERSION into $RELEASE_DIR (about 80 MB)"
    mkdir -p "$RELEASE_DIR"
    curl -LsSf "https://raw.githubusercontent.com/imbue-ai/datalib/$PINNED_VERSION/scripts/install.sh" \
        | DATALIB_VERSION="$PINNED_VERSION" DATALIB_LIBC=musl DATALIB_INSTALL_DIR="$RELEASE_DIR" sh
    [ -x "$RELEASE_DIR/datalib-http" ] || {
        _log "the installer did not produce $RELEASE_DIR/datalib-http"
        exit 1
    }
fi
_link_binaries
_log "binaries linked into $BIN_DIR"

# The tarball carries the binaries only. The Node runtime (latchkey and qmd,
# at the versions datalib was built with) is a separate asset of the same
# release, fetched sha256-checked into ~/.cache/datalib/runtime. A sync
# fetches it too if this fails, so a miss here is reported but not fatal.
_log "fetching the Node runtime (about 115 MB, once)"
if "$RELEASE_DIR/datalib-step" pull-runtime; then
    _log "runtime in place under ~/.cache/datalib/runtime"
else
    _log "runtime fetch FAILED; the first sync will try again"
fi
