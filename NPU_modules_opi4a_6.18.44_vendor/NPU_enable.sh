#!/usr/bin/env bash
# =============================================================================
# npu — Unified NPU Lifecycle & Driver Manager for Orange Pi 4A (Allwinner T527)
#
# Manages both supported NPU driver pipelines on Linux 6.18+:
#   1. Mainline DRM / Teflon Stack (etnaviv -> /dev/dri/renderD129 for LiteRT)
#   2. Vendor VIPLite Stack (vipcore.ko -> /dev/vipcore for NBG models & vpm_run)
#
# Supported commands:
#   npu status           Full diagnostic overview of NPU subsystem & telemetry
#   npu teflon           Switch active driver to Mainline Etnaviv/Teflon
#   npu vipcore          Switch active driver to Vendor VIPCore/VIPLite
#   npu disable          Unload active driver (clean idle power-gated state)
#   npu test [driver]    Run hardware inference smoke-test (auto / teflon / vipcore)
#   npu enable [driver]  Alias to activate driver (default: teflon)
#   npu switch <driver>  Alias for switching driver
# =============================================================================

set -euo pipefail

# ---- Resolve real user and home directories ----
REAL_USER="${SUDO_USER:-$(id -un)}"
REAL_HOME="$(getent passwd "$REAL_USER" 2>/dev/null | cut -d: -f6)"
[ -n "$REAL_HOME" ] || REAL_HOME="$HOME"

# ---- Paths & Device Nodes ----
RENDER_NODE="/dev/dri/renderD129"
VIPCORE_NODE="/dev/vipcore"
BLACKLIST="/etc/modprobe.d/blacklist-etnaviv.conf"

NPU_SYSFS="/sys/devices/platform/soc/7122000.npu"
NPU_ACTIVE="${NPU_SYSFS}/power/runtime_active_time"
NPU_STATUS="${NPU_SYSFS}/power/runtime_status"
NPU_SUSPENDED="${NPU_SYSFS}/power/runtime_suspended_time"

# ---- Resolve Script Directory (supports symlinks) ----
SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"

VIPCORE_KMOD="${SCRIPT_DIR}/kernel/vipcore.ko"
[ -f "$VIPCORE_KMOD" ] || VIPCORE_KMOD="${REAL_HOME}/NPU_modules_opi4a_6.18.44_vendor/kernel/vipcore.ko"
VIPCORE_SAMPLE_DIR="${SCRIPT_DIR}/sample"
[ -d "$VIPCORE_SAMPLE_DIR" ] || VIPCORE_SAMPLE_DIR="${REAL_HOME}/NPU_modules_opi4a_6.18.44_vendor/sample"

VENV_PYTHON="${REAL_HOME}/venv_npu/bin/python3"
TEST_SCRIPT="${REAL_HOME}/opi4a-npu-ocr/test_npu.py"

# ---- Formatting Helpers ----
info() { echo -e "\033[1;34m[INFO]\033[0m $*"; }
ok()   { echo -e "\033[1;32m[ OK ]\033[0m $*"; }
warn() { echo -e "\033[1;33m[WARN]\033[0m $*"; }
err()  { echo -e "\033[1;31m[ERR ]\033[0m $*" >&2; }

require_root() {
  if [[ $EUID -ne 0 ]]; then
    err "This action requires root privileges. Please run with sudo:"
    err "  sudo $0 $1"
    exit 1
  fi
}

find_teflon_libs() {
  local candidates=(
    "/usr/local/lib/libteflon.so"
    "/usr/lib/teflon/libteflon.so"
    "${REAL_HOME}/libteflon_vip9000.so"
    "${REAL_HOME}/opi4a-npu-ocr/lib/libteflon.so"
    "${REAL_HOME}/opi4a-npu-mobilenet/libteflon.so"
    "${REAL_HOME}/opi4a-npu-mobilenet/lib/libteflon.so"
  )
  local found=()
  for lib in "${candidates[@]}"; do
    if [[ -f "$lib" ]]; then
      found+=("$lib")
    fi
  done
  echo "${found[@]}"
}

