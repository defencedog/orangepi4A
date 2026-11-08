#!/usr/bin/env bash
# Extract the Flow .deb, seed onboarding, launch it, hand off a video through
# Flow's loopback bridge, then verify that WebKit is driving the cedar VPU.
set -euo pipefail

DEB="${1:?usage: $0 /path/to/Flow_..._arm64.deb}"
ROOT="${ROOT:-/tmp/flow-deb}"
APP_ID="io.github.aedev.flow.desktop"
DATA="${XDG_DATA_HOME:-$HOME/.local/share}/$APP_ID"
DB="$DATA/flow-desktop.sqlite"
BRIDGE="http://127.0.0.1:47893"
VIDEO_ID="${VIDEO_ID:-h17LanZ4drU}"

export DISPLAY="${DISPLAY:-:0}"
export WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-wayland-0}"
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
export WEBKIT_DISABLE_SANDBOX_THIS_IS_DANGEROUS="${WEBKIT_DISABLE_SANDBOX_THIS_IS_DANGEROUS:-1}"
export GST_PLUGIN_FEATURE_RANK="${GST_PLUGIN_FEATURE_RANK:-omxh264dec:257,omxhevcvideodec:257,omxvp9videodec:257,omxavsvideodec:257,omxmpeg4videodec:257}"

stop_app() {
  pkill -f "$ROOT" 2>/dev/null || true
  for _ in $(seq 1 20); do
    curl -fsS --max-time 1 "$BRIDGE/flow/ping" >/dev/null 2>&1 || return 0
    sleep 0.5
  done
  pkill -9 -f "$ROOT" 2>/dev/null || true
  sleep 1
}

wait_bridge() {
  for _ in $(seq 1 90); do
    if curl -fsS --max-time 1 "$BRIDGE/flow/ping" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  return 1
}

cedar_holders() {
  for p in /proc/[0-9]*; do
    pid=${p#/proc/}
    if ls -l "$p/fd" 2>/dev/null | grep -q cedar_dev; then
      echo "$pid:$(cat "$p/comm" 2>/dev/null)"
    fi
  done
}

cedar_irqs() {
  awk '/cedar_dev/{for (j=2; j<=NF; j++) { if ($j ~ /^[0-9]+$/) s+=$j; else break }; print s+0}' /proc/interrupts
}

POWER=/sys/devices/platform/soc/1c0e000.video-engine/power

echo "== stopping any old Flow =="
stop_app
echo "== extracting $DEB =="
rm -rf "$ROOT"
mkdir -p "$ROOT"
dpkg-deb -x "$DEB" "$ROOT"
BIN=$(find "$ROOT" -type f -name flow -perm -111 | head -1)
[[ -n "$BIN" ]] || { echo "ERROR: flow binary not found under $ROOT"; exit 1; }
echo "binary: $BIN"

echo "== first launch (creates the profile database) =="
"$BIN" >/tmp/flow-first.log 2>&1 &
wait_bridge || { echo "ERROR: bridge did not start; see /tmp/flow-first.log"; tail -80 /tmp/flow-first.log; exit 1; }
for _ in $(seq 1 30); do
  [[ -f "$DB" ]] && break
  sleep 1
done
echo "database: $DB ($([[ -f $DB ]] && echo present || echo MISSING))"
stop_app

echo "== seeding a completed onboarding state =="
"$HOME/venv_npu/bin/python" - "$DB" <<'PY'
import json
import sqlite3
import sys

db = sys.argv[1]
con = sqlite3.connect(db)
brain = {"has_completed_onboarding": True, "schema_version": 3}
con.execute(
    "INSERT INTO settings(key, value, updated_at) VALUES(?, ?, CURRENT_TIMESTAMP) "
    "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=CURRENT_TIMESTAMP",
    ("user_neuro_brain", json.dumps(brain, separators=(",", ":"))),
)
con.commit()
row = con.execute("SELECT length(value) FROM settings WHERE key='user_neuro_brain'").fetchone()
print("user_neuro_brain bytes:", row[0] if row else None)
con.close()
PY

echo "== second launch =="
"$BIN" >/tmp/flow-run.log 2>&1 &
wait_bridge || { echo "ERROR: bridge did not start; see /tmp/flow-run.log"; tail -80 /tmp/flow-run.log; exit 1; }
echo "bridge: $(curl -fsS "$BRIDGE/flow/ping")"
sleep 3

echo "== handing off video $VIDEO_ID =="
curl -fsS "$BRIDGE/flow/watch?v=$VIDEO_ID"
echo

echo "== waiting for cedar decode =="
found=0
for i in $(seq 1 80); do
  holders=$(cedar_holders)
  status=$(cat "$POWER/runtime_status" 2>/dev/null || echo unknown)
  if [[ -n "$holders" && "$status" == "active" ]]; then
    found=1
    echo "cedar active after ~$((i / 2))s: $holders"
    break
  fi
  sleep 0.5
done

if [[ "$found" != 1 ]]; then
  echo "WARNING: no cedar holder/active state yet"
  echo "holders: $(cedar_holders)"
  echo "status: $(cat "$POWER/runtime_status" 2>/dev/null || true)"
fi

echo "== cedar telemetry (10 x 0.5 s) =="
prev_irq=$(cedar_irqs)
prev_active=$(cat "$POWER/runtime_active_time")
for i in $(seq 1 10); do
  sleep 0.5
  irq=$(cedar_irqs)
  active=$(cat "$POWER/runtime_active_time")
  echo "t=$i status=$(cat "$POWER/runtime_status") active_delta=$((active - prev_active))ms irq_delta=$((irq - prev_irq))"
  prev_irq=$irq
  prev_active=$active
done
echo "holders: $(cedar_holders)"

echo "== recent Flow log =="
LOG=$(ls -1t "$DATA"/logs/*.log 2>/dev/null | head -1 || true)
if [[ -n "$LOG" ]]; then
  echo "log: $LOG"
  tail -60 "$LOG"
fi
echo "== stderr tail =="
tail -30 /tmp/flow-run.log || true

echo "== Flow is still running for manual inspection =="
echo "PID(s): $(pgrep -f "$ROOT" | tr '\n' ' ')"
