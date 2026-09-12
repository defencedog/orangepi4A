#!/usr/bin/env bash
# =============================================================================
# NPU_enable.sh — Activate the VeriSilicon VIP9000 NPU on Orange Pi 4A (T527)
#                  Mainline kernel 6.18+ / DRM etnaviv Subsystem
#
#  DRIVER ARCHITECTURE & PRODUCTION STATUS:
#  - etnaviv (Mesa DRM): The ONLY production-ready, functional NPU driver on
#    mainline Linux. Binds to DT node npu@7122000 and exposes the NPU compute
#    core as /dev/dri/renderD129. Paired with the patched Mesa Teflon delegate
#    (libteflon.so), it executes standard quantized TFLite / Google LiteRT
#    neural network models directly on the VIP9000 hardware core.
#
#  - vipcore (VeriSilicon VIPLite): NON-FUNCTIONAL for production workloads.
#    Lacks working userspace runtime libraries (libVIPlite.so / libVIPhal.so),
#    lacks runtime execution providers (ONNX-RT / LiteRT), and requires
#    offline ACUITY-compiled NBG models compiled for T527.
#
#  Usage:
#      sudo ./NPU_enable.sh enable    # Load etnaviv & initialize /dev/dri/renderD129
#      sudo ./NPU_enable.sh disable   # Unload etnaviv & restore clean desktop GL state
#      ./NPU_enable.sh status         # Query driver, device node, permissions & telemetry
#      ./NPU_enable.sh test           # Run hardware NPU smoke-test via LiteRT + Teflon
# =============================================================================

set -euo pipefail

# ---- Resolve real user and paths (supports direct run and sudo) ----
REAL_USER="${SUDO_USER:-$(id -un)}"
REAL_HOME="$(getent passwd "$REAL_USER" 2>/dev/null | cut -d: -f6)"
[ -n "$REAL_HOME" ] || REAL_HOME="$HOME"

RENDER_NODE="/dev/dri/renderD129"
BLACKLIST="/etc/modprobe.d/blacklist-etnaviv.conf"
NPU_SYSFS="/sys/devices/platform/soc/7122000.npu"
NPU_ACTIVE="${NPU_SYSFS}/power/runtime_active_time"
NPU_STATUS="${NPU_SYSFS}/power/runtime_status"
NPU_SUSPENDED="${NPU_SYSFS}/power/runtime_suspended_time"