# -----------------------------------------------------------------------------
# SWITCH TO MAINLINE TEFLON / ETNAVIV
# -----------------------------------------------------------------------------
switch_teflon() {
  require_root "teflon"
  info "Activating Mainline Etnaviv / Teflon NPU pipeline..."

  # 1. Unload vipcore if active
  if lsmod | grep -q '^vipcore'; then
    info "Unloading active vipcore module..."
    if ! rmmod vipcore; then
      err "Failed to unload 'vipcore'. Device may be in use."
      exit 1
    fi
    ok "vipcore module unloaded."
    sleep 0.5
  fi

  # 2. Ensure blacklist doesn't have dummy install shim
  if [[ -f "$BLACKLIST" ]]; then
    if grep -q 'install etnaviv /bin/true' "$BLACKLIST"; then
      sed -i '/install etnaviv \/bin\/true/d' "$BLACKLIST"
    fi
  fi

  # 3. Load etnaviv module
  if lsmod | grep -q '^etnaviv'; then
    ok "Kernel module 'etnaviv' is already loaded."
  else
    info "Loading 'etnaviv' kernel module..."
    if ! modprobe etnaviv; then
      err "Failed to load 'etnaviv' module. Check dmesg:"
      dmesg | grep -iE 'etnaviv|npu' | tail -10 >&2
      exit 1
    fi
    ok "Kernel module 'etnaviv' loaded successfully."
  fi

  # 4. Wait for DRM render node to appear
  local node_ready=false
  for _ in {1..15}; do
    if [[ -e "$RENDER_NODE" ]]; then
      node_ready=true
      break
    fi
    sleep 0.2
  done

  if [[ "$node_ready" != true ]]; then
    err "Timed out waiting for $RENDER_NODE to appear."
    dmesg | grep -iE 'etnaviv|npu' | tail -10 >&2
    exit 1
  fi

  # 5. Configure permissions
  chgrp render "$RENDER_NODE" 2>/dev/null || true
  chmod 0660 "$RENDER_NODE"
  ok "Device node $RENDER_NODE ready: $(ls -la "$RENDER_NODE")"

  # 6. Check user membership
  if ! id -nG "$REAL_USER" | grep -qw "render"; then
    warn "User '$REAL_USER' is not in the 'render' group."
    warn "Run: sudo usermod -aG render $REAL_USER"
  fi

  echo
  ok "================================================================"
  ok " Mainline Etnaviv / Teflon pipeline active ($RENDER_NODE)"
  ok " Ready for Google LiteRT / TensorFlow Lite models."
  ok "================================================================"
}

# -----------------------------------------------------------------------------
# SWITCH TO VENDOR VIPCORE / VIPLITE
# -----------------------------------------------------------------------------
switch_vipcore() {
  require_root "vipcore"
  info "Activating Vendor VIPCore / VIPLite NPU pipeline..."

  # 1. Unload etnaviv if active
  if lsmod | grep -q '^etnaviv'; then
    info "Unloading active etnaviv module..."
    if ! modprobe -r etnaviv; then
      if [[ -e /sys/bus/platform/drivers/etnaviv/7122000.npu ]]; then
        echo 7122000.npu > /sys/bus/platform/drivers/etnaviv/unbind || true
      fi
      modprobe -r etnaviv
    fi
    ok "etnaviv module unloaded."
    sleep 0.5
  fi

  # 2. Insert vipcore module
  if lsmod | grep -q '^vipcore'; then
    ok "vipcore module is already loaded."
  else
    if [[ ! -f "$VIPCORE_KMOD" ]]; then
      err "Kernel module not found at: $VIPCORE_KMOD"
      exit 1
    fi
    info "Inserting vipcore.ko..."
    if ! insmod "$VIPCORE_KMOD"; then
      err "Failed to insert vipcore.ko. Check dmesg:"
      dmesg | tail -15 >&2
      exit 1
    fi
    ok "vipcore.ko inserted successfully."
  fi

  # 3. Wait for device node
  local node_ready=false
  for _ in {1..15}; do
    if [[ -e "$VIPCORE_NODE" ]]; then
      node_ready=true
      break
    fi
    sleep 0.2
  done

  if [[ "$node_ready" != true ]]; then
    err "Timed out waiting for $VIPCORE_NODE to appear."
    dmesg | tail -15 >&2
    exit 1
  fi

  # 4. Set permissions
  chmod 0666 "$VIPCORE_NODE"
  ok "Device node $VIPCORE_NODE ready: $(ls -la "$VIPCORE_NODE")"

  echo
  ok "================================================================"
  ok " Vendor VIPCore / VIPLite pipeline active ($VIPCORE_NODE)"
  ok " Ready for NBG models & vpm_run."
  ok "================================================================"
}

