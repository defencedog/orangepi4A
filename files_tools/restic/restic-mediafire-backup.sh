#!/usr/bin/env bash
#
# restic-mediafire-backup.sh
#
# Back up local directories to an encrypted, deduplicated restic repository
# on a MediaFire FUSE mount at /media/mediafire/backup.
#
# SECURITY NOTE:
#   Keep this file mode 700. Never commit passwords or credentials to public
#   repositories. Set RESTIC_PASSWORD via environment variable or in this file.
#
# Requirements:
#   - restic 0.18.x (installed via: sudo apt install restic) or rustic
#   - mediafire-tools 0.60+patched5 installed system-wide (/usr/bin/mediafire-fuse)
#   - MediaFire account credentials configured in ~/.config/mediafire-tools/config
#   - Repository initialized at /media/mediafire/backup (see README.md)
#
# Usage:
#   ./restic-mediafire-backup.sh                 # backup + metadata check
#   ./restic-mediafire-backup.sh --verify-data   # backup + 10% read-data check
#   ./restic-mediafire-backup.sh --prune         # backup + check + forget/prune
#   ./restic-mediafire-backup.sh --help
#
set -euo pipefail
umask 077

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
REPO="/media/mediafire/backup"
MOUNT="/media/mediafire"

# ---------------------------------------------------------------------------
# Source Directories to Backup
# Add or remove local folders as needed.
# ---------------------------------------------------------------------------
SOURCES=(
    "$HOME/Documents"
    "$HOME/projects"
    # Example paths:
    # "/home/ukhan/claude_ukhan"
    # "/home/ukhan/gemini"
)

BACKUP_HOST="${BACKUP_HOST:-orangepi-4a}"
BACKUP_TAG="${BACKUP_TAG:-mediafire}"
STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/restic-mediafire"
LOG="$STATE_DIR/backup-$(date +%Y%m%d-%H%M%S).log"
LOCK_FILE="$STATE_DIR/backup.lock"
FUSE_LOG="$STATE_DIR/fuse.log"
MOUNT_WAIT_SECONDS="${MOUNT_WAIT_SECONDS:-180}"

# Backup engine: defaults to 'restic' from Ubuntu repos, or 'rustic' if preferred
RESTIC_BIN="${RESTIC_BIN:-restic}"

# Use the system-wide patched mediafire-tools binary. Override with
# MEDIAFIRE_FUSE_BIN if a different build is needed.
FUSE_BIN="${MEDIAFIRE_FUSE_BIN:-/usr/bin/mediafire-fuse}"

# ---------------------------------------------------------------------------
# Restic Repository Encryption Password
# Set via environment variable (RESTIC_PASSWORD) or define here:
# ---------------------------------------------------------------------------
export RESTIC_PASSWORD="${RESTIC_PASSWORD:-YOUR_STRONG_RESTIC_PASSWORD_HERE}"
export RESTIC_REPOSITORY="$REPO"

# Rustic environment compatibility
export RUSTIC_PASSWORD="$RESTIC_PASSWORD"
export RUSTIC_REPOSITORY="$REPO"

PRUNE=0
VERIFY_DATA=0
RETENTION=(--keep-daily 7 --keep-weekly 4 --keep-monthly 6)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
usage() {
    cat <<'EOF'
Usage: restic-mediafire-backup.sh [options]

Options:
  --prune        After a successful backup and check, remount and run
                 `restic forget --prune` with the retention policy
                 (daily 7, weekly 4, monthly 6).
  --verify-data  Run `restic check --read-data-subset=10%` instead of the
                 metadata-only `restic check`.
  -h, --help     Show this help.

The script leaves /media/mediafire mounted. Logs are written under
~/.local/state/restic-mediafire/. The FUSE log contains MediaFire session
tokens; it is mode 600 and should be deleted after troubleshooting.
EOF
}

log() {
    printf '[%s] %s\n' "$(date '+%F %T')" "$*"
}

die() {
    log "FATAL: $*"
    exit 1
}

is_mounted() {
    mountpoint -q "$MOUNT"
}

mount_healthy() {
    # statfs is not implemented by the FUSE filesystem, so do not use
    # `stat -f` or `df`. A readdir of the small root directory is enough.
    timeout 10 ls "$MOUNT" >/dev/null 2>&1
}

wait_for_mount() {
    local i
    for ((i = 1; i <= MOUNT_WAIT_SECONDS; i++)); do
        if is_mounted && mount_healthy; then
            log "mount ready after ${i}s"
            return 0
        fi
        sleep 1
    done
    return 1
}

kill_stale_daemon() {
    local pids
    pids=$(pgrep -f "^${FUSE_BIN}( -f)? ${MOUNT}" 2>/dev/null || true)
    if [ -n "$pids" ]; then
        log "stopping stale mediafire-fuse daemon(s): $pids"
        kill $pids 2>/dev/null || true
        sleep 1
        pids=$(pgrep -f "^${FUSE_BIN}( -f)? ${MOUNT}" 2>/dev/null || true)
        [ -n "$pids" ] && kill -9 $pids 2>/dev/null || true
    fi
}

unmount_mediafire() {
    if ! is_mounted; then
        return 0
    fi
    log "unmounting $MOUNT"
    fusermount3 -u "$MOUNT" 2>/dev/null || umount "$MOUNT" 2>/dev/null || true
    local i
    for ((i = 0; i < 30; i++)); do
        is_mounted || return 0
        sleep 1
    done
    log "normal unmount did not complete; trying lazy unmount"
    fusermount3 -uz "$MOUNT" 2>/dev/null || umount -l "$MOUNT" 2>/dev/null || true
    sleep 2
    ! is_mounted
}