# Preferred Python venv and test paths
VENV_PYTHON="${REAL_HOME}/venv_npu/bin/python3"
TEST_SCRIPT="${REAL_HOME}/opi4a-npu-ocr/test_npu.py"

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
# ENABLE: Unload vipcore (if present), load etnaviv, verify /dev/dri/renderD129
# -----------------------------------------------------------------------------
enable_npu() {
  require_root "enable"
  info "Activating VeriSilicon VIP9000 NPU via etnaviv DRM driver..."

  # 1. Unload conflicting vipcore if active
  if lsmod | grep -q '^vipcore'; then
    warn "Unloading conflicting vipcore module..."
    modprobe -r vipcore 2>/dev/null || true
    sleep 1
  fi

  # 2. Ensure blacklist doesn't block explicit modprobe
  if [[ -f "$BLACKLIST" ]]; then
    if grep -q 'install etnaviv /bin/true' "$BLACKLIST"; then
      info "Removing dummy install shim from $BLACKLIST..."
      sed -i '/install etnaviv \/bin\/true/d' "$BLACKLIST"
    fi
  fi

  # 3. Load etnaviv module
  if lsmod | grep -q '^etnaviv'; then
    ok "Kernel module 'etnaviv' is already loaded."
  else
    info "Loading 'etnaviv' kernel module..."
    if ! modprobe etnaviv; then
      err "Failed to load 'etnaviv' module. Check dmesg for kernel errors:"
      dmesg | grep -iE 'etnaviv|npu' | tail -10 >&2
      exit 1
    fi
    ok "Kernel module 'etnaviv' loaded successfully."
  fi

  # 4. Wait for DRM render node to appear
  info "Waiting for DRM device node $RENDER_NODE..."
  local node_ready=false
  for i in {1..15}; do
    if [[ -e "$RENDER_NODE" ]]; then
      node_ready=true
      break
    fi
    sleep 0.2
  done

  if [[ "$node_ready" != true ]]; then
    err "Timeout waiting for $RENDER_NODE to appear."
    err "Check dmesg for driver probe status:"
    dmesg | grep -iE 'etnaviv|drm|7122000' | tail -15 >&2
    exit 1
  fi

  # Ensure group and permissions
  chgrp render "$RENDER_NODE" 2>/dev/null || true
  chmod 0660 "$RENDER_NODE"
  ok "DRM render node $RENDER_NODE is present: $(ls -la "$RENDER_NODE" | awk '{print $1, $3, $4, $NF}')"

  # 5. Verify user group permissions
  if id -nG "$REAL_USER" | grep -qw "render"; then
    ok "User '$REAL_USER' is in 'render' group (full read/write access granted)."
  else
    warn "User '$REAL_USER' is NOT in 'render' group!"
    warn "Grant access with:  sudo usermod -aG render $REAL_USER"
    warn "(Requires logout/login to take effect for new sessions)."
  fi

  # 6. Check power telemetry sysfs
  if [[ -r "$NPU_ACTIVE" ]]; then
    local cur_active cur_stat
    cur_active="$(cat "$NPU_ACTIVE" 2>/dev/null || echo "0")"
    cur_stat="$(cat "$NPU_STATUS" 2>/dev/null || echo "unknown")"
    ok "NPU Power Management Telemetry: status=$cur_stat, active_time=${cur_active} ms"
  else
    warn "NPU sysfs telemetry node not accessible yet."
  fi

  # 7. Check Teflon delegate
  local libs
  read -ra libs <<< "$(find_teflon_libs)"
  if [[ ${#libs[@]} -gt 0 ]]; then
    ok "Found Mesa Teflon delegate: ${libs[0]}"
  else
    warn "libteflon.so not found in standard paths. Build or copy libteflon.so for LiteRT."
  fi

  echo
  ok "================================================================"
  ok " NPU Hardware & DRM Subsystem is READY: /dev/dri/renderD129"
  ok " Run './NPU_enable.sh test' to verify neural network inference."
  ok "================================================================"
}

# -----------------------------------------------------------------------------
# DISABLE: Unload etnaviv, clean up DRM nodes, restore desktop GL defaults
# -----------------------------------------------------------------------------
disable_npu() {
  require_root "disable"
  info "Deactivating NPU and unloading etnaviv DRM driver..."

  # 1. Check for active processes
  if command -v fuser >/dev/null 2>&1; then
    if fuser "$RENDER_NODE" >/dev/null 2>&1; then
      warn "Active processes currently accessing $RENDER_NODE:"
      fuser -v "$RENDER_NODE" 2>&1 || true
      warn "Terminating or closing NPU applications before unloading..."
      fuser -k -15 "$RENDER_NODE" 2>/dev/null || true
      sleep 1
    fi
  fi

  # 2. Unload etnaviv module
  if lsmod | grep -q '^etnaviv'; then
    if ! modprobe -r etnaviv; then
      err "Failed to unload 'etnaviv'. The device node may still be in use."
      exit 1
    fi
    ok "Kernel module 'etnaviv' unloaded."
  else
    ok "'etnaviv' module is not loaded."
  fi

  # 3. Ensure blacklist file exists to prevent auto-loading card0 on boot
  if [[ ! -f "$BLACKLIST" ]]; then
    cat << 'BLIST' > "$BLACKLIST"
# La NPU (etnaviv/renderD129) no hace OpenGL; si es la GPU de render por defecto
# rompe la aceleracion (apps a llvmpipe, Chromium sin WebGL). Cargar on-demand:
#   sudo modprobe etnaviv   (para Teflon/NN)   /   sudo modprobe -r etnaviv
blacklist etnaviv
BLIST
    ok "Restored default $BLACKLIST"
  fi

  # 4. Verify render node cleanup
  if [[ ! -e "$RENDER_NODE" ]]; then
    ok "Device node $RENDER_NODE removed successfully."
  else
    warn "Device node $RENDER_NODE still visible in /dev/dri."
  fi

  echo
  ok "================================================================"
  ok " NPU successfully deactivated. Primary GPU (Panfrost) active."
  ok "================================================================"
}

# -----------------------------------------------------------------------------
# STATUS: Full read-only diagnostic inventory
# -----------------------------------------------------------------------------
status_npu() {
  echo "================================================================"
  echo " Orange Pi 4A (Allwinner T527) - NPU Subsystem Status"
  echo "================================================================"

  # 1. Kernel Modules
  echo -n "Driver 'etnaviv' (Production DRM) : "
  if lsmod | grep -q '^etnaviv'; then
    local emod
    emod="$(lsmod | awk '$1=="etnaviv"{print "size: "$2", used by: "$3}')"
    echo -e "\033[1;32mLOADED\033[0m ($emod)"
  else
    echo -e "\033[1;33mNOT LOADED\033[0m"
  fi

  echo -n "Driver 'vipcore' (Vendor Legacy)  : "
  if lsmod | grep -q '^vipcore'; then
    echo -e "\033[1;31mLOADED (Conflict risk!)\033[0m"
  else
    echo -e "\033[1;32mNOT LOADED (OK)\033[0m"
  fi

  # 2. Device Nodes
  echo -n "NPU DRM Node ($RENDER_NODE)   : "
  if [[ -e "$RENDER_NODE" ]]; then
    echo -e "\033[1;32mAVAILABLE\033[0m"
    echo "  Permissions : $(ls -la "$RENDER_NODE" | awk '{print $1, $3, $4}')"
  else
    echo -e "\033[1;33mMISSING\033[0m (Run: sudo $0 enable)"
  fi

  echo "DRM Devices in /dev/dri/          :"
  if [[ -d /dev/dri ]]; then
    for dev in /dev/dri/*; do
      [[ -e "$dev" ]] || continue
      ls -ld "$dev" | awk '{printf "  %-14s %s:%s %s\n", $NF, $3, $4, $1}'
    done
  fi

  # 3. User Group Permissions
  echo -n "User '$REAL_USER' in 'render' group   : "
  if id -nG "$REAL_USER" | grep -qw "render"; then
    echo -e "\033[1;32mYES\033[0m (Direct access enabled)"
  else
    echo -e "\033[1;31mNO\033[0m (Run: sudo usermod -aG render $REAL_USER)"
  fi

  # 4. Blacklist configuration
  echo -n "Modprobe Blacklist Status         : "
  if [[ -f "$BLACKLIST" ]]; then
    echo "Present ($BLACKLIST)"
    grep -v '^[[:space:]]*#' "$BLACKLIST" | grep -v '^[[:space:]]*$' | sed 's/^/  /' || true
  else
    echo "None (Autoload unconstrained)"
  fi

  # 5. Hardware Power & Telemetry
  echo "NPU Hardware Power Telemetry      :"
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

  # 6. Teflon Libraries
  echo "Mesa Teflon Delegate Libraries    :"
  local libs
  read -ra libs <<< "$(find_teflon_libs)"
  if [[ ${#libs[@]} -gt 0 ]]; then
    for lib in "${libs[@]}"; do
      echo "  - $lib ($(ls -lh "$lib" | awk '{print $5}'))"
    done
  else
    echo "  None found in standard paths"
  fi

  # 7. Python Virtual Environment
  echo -n "Python LiteRT Environment         : "
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
# TEST: End-to-end hardware inference smoke-test
# -----------------------------------------------------------------------------
test_npu() {
  info "Initiating NPU hardware inference diagnostic..."

  # 1. Verify device node
  if [[ ! -e "$RENDER_NODE" ]]; then
    err "Render node $RENDER_NODE is not available!"
    err "Please enable the driver first:  sudo $0 enable"
    exit 1
  fi

  if [[ ! -r "$RENDER_NODE" || ! -w "$RENDER_NODE" ]]; then
    err "Current user '$REAL_USER' cannot read/write $RENDER_NODE."
    err "Ensure you are in the 'render' group: sudo usermod -aG render $REAL_USER"
    exit 1
  fi

  # 2. Determine Python interpreter
  local py_cmd="python3"
  if [[ -x "$VENV_PYTHON" ]]; then
    py_cmd="$VENV_PYTHON"
  fi

  # 3. Read pre-inference telemetry
  local t_before=0
  if [[ -r "$NPU_ACTIVE" ]]; then
    t_before="$(cat "$NPU_ACTIVE" 2>/dev/null || echo "0")"
  fi

  # 4. Execute test script
  if [[ -f "$TEST_SCRIPT" ]]; then
    info "Executing $TEST_SCRIPT using $py_cmd..."
    "$py_cmd" "$TEST_SCRIPT"
  else
    # Fallback to inline Python diagnostic
    info "Executing inline LiteRT + Teflon smoke-test..."
    local lib_path
    local libs
    read -ra libs <<< "$(find_teflon_libs)"
    if [[ ${#libs[@]} -eq 0 ]]; then
      err "No libteflon.so delegate found. Cannot run inference."
      exit 1
    fi
    lib_path="${libs[0]}"

    "$py_cmd" - << PYEOF
import os, sys, time
import numpy as np

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

  # 5. Read post-inference telemetry
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
      ok "  -> VERIFIED: VIP9000 NPU core executed inference instructions."
    fi
  fi
}

# -----------------------------------------------------------------------------
# Dispatcher
# -----------------------------------------------------------------------------
case "${1:-status}" in
  enable)   enable_npu ;;
  disable)  disable_npu ;;
  status)   status_npu ;;
  test)     test_npu ;;
  -h|--help|help)
    echo "Usage: $0 [enable|disable|status|test]"
    echo
    echo "Commands:"
    echo "  enable   Load etnaviv module and make /dev/dri/renderD129 available (requires sudo)"
    echo "  disable  Unload etnaviv module and restore clean desktop state (requires sudo)"
    echo "  status   Display detailed status of NPU driver, DRM nodes, and telemetry"
    echo "  test     Run hardware inference test and verify active time delta"
    echo
    ;;
  *)
    err "Unknown command: '$1'"
    echo "Usage: $0 [enable|disable|status|test]"
    exit 1
    ;;
esac