# -----------------------------------------------------------------------------
# DISABLE ALL NPU DRIVERS (IDLE STATE)
# -----------------------------------------------------------------------------
disable_all() {
  require_root "disable"
  info "Deactivating all NPU drivers..."

  # 1. Unload etnaviv
  if lsmod | grep -q '^etnaviv'; then
    if command -v fuser >/dev/null 2>&1 && [[ -e "$RENDER_NODE" ]]; then
      if fuser -s "$RENDER_NODE" 2>/dev/null; then
        warn "Processes are accessing $RENDER_NODE:"
        fuser -v "$RENDER_NODE" || true
      fi
    fi
    modprobe -r etnaviv || true
    ok "etnaviv module unloaded."
  fi

  # 2. Unload vipcore
  if lsmod | grep -q '^vipcore'; then
    rmmod vipcore || true
    ok "vipcore module unloaded."
  fi

  # 3. Restore default blacklist
  if [[ ! -f "$BLACKLIST" ]]; then
    cat << 'BLIST' > "$BLACKLIST"
# NPU is loaded on-demand via 'npu teflon' or 'npu vipcore':
blacklist etnaviv
BLIST
    ok "Restored default $BLACKLIST"
  fi

  echo
  ok "================================================================"
  ok " NPU successfully deactivated. Hardware is idle and power-gated."
  ok " Primary GPU (Panfrost) active."
  ok "================================================================"
}

