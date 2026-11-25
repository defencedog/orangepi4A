#!/usr/bin/env bash
# Remove the Falkon -> Clapper handoff and restore the latest installer backups.
#
#   ./uninstall.sh                     # Falkon must be closed
#   ./uninstall.sh --restart-falkon    # close/restart Falkon around the removal

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="${HOME}/.local/bin"
APPS_DIR="${HOME}/.local/share/applications"
PROFILE="${FALKON_PROFILE:-${HOME}/.config/falkon/profiles/default}"
RESTART=0

usage() {
    sed -n '2,8p' "$0" | sed 's/^# \{0,1\}//'
    exit "${1:-0}"
}

while [ $# -gt 0 ]; do
    case "$1" in
        --restart-falkon) RESTART=1; shift ;;
        --profile)
            [ $# -ge 2 ] || { echo "--profile needs a directory" >&2; exit 2; }
            PROFILE="$2"; shift 2 ;;
        -h|--help) usage 0 ;;
        *) echo "Unknown option: $1" >&2; usage 2 ;;
    esac
done

SETTINGS="${PROFILE}/settings.ini"
EXTENSIONS="${PROFILE}/extensions/extensions.ini"
GM_SCRIPT="${PROFILE}/extensions/greasemonkey/youtube-clapper.user.js"
MIMEAPPS="${XDG_CONFIG_HOME:-${HOME}/.config}/mimeapps.list"

say()  { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[!]\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31m[x]\033[0m %s\n' "$*" >&2; exit 1; }

falkon_running() { pgrep -x falkon >/dev/null 2>&1; }

stop_falkon() {
    if ! falkon_running; then
        return 0
    fi
    say "Waiting for Falkon's session autosave..."
    sleep 12
    pkill -TERM -x falkon 2>/dev/null || true
    for _ in $(seq 1 15); do
        falkon_running || return 0
        sleep 1
    done
    warn "Falkon did not exit after SIGTERM; sending SIGKILL."
    pkill -KILL -x falkon 2>/dev/null || true
    sleep 1
    falkon_running && die "Could not stop Falkon"
}

start_falkon() {
    local log="${HOME}/.cache/falkon-clapper-launch.log"
    say "Starting Falkon (log: $log)"
    : >"$log"
    nohup falkon >"$log" 2>&1 &
    disown || true
    sleep 4
    falkon_running && say "Falkon is running." || warn "Falkon did not start; check $log"
}

if falkon_running && [ "$RESTART" -ne 1 ]; then
    die "Falkon is running. Close it first, or rerun with --restart-falkon."
fi

[ "$RESTART" -eq 1 ] && stop_falkon

say "Removing handler and desktop entry"
rm -f "$BIN_DIR/clapper-yt-handler"
rm -f "$APPS_DIR/clapper-yt-handler.desktop"

say "Removing userscript"
rm -f "$GM_SCRIPT"

say "Removing handler cache"
rm -rf "${HOME}/.cache/falkon-clapper"

STATE_DIR="${HOME}/.local/state/falkon-clapper"
STATE_FILE="${STATE_DIR}/state.env"

restore_value() {
    local path="$1" section="$2" key="$3" value="$4"
    if [ -z "$value" ]; then
        python3 "$ROOT/falkon_ini.py" delete "$path" "$section" "$key"
    else
        python3 "$ROOT/falkon_ini.py" set "$path" "$section" "$key" "$value"
    fi
}

if [ -f "$STATE_FILE" ]; then
    say "Restoring original Falkon values from $STATE_FILE"
    # shellcheck disable=SC1090
    . "$STATE_FILE"
    if [ -f "$SETTINGS" ]; then
        restore_value "$SETTINGS" "Plugin-Settings" "AllowedPlugins" "${ALLOWED_PLUGINS_ORIG:-}"
        restore_value "$SETTINGS" "Web-Browser-Settings" "AutomaticallyOpenProtocols" "${AUTO_OPEN_ORIG:-}"
    fi
    if [ -f "$EXTENSIONS" ]; then
        restore_value "$EXTENSIONS" "GreaseMonkey" "enabled" "${GM_ENABLED_ORIG:-}"
    fi
else
    say "No original-state file; restoring latest full backups"
    restore_latest() {
        local target="$1"
        local latest
        latest="$(ls -1t "${target}".bak-*-pre-clapper 2>/dev/null | head -1 || true)"
        if [ -n "$latest" ]; then
            cp -a "$latest" "$target"
            say "restored $target from $latest"
        else
            warn "no backup found for $target"
        fi
    }
    [ -f "$SETTINGS" ] && restore_latest "$SETTINGS"
    [ -f "$EXTENSIONS" ] && restore_latest "$EXTENSIONS"
fi

# Restore the protocol association backup if there is one, otherwise remove
# only the clapper line we added.
if [ -f "$MIMEAPPS" ]; then
    latest_mime="$(ls -1t "${MIMEAPPS}".bak-*-pre-clapper 2>/dev/null | head -1 || true)"
    if [ -n "$latest_mime" ]; then
        cp -a "$latest_mime" "$MIMEAPPS"
        say "restored $MIMEAPPS from $latest_mime"
    else
        sed -i '/^x-scheme-handler\/clapper=/d' "$MIMEAPPS"
    fi
fi

rm -f "$STATE_FILE"
rmdir "$STATE_DIR" 2>/dev/null || true

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$APPS_DIR" >/dev/null 2>&1 || true
fi

if [ "$RESTART" -eq 1 ]; then
    start_falkon
fi

cat <<EOF

Removed the Falkon -> Clapper integration.
Falkon settings and the userscript are gone; the Clapper/yt-dlp/cedar stack
itself was not touched.

The x-scheme-handler/clapper association and the clapper-yt-handler.desktop
entry have been removed.
EOF
