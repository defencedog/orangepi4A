#!/usr/bin/env bash
# Install the Falkon -> Clapper handoff.
#
#   ./install.sh                     # install, Falkon must be closed
#   ./install.sh --restart-falkon    # install, closing/restarting Falkon
#   ./install.sh --profile DIR       # use a non-default Falkon profile
#
# The installer is idempotent.  It backs up settings.ini and
# extensions/extensions.ini before changing anything.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="${HOME}/.local/bin"
APPS_DIR="${HOME}/.local/share/applications"
PROFILE="${FALKON_PROFILE:-${HOME}/.config/falkon/profiles/default}"
RESTART=0
STAMP="$(date +%Y%m%d-%H%M%S)"

usage() {
    sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'
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
GM_DIR="${PROFILE}/extensions/greasemonkey"
SESSION="${PROFILE}/session.dat"

say()  { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[!]\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31m[x]\033[0m %s\n' "$*" >&2; exit 1; }

[ -x /usr/bin/clapper ] || die "Clapper not found at /usr/bin/clapper"
[ -f "$SETTINGS" ] || die "Falkon settings not found: $SETTINGS"

falkon_running() {
    pgrep -x falkon >/dev/null 2>&1
}

stop_falkon() {
    if ! falkon_running; then
        return 0
    fi
    say "Waiting for Falkon's 10-second session autosave..."
    sleep 12
    if [ -f "$SESSION" ]; then
        cp -a "$SESSION" "${SESSION}.bak-${STAMP}-pre-clapper"
        say "Session backup: ${SESSION}.bak-${STAMP}-pre-clapper"
    fi
    say "Stopping Falkon (session restore is enabled: afterLaunch=3)..."
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
    if falkon_running; then
        if grep -q 'extensions loaded' "$log" 2>/dev/null; then
            grep 'extensions loaded' "$log" | tail -1
        fi
        say "Falkon is running."
    else
        warn "Falkon did not start; check $log"
    fi
}

if falkon_running && [ "$RESTART" -ne 1 ]; then
    die "Falkon is running. Close it first, or rerun with --restart-falkon."
fi

if [ "$RESTART" -eq 1 ]; then
    stop_falkon
fi

# ---------------------------------------------------------------------------
# 1. Handler + desktop file
# ---------------------------------------------------------------------------
say "Installing clapper:// handler"
mkdir -p "$BIN_DIR" "$APPS_DIR"
install -m 755 "$ROOT/clapper-yt-handler" "$BIN_DIR/clapper-yt-handler"
sed "s|^Exec=.*|Exec=${BIN_DIR}/clapper-yt-handler %u|" \
    "$ROOT/clapper-yt-handler.desktop" >"$APPS_DIR/clapper-yt-handler.desktop"
chmod 644 "$APPS_DIR/clapper-yt-handler.desktop"

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$APPS_DIR" >/dev/null 2>&1 || true
fi

MIMEAPPS="${XDG_CONFIG_HOME:-${HOME}/.config}/mimeapps.list"
if [ -f "$MIMEAPPS" ]; then
    cp -a "$MIMEAPPS" "${MIMEAPPS}.bak-${STAMP}-pre-clapper"
    say "mimeapps backup: ${MIMEAPPS}.bak-${STAMP}-pre-clapper"
fi
xdg-mime default clapper-yt-handler.desktop x-scheme-handler/clapper
default_handler="$(xdg-mime query default x-scheme-handler/clapper || true)"
if [ "$default_handler" != "clapper-yt-handler.desktop" ]; then
    warn "xdg-mime default is '$default_handler', expected clapper-yt-handler.desktop"
else
    say "Default handler: $default_handler"
fi

# ---------------------------------------------------------------------------
# 2. Userscript
# ---------------------------------------------------------------------------
say "Installing GreaseMonkey userscript"
mkdir -p "$GM_DIR/requires"
install -m 644 "$ROOT/youtube-clapper.user.js" "$GM_DIR/youtube-clapper.user.js"

# ---------------------------------------------------------------------------
# 3. Falkon configuration (Falkon is closed at this point)
# ---------------------------------------------------------------------------
say "Backing up Falkon configuration"
cp -a "$SETTINGS" "${SETTINGS}.bak-${STAMP}-pre-clapper"
if [ -f "$EXTENSIONS" ]; then
    cp -a "$EXTENSIONS" "${EXTENSIONS}.bak-${STAMP}-pre-clapper"
else
    mkdir -p "$(dirname "$EXTENSIONS")"
    : >"$EXTENSIONS"
    cp -a "$EXTENSIONS" "${EXTENSIONS}.bak-${STAMP}-pre-clapper"
fi
say "Backups: ${SETTINGS}.bak-${STAMP}-pre-clapper"
say "         ${EXTENSIONS}.bak-${STAMP}-pre-clapper"

# Remember the exact pre-install values so uninstall can remove only our
# additions instead of reverting unrelated later changes.  Keep the first
# recorded state if the installer is re-run without uninstalling.
STATE_DIR="${HOME}/.local/state/falkon-clapper"
STATE_FILE="${STATE_DIR}/state.env"
mkdir -p "$STATE_DIR"
if [ ! -f "$STATE_FILE" ]; then
    {
        printf 'ALLOWED_PLUGINS_ORIG=%q\n' "$(python3 "$ROOT/falkon_ini.py" get "$SETTINGS" "Plugin-Settings" "AllowedPlugins" || true)"
        printf 'AUTO_OPEN_ORIG=%q\n' "$(python3 "$ROOT/falkon_ini.py" get "$SETTINGS" "Web-Browser-Settings" "AutomaticallyOpenProtocols" || true)"
        printf 'GM_ENABLED_ORIG=%q\n' "$(python3 "$ROOT/falkon_ini.py" get "$EXTENSIONS" "GreaseMonkey" "enabled" || true)"
    } >"$STATE_FILE"
    say "Original-state file: $STATE_FILE"
fi

say "Enabling GreaseMonkey and clapper:// auto-open"
python3 "$ROOT/falkon_ini.py" add-list "$SETTINGS" "Plugin-Settings" "AllowedPlugins" "lib:GreaseMonkey.so"
python3 "$ROOT/falkon_ini.py" add-list "$SETTINGS" "Web-Browser-Settings" "AutomaticallyOpenProtocols" "clapper"
python3 "$ROOT/falkon_ini.py" set-bool "$EXTENSIONS" "GreaseMonkey" "enabled" true

# ---------------------------------------------------------------------------
# 4. Self-test
# ---------------------------------------------------------------------------
say "Handler dry-run tests"
dry_run="$("$BIN_DIR/clapper-yt-handler" --dry-run 'clapper://play?v=jNQXAC9IVRw')"
printf '%s\n' "$dry_run"
case "$dry_run" in
    *--new-window*)
        die "Handler would create a second Clapper window"
        ;;
esac
"$BIN_DIR/clapper-yt-handler" --dry-run 'clapper://watch/jNQXAC9IVRw'
if "$BIN_DIR/clapper-yt-handler" --dry-run 'clapper://play?v=not-an-id' >/dev/null 2>&1; then
    die "Handler accepted an invalid video id"
fi
say "Invalid id correctly rejected (single-window mode)"

if [ "$RESTART" -eq 1 ]; then
    start_falkon
fi

cat <<EOF

Installed:
  handler    $BIN_DIR/clapper-yt-handler
  desktop    $APPS_DIR/clapper-yt-handler.desktop
  userscript $GM_DIR/youtube-clapper.user.js
  config     $SETTINGS
             $EXTENSIONS

Test without Falkon:
  xdg-open 'clapper://play?v=jNQXAC9IVRw'

Test in Falkon:
  Open https://www.youtube.com/watch?v=jNQXAC9IVRw
  Auto mode shows a 1.5 s countdown; the floating button and Alt+P are manual.

Log:
  ~/.cache/clapper-yt-handler.log

Uninstall:
  $ROOT/uninstall.sh
EOF