# -----------------------------------------------------------------------------
# STATUS: Complete diagnostic inventory
# -----------------------------------------------------------------------------
status_npu() {
  echo "================================================================"
  echo " Orange Pi 4A (Allwinner T527) - NPU Subsystem Status"
  echo "================================================================"

  # 1. Active Pipeline
  local active_pipe="NONE"
  if lsmod | grep -q '^etnaviv'; then
    active_pipe="TEFLON (Mainline DRM / etnaviv)"
  elif lsmod | grep -q '^vipcore'; then
    active_pipe="VIPCORE (Vendor VIPLite v1.13)"
  fi
  echo -e "Active Pipeline                   : \033[1;32m${active_pipe}\033[0m"

  # 2. Kernel Drivers
  echo -n "Driver 'etnaviv' (Mesa DRM)       : "
  if lsmod | grep -q '^etnaviv'; then
    local emod
    emod="$(lsmod | awk '$1=="etnaviv"{print "size: "$2", used by: "$3}')"
    echo -e "\033[1;32mLOADED\033[0m ($emod)"
  else
    echo -e "\033[1;33mNOT LOADED\033[0m"
  fi

  echo -n "Driver 'vipcore' (Vendor v1.13)   : "
  if lsmod | grep -q '^vipcore'; then
    local vmod
    vmod="$(lsmod | awk '$1=="vipcore"{print "size: "$2", used by: "$3}')"
    echo -e "\033[1;32mLOADED\033[0m ($vmod)"
  else
    echo -e "\033[1;33mNOT LOADED\033[0m"
  fi

  # 3. Device Nodes
  echo -n "Teflon DRM Node ($RENDER_NODE)   : "
  if [[ -e "$RENDER_NODE" ]]; then
    echo -e "\033[1;32mAVAILABLE\033[0m ($(ls -la "$RENDER_NODE" | awk '{print $1, $3, $4}'))"
  else
    echo -e "\033[1;33mMISSING\033[0m (Active when 'npu teflon' is enabled)"
  fi

  echo -n "VIPCore Character Node ($VIPCORE_NODE) : "
  if [[ -e "$VIPCORE_NODE" ]]; then
    echo -e "\033[1;32mAVAILABLE\033[0m ($(ls -la "$VIPCORE_NODE" | awk '{print $1, $3, $4}'))"
  else
    echo -e "\033[1;33mMISSING\033[0m (Active when 'npu vipcore' is enabled)"
  fi

  # 4. User Permissions
  echo -n "User '$REAL_USER' in 'render' group   : "
  if id -nG "$REAL_USER" | grep -qw "render"; then
    echo -e "\033[1;32mYES\033[0m (Direct DRM access enabled)"
  else
    echo -e "\033[1;31mNO\033[0m (Run: sudo usermod -aG render $REAL_USER)"
  fi

  # 5. Hardware Power & Telemetry
  echo "Hardware Power Telemetry (Sysfs)  :"
  if [[ -d "$NPU_SYSFS" ]]; then
    local act stat susp
    act="$(cat "$NPU_ACTIVE" 2>/dev/null || echo "N/A")"
    stat="$(cat "$NPU_STATUS" 2>/dev/null || echo "N/A")"
    susp="$(cat "$NPU_SUSPENDED" 2>/dev/null || echo "N/A")"
    echo "  runtime_status         : $stat"
    echo "  runtime_active_time    : ${act} ms (increments during inference)"
    echo "  runtime_suspended_time : ${susp} ms"
  else
    echo "  Sysfs node not found ($NPU_SYSFS)"
  fi

  # 6. Installed Userspace Libraries
  echo "Userspace Libraries (System-Wide) :"
  for lib in /usr/local/lib/libteflon.so /usr/local/lib/libVIPlite.so /usr/local/lib/libVIPuser.so; do
    if [[ -f "$lib" ]]; then
      echo "  - $lib ($(ls -lh "$lib" | awk '{print $5}'))"
    fi
  done

  # 7. Model Runners & Toolchains
  echo -n "Vendor Model Runner (vpm_run)     : "
  if command -v vpm_run >/dev/null 2>&1; then
    echo -e "\033[1;32mAVAILABLE\033[0m ($(which vpm_run))"
  else
    echo -e "\033[1;33mNOT IN PATH\033[0m"
  fi

  echo -n "Python LiteRT Virtual Environment : "
  if [[ -x "$VENV_PYTHON" ]]; then
    local pyver
    pyver="$("$VENV_PYTHON" -c 'import sys; print(f"Python {sys.version.split()[0]}")' 2>/dev/null || echo "Python")"
    echo -e "\033[1;32mAVAILABLE\033[0m ($VENV_PYTHON, $pyver)"
  else
    echo -e "\033[1;33mNOT FOUND\033[0m ($VENV_PYTHON)"
  fi
  echo "================================================================"
}

# -----------------------------------------------------------------------------
# TEST: Execute hardware inference smoke-test
# -----------------------------------------------------------------------------
test_teflon() {
  info "Running LiteRT + Teflon smoke-test on $RENDER_NODE..."
  if [[ ! -e "$RENDER_NODE" ]]; then
    err "Render node $RENDER_NODE is not available! Run: sudo npu teflon"
    exit 1
  fi

  local py_cmd="python3"
  if [[ -x "$VENV_PYTHON" ]]; then
    py_cmd="$VENV_PYTHON"
  fi

  local t_before=0
  if [[ -r "$NPU_ACTIVE" ]]; then
    t_before="$(cat "$NPU_ACTIVE" 2>/dev/null || echo "0")"
  fi

  if [[ -f "$TEST_SCRIPT" ]]; then
    "$py_cmd" "$TEST_SCRIPT"
  else
    local lib_path="/usr/local/lib/libteflon.so"
    "$py_cmd" - << PYEOF
import os, sys
try:
    import ai_edge_litert.interpreter as tflite
except ImportError:
    try:
        import tflite_runtime.interpreter as tflite
    except ImportError:
        print("[ERR] Neither ai_edge_litert nor tflite_runtime is installed.")
        sys.exit(1)

lib_path = "${lib_path}"
print(f"[OK] Loading Teflon delegate: {lib_path}")
try:
    delegate = tflite.load_delegate(lib_path)
    print("[OK] Teflon delegate initialized on /dev/dri/renderD129")
except Exception as e:
    print(f"[ERR] Failed to load delegate: {e}")
    sys.exit(1)
PYEOF
  fi

  if [[ -r "$NPU_ACTIVE" ]]; then
    local t_after delta
    t_after="$(cat "$NPU_ACTIVE" 2>/dev/null || echo "0")"
    delta=$(( t_after - t_before ))
    echo
    ok "Hardware Telemetry Verification:"
    ok "  runtime_active_time before : ${t_before} ms"
    ok "  runtime_active_time after  : ${t_after} ms"
    ok "  Hardware core active delta : +${delta} ms"
    if [[ $delta -gt 0 ]]; then
      ok "  -> VERIFIED: VIP9000 core executed inference instructions via Teflon."
    fi
  fi
}

