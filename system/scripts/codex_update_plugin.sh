#!/usr/bin/env bash
set -euo pipefail

# codex_update_plugin.sh [--strict]
# codex_update_plugin.sh --refresh-shared
#
# Without --refresh-shared: run after mngr writes the per-agent config, before the
# first Codex process. Never install into an inherited CODEX_HOME: that may be the
# account's shared authentication home, or the parent agent's home. mngr only sets
# CODEX_HOME on the launched Codex process, not on extra provisioning commands.
#
# A new chat waits for this script, so it does not fetch anything when it can
# avoid it. The workspace keeps one installed copy of code-guardian under
# data/.state/codex-plugins/, and a new agent gets a copy of that. Only the first
# agent on a workspace, which has no shared copy yet, installs from GitHub itself,
# and its install becomes the shared copy. Each agent also leaves its config.toml
# there, which declares the marketplace a refresh installs from.
#
# --refresh-shared installs the latest code-guardian from GitHub into a fresh home
# and makes it the shared copy, so an update reaches the next new agent. The hourly
# refresh_agent_tools.sh runs it; it does nothing until a Codex agent has been
# created here.
#
# Like the Claude installer, outages warn without preventing agent creation;
# --strict is available for verification. No cache is deleted.
MARKETPLACE="imbue-code-guardian"
PLUGIN="imbue-code-guardian@imbue-code-guardian"

script_path="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"
repo_root="$(cd "$(dirname "$script_path")/../.." && pwd)"
shared_root="${CODEX_PLUGIN_SHARED_COPY_DIR:-$repo_root/data/.state/codex-plugins}"
# A symlink to the newest complete copy, a Codex home holding just the
# marketplace snapshot and the installed plugin.
shared_current="$shared_root/current"
shared_config="$shared_root/config.toml"

export GIT_TERMINAL_PROMPT=0
export GIT_SSH_COMMAND='ssh -o StrictHostKeyChecking=accept-new -o BatchMode=yes -o ConnectTimeout=5'

plugin_paths() {
    printf '%s\n' ".tmp/marketplaces/$MARKETPLACE" "plugins/cache/$MARKETPLACE"
}

# Copy the marketplace snapshot and the installed plugin from one Codex home to
# another, replacing whatever the destination had.
copy_install() {
    local source_home="$1"
    local destination_home="$2"
    local path
    while read -r path; do
        [[ -d "$source_home/$path" ]] || return 1
    done < <(plugin_paths)
    while read -r path; do
        rm -rf "${destination_home:?}/$path"
        mkdir -p "$(dirname "$destination_home/$path")"
        cp -a "$source_home/$path" "$destination_home/$path"
    done < <(plugin_paths)
}

# Make a copy of the install in `source_home` the shared copy, and drop every
# older copy but the one it replaces (an agent may still be copying from that).
publish_shared_copy() {
    local source_home="$1"
    local previous=""
    local copy
    mkdir -p "$shared_root"
    copy="$(mktemp -d "$shared_root/copy.XXXXXX")"
    copy_install "$source_home" "$copy" || { rm -rf "$copy"; return 1; }
    if [[ -L "$shared_current" ]]; then
        previous="$(readlink "$shared_current")"
    fi
    ln -sfn "$(basename "$copy")" "$shared_current"
    for old in "$shared_root"/copy.*; do
        [[ "$(basename "$old")" == "$(basename "$copy")" || "$(basename "$old")" == "$previous" ]] || rm -rf "$old"
    done
}

# Install from GitHub into `home`: fetch the marketplace, then add the plugin.
install_from_github() {
    local home="$1"
    # The marketplace source and plugin enablement live in mngr config_overrides,
    # so a config rewrite cannot strand the cached Git marketplace. Upgrade also
    # fetches the initial snapshot for a newly provisioned home.
    if ! CODEX_HOME="$home" codex plugin marketplace upgrade "$MARKETPLACE"; then
        echo "warning: could not refresh code-guardian; attempting the cached marketplace" >&2
    fi
    CODEX_HOME="$home" codex plugin add "$PLUGIN"
}

# Install the latest code-guardian into a fresh home, then make it the shared copy.
refresh_shared_copy() {
    local home
    if ! command -v codex &>/dev/null || [[ ! -f "$shared_config" ]]; then
        return 0
    fi
    exec 9>"$shared_root/refresh.lock"
    if command -v flock >/dev/null 2>&1; then
        flock -n 9 || return 0
    fi
    # Whatever an earlier refresh that was stopped left behind.
    rm -rf "$shared_root"/refresh.??????
    home="$(mktemp -d "$shared_root/refresh.XXXXXX")"
    cp "$shared_config" "$home/config.toml"
    if ! install_from_github "$home"; then
        echo "warning: could not refresh the shared code-guardian copy; new agents keep the previous one"
        rm -rf "$home"
        return 1
    fi
    if ! publish_shared_copy "$home"; then
        echo "warning: could not publish the refreshed code-guardian copy"
        rm -rf "$home"
        return 1
    fi
    rm -rf "$home"
}

# Keep this agent's config as the one a refresh installs with. It is moved into
# place whole, so a refresh never reads a half-written file.
save_shared_config() {
    local staged
    mkdir -p "$shared_root"
    staged="$(mktemp "$shared_root/config.XXXXXX")"
    cp "$CODEX_HOME/config.toml" "$staged"
    mv "$staged" "$shared_config"
}

STRICT=0
if [[ $# -eq 1 && "$1" == "--refresh-shared" ]]; then
    refresh_shared_copy
    exit $?
elif [[ $# -eq 1 && "$1" == "--strict" ]]; then
    STRICT=1
elif [[ $# -ne 0 ]]; then
    echo "usage: $0 [--strict | --refresh-shared]" >&2
    exit 2
fi

if [[ -z "${MNGR_AGENT_STATE_DIR:-}" ]]; then
    echo "error: MNGR_AGENT_STATE_DIR is required; refusing a shared-home install" >&2
    exit 1
fi
export CODEX_HOME="$MNGR_AGENT_STATE_DIR/plugin/codex/home"
if [[ ! -f "$CODEX_HOME/config.toml" ]]; then
    echo "error: Codex must be provisioned before installing its plugins" >&2
    exit 1
fi

if ! command -v codex &>/dev/null; then
    echo "warning: codex is not on PATH; code-guardian could not be installed" >&2
    exit "$STRICT"
fi

save_shared_config || echo "warning: could not keep this agent's config for refreshing code-guardian" >&2

if [[ -L "$shared_current" ]] && copy_install "$(cd "$shared_current" && pwd -P)" "$CODEX_HOME"; then
    exit 0
fi

if ! install_from_github "$CODEX_HOME"; then
    echo "warning: code-guardian installation failed; this Codex agent may lack review skills and Stop checks" >&2
    exit "$STRICT"
fi
publish_shared_copy "$CODEX_HOME" || echo "warning: could not keep a shared copy of code-guardian for new agents" >&2