mount_mediafire() {
    if is_mounted; then
        if mount_healthy; then
            log "$MOUNT is already mounted and responsive"
            return 0
        fi
        log "$MOUNT is mounted but unresponsive; remounting"
        unmount_mediafire || true
    fi

    if [ ! -x "$FUSE_BIN" ]; then
        FUSE_BIN="/usr/bin/mediafire-fuse"
    fi
    [ -x "$FUSE_BIN" ] || die "no mediafire-fuse binary found at $FUSE_BIN (install mediafire-tools 0.60+patched5)"

    kill_stale_daemon
    : > "$FUSE_LOG"
    log "starting $FUSE_BIN -f $MOUNT"
    nohup "$FUSE_BIN" -f "$MOUNT" >>"$FUSE_LOG" 2>&1 &
    if ! wait_for_mount; then
        log "mount log tail:"
        tail -30 "$FUSE_LOG" || true
        die "mount did not become ready in ${MOUNT_WAIT_SECONDS}s"
    fi
}

check_repo_readable() {
    if ! "$RESTIC_BIN" cat config >/dev/null 2>&1; then
        log "cannot read repository config; remounting and retrying once"
        unmount_mediafire || true
        mount_mediafire
        "$RESTIC_BIN" cat config >/dev/null
    fi
}

run_backup() {
    local rc
    set +e
    "$RESTIC_BIN" backup \
        --host "$BACKUP_HOST" \
        --tag "$BACKUP_TAG" \
        --one-file-system \
        --exclude-caches \
        --skip-if-unchanged \
        "${SOURCES[@]}"
    rc=$?
    set -e
    case "$rc" in
        0) log "backup completed successfully" ;;
        3) log "WARNING: backup completed with partial read (restic exit 3); inspect the log" ;;
        *) die "$RESTIC_BIN backup failed with exit code $rc" ;;
    esac
}

run_check() {
    if [ "$VERIFY_DATA" = 1 ]; then
        "$RESTIC_BIN" check --read-data-subset=10%
    else
        "$RESTIC_BIN" check
    fi
}

check_fuse_errors() {
    # restic can read a pack from the FUSE file cache even when the remote
    # upload failed, so restic check alone is not sufficient. Fail loudly if
    # the daemon reported upload/cache errors during this run.
    local patterns='mfconn_api_upload_simple failed|mfconn_upload_poll_for_completion failed|filecache_open_file failed|mfconn_api_file_update failed|mfconn_api_folder_update failed|mfconn_api_file_move failed|mfconn_api_folder_move failed|rename: old path .* not found'
    if [ -f "$FUSE_LOG" ] && grep -E "$patterns" "$FUSE_LOG" >/dev/null 2>&1; then
        log "FUSE upload/cache errors detected in $FUSE_LOG:"
        grep -E "$patterns" "$FUSE_LOG" | tail -20
        return 1
    fi
    return 0
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
while [ $# -gt 0 ]; do
    case "$1" in
        --prune) PRUNE=1 ;;
        --verify-data) VERIFY_DATA=1 ;;
        -h|--help) usage; exit 0 ;;
        *) echo "Unknown option: $1" >&2; usage; exit 2 ;;
    esac
    shift
done

# Password check
if [ "$RESTIC_PASSWORD" = "YOUR_STRONG_RESTIC_PASSWORD_HERE" ] || [ -z "$RESTIC_PASSWORD" ]; then
    die "RESTIC_PASSWORD is not configured! Please export RESTIC_PASSWORD='...' or edit the script."
fi

# Binary check
command -v "$RESTIC_BIN" >/dev/null 2>&1 || die "Backup command '$RESTIC_BIN' not found. Install with: sudo apt install restic"

mkdir -p "$STATE_DIR"
exec > >(tee -a "$LOG") 2>&1
trap 'rc=$?; log "ERROR: exit $rc at line $LINENO"; exit $rc' ERR

exec 9>"$LOCK_FILE"
flock -n 9 || die "another backup is already running (lock: $LOCK_FILE)"

log "=== restic-mediafire backup start ==="
log "engine: $RESTIC_BIN ($(command -v "$RESTIC_BIN"))"
log "repository: $REPO"
log "sources: ${SOURCES[*]}"
log "log file: $LOG"

for s in "${SOURCES[@]}"; do
    [ -d "$s" ] || die "source directory missing: $s"
done

mount_mediafire

[ -f "$REPO/config" ] || die "repository not initialized at $REPO (see README.md for one-time setup)"
check_repo_readable

run_backup

if ! check_fuse_errors; then
    die "FUSE upload/cache errors detected; inspect $FUSE_LOG and rerun the backup"
fi

"$RESTIC_BIN" snapshots --last --host "$BACKUP_HOST" --tag "$BACKUP_TAG" || log "WARNING: could not list snapshots"

if ! run_check; then
    log "check failed; remounting and retrying once"
    unmount_mediafire || true
    mount_mediafire
    run_check
fi

if [ "$PRUNE" = 1 ]; then
    log "prune requested; remounting for a fresh tree before forget --prune"
    unmount_mediafire || true
    mount_mediafire
    "$RESTIC_BIN" forget \
        --host "$BACKUP_HOST" \
        --tag "$BACKUP_TAG" \
        "${RETENTION[@]}" \
        --prune
fi

log "=== done; backup log: $LOG ==="
log "=== FUSE log: $FUSE_LOG (mode 600; contains session tokens; delete when done) ==="