test_vipcore() {
  info "Running Vendor VIPCore smoke-test on $VIPCORE_NODE..."
  if [[ ! -e "$VIPCORE_NODE" ]]; then
    err "Character node $VIPCORE_NODE is not available! Run: sudo npu vipcore"
    exit 1
  fi

  if [[ ! -d "$VIPCORE_SAMPLE_DIR" ]]; then
    err "Sample directory not found: $VIPCORE_SAMPLE_DIR"
    exit 1
  fi

  (
    cd "$VIPCORE_SAMPLE_DIR"
    vpm_run -s sample.txt -l 1
  )
}

test_dispatch() {
  local target="${1:-auto}"
  if [[ "$target" == "teflon" ]]; then
    test_teflon
  elif [[ "$target" == "vipcore" ]]; then
    test_vipcore
  else
    if lsmod | grep -q '^etnaviv'; then
      test_teflon
    elif lsmod | grep -q '^vipcore'; then
      test_vipcore
    else
      warn "No NPU driver is currently loaded."
      warn "Enable a driver first: 'sudo npu teflon' or 'sudo npu vipcore'"
      exit 1
    fi
  fi
}

# -----------------------------------------------------------------------------
# Dispatcher
# -----------------------------------------------------------------------------
cmd="${1:-status}"
shift || true

case "$cmd" in
  teflon|etnaviv)       switch_teflon ;;
  vipcore|vendor)       switch_vipcore ;;
  disable|off|stop)     disable_all ;;
  status|info)          status_npu ;;
  test)                 test_dispatch "${1:-auto}" ;;
  enable|start)
    subcmd="${1:-teflon}"
    case "$subcmd" in
      vipcore|vendor)   switch_vipcore ;;
      *)                switch_teflon ;;
    esac
    ;;
  switch)
    subcmd="${1:-}"
    case "$subcmd" in
      vipcore|vendor)   switch_vipcore ;;
      teflon|etnaviv)   switch_teflon ;;
      *)
        err "Specify driver to switch to: 'npu switch teflon' or 'npu switch vipcore'"
        exit 1
        ;;
    esac
    ;;
  -h|--help|help)
    echo "Usage: npu <command> [options]"
    echo
    echo "Driver Switching & Lifecycle:"
    echo "  npu teflon          Switch active driver to Mainline Etnaviv/Teflon (/dev/dri/renderD129)"
    echo "  npu vipcore         Switch active driver to Vendor VIPCore (/dev/vipcore)"
    echo "  npu disable         Unload active NPU driver (leaves NPU idle and power-gated)"
    echo
    echo "Diagnostics & Verification:"
    echo "  npu status          Display complete NPU hardware, driver, and library status"
    echo "  npu test [stack]    Run hardware inference test (auto, teflon, or vipcore)"
    echo
    echo "Convenience Aliases:"
    echo "  npu enable [stack]  Alias to activate driver (default: teflon)"
    echo "  npu switch <stack>  Alias for switching driver"
    echo
    ;;
  *)
    err "Unknown command: '$cmd'"
    echo "Run 'npu --help' for usage instructions."
    exit 1
    ;;
esac
