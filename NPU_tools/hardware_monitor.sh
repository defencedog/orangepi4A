#!/usr/bin/env bash
# ==============================================================================
# Orange Pi 4A (Allwinner T527) Hardware Monitor
# Real-Time CPU, GPU (Mali-G57), NPU (VIP9000), Memory & Thermal Dashboard
# ==============================================================================

REFRESH_INTERVAL=1
RUN_ONCE=false

if [ "$1" = "--once" ] || [ "$1" = "-1" ]; then
    RUN_ONCE=true
elif [ -n "$1" ] && [ "$1" -eq "$1" ] 2>/dev/null; then
    REFRESH_INTERVAL="$1"
fi

# ANSI Colors
BOLD="\033[1m"
RESET="\033[0m"
CYAN="\033[36m"
GREEN="\033[32m"
YELLOW="\033[33m"
RED="\033[31m"
BLUE="\033[34m"
MAGENTA="\033[35m"
WHITE="\033[37m"
GRAY="\033[90m"

# Render colored progress bar
draw_bar() {
    local val=$1
    local width=20
    local filled=$(( (val * width) / 100 ))
    if [ "$filled" -gt "$width" ]; then filled=$width; fi
    if [ "$filled" -lt 0 ]; then filled=0; fi
    local empty=$(( width - filled ))
    
    local color="$GREEN"
    if [ "$val" -ge 80 ]; then
        color="$RED"
    elif [ "$val" -ge 50 ]; then
        color="$YELLOW"
    fi
    
    local bar=""
    for ((i=0; i<filled; i++)); do bar="${bar}█"; done
    for ((i=0; i<empty; i++)); do bar="${bar}░"; done
    printf "${color}[%s] %3d%%${RESET}" "$bar" "$val"
}

# Format milli-Celsius to Celsius string with color
format_temp() {
    local raw=$1
    if [ -z "$raw" ] || [ "$raw" -le 0 ]; then
        printf "${GRAY}  N/A   ${RESET}"
        return
    fi
    local whole=$((raw / 1000))
    local frac=$(( (raw % 1000) / 100 ))
    
    local color="$GREEN"
    if [ "$whole" -ge 75 ]; then
        color="$RED"
    elif [ "$whole" -ge 60 ]; then
        color="$YELLOW"
    fi
    printf "${color}%2d.%d °C${RESET}" "$whole" "$frac"
}

# Initial CPU & NPU stats
read -r _ u n s id io ir sir st _ < /proc/stat
prev_active=$((u + n + s + ir + sir + st))
prev_total=$((prev_active + id + io))

read -r _ c0 c1 c2 c3 c4 c5 c6 c7 _ < <(grep -m 1 "vipcore_0" /proc/interrupts 2>/dev/null)
prev_npu_irq=$((c0 + c1 + c2 + c3 + c4 + c5 + c6 + c7))

while true; do
    sleep "$REFRESH_INTERVAL"
    
    # 1. CPU Usage Calculation
    read -r _ u n s id io ir sir st _ < /proc/stat
    curr_active=$((u + n + s + ir + sir + st))
    curr_total=$((curr_active + id + io))
    
    diff_active=$((curr_active - prev_active))
    diff_total=$((curr_total - prev_total))
    
    if [ "$diff_total" -gt 0 ]; then
        cpu_usage=$(( (diff_active * 100) / diff_total ))
    else
        cpu_usage=0
    fi
    prev_active=$curr_active
    prev_total=$curr_total

    # 2. CPU Frequencies & Temperatures
    raw_cpul_freq=$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq 2>/dev/null || echo 0)
    raw_cpub_freq=$(cat /sys/devices/system/cpu/cpu4/cpufreq/scaling_cur_freq 2>/dev/null || echo 0)
    freq_cpul=$((raw_cpul_freq / 1000))
    freq_cpub=$((raw_cpub_freq / 1000))
    
    gov_cpul=$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor 2>/dev/null || echo "ondemand")
    gov_cpub=$(cat /sys/devices/system/cpu/cpu4/cpufreq/scaling_governor 2>/dev/null || echo "ondemand")

    raw_cpul_temp=$(cat /sys/class/thermal/thermal_zone0/temp 2>/dev/null || echo 0)
    raw_cpub_temp=$(cat /sys/class/thermal/thermal_zone1/temp 2>/dev/null || echo 0)

    # 3. GPU (Mali-G57 MC1) - Dynamic Load & Frequency
    raw_gpu_freq=$(cat /sys/class/devfreq/1800000.gpu/cur_freq 2>/dev/null || echo 0)
    freq_gpu=$((raw_gpu_freq / 1000000))
    gov_gpu=$(cat /sys/class/devfreq/1800000.gpu/governor 2>/dev/null || echo "simple_ondemand")
    raw_gpu_temp=$(cat /sys/class/thermal/thermal_zone2/temp 2>/dev/null || echo 0)

    # GPU Load Calculation (150 MHz base idle -> 0%, 696 MHz max boost -> 100%)
    if [ "$freq_gpu" -le 150 ]; then
        gpu_load=0
    elif [ "$freq_gpu" -ge 696 ]; then
        gpu_load=100
    else
        gpu_load=$(( ((freq_gpu - 150) * 100) / (696 - 150) ))
    fi

    # 4. NPU (VIP9000 2.0 TOPS) - Dynamic Load & State
    npu_node="Offline"
    if [ -c /dev/vipcore ]; then
        npu_node="Active (/dev/vipcore)"
    fi
    raw_npu_freq=$(cat /sys/kernel/debug/clk/npu/clk_rate 2>/dev/null || echo 696000000)
    freq_npu=$((raw_npu_freq / 1000000))
    raw_npu_temp=$(cat /sys/class/thermal/thermal_zone3/temp 2>/dev/null || echo 0)

    # NPU Real-Time Hardware Interrupt Delta & Load %
    read -r _ c0 c1 c2 c3 c4 c5 c6 c7 _ < <(grep -m 1 "vipcore_0" /proc/interrupts 2>/dev/null)
    curr_npu_irq=$((c0 + c1 + c2 + c3 + c4 + c5 + c6 + c7))
    npu_irq_delta=$((curr_npu_irq - prev_npu_irq))
    prev_npu_irq=$curr_npu_irq

    if [ "$npu_irq_delta" -gt 0 ]; then
        npu_load=$(( (npu_irq_delta * 100) / (20 * REFRESH_INTERVAL) ))
        if [ "$npu_load" -gt 100 ]; then npu_load=100; fi
        if [ "$npu_load" -lt 10 ]; then npu_load=10; fi
        npu_state="${GREEN}Processing (Active, ${npu_irq_delta} irq/s)${RESET}"
    else
        npu_load=0
        npu_state="${GRAY}Standby (idle)${RESET}"
    fi

    # 5. Memory (RAM & DDR)
    mem_total_kb=0
    mem_avail_kb=0
    while read -r key val _; do
        case "$key" in
            MemTotal:) mem_total_kb="$val" ;;
            MemAvailable:) mem_avail_kb="$val" ;;
        esac
    done < /proc/meminfo
    
    mem_total_mb=$((mem_total_kb / 1024))
    mem_avail_mb=$((mem_avail_kb / 1024))
    mem_used_mb=$((mem_total_mb - mem_avail_mb))
    if [ "$mem_total_mb" -gt 0 ]; then
        mem_pct=$(( (mem_used_mb * 100) / mem_total_mb ))
    else
        mem_pct=0
    fi
    
    raw_ddr_freq=$(cat /sys/class/devfreq/3120000.dmcfreq/cur_freq 2>/dev/null || echo 0)
    freq_ddr=$((raw_ddr_freq / 1000000))
    raw_ddr_temp=$(cat /sys/class/thermal/thermal_zone4/temp 2>/dev/null || echo 0)

    curr_time=$(date "+%Y-%m-%d %H:%M:%S")
    uptime_str=$(uptime -p 2>/dev/null || uptime | awk -F,  {print })

    # Render Dashboard
    printf "\033[2J\033[H"
    printf "${BOLD}${CYAN}========================================================================${RESET}\n"
    printf "${BOLD}${WHITE}            ORANGE PI 4A (Allwinner T527) - HARDWARE MONITOR            ${RESET}\n"
    printf "${BOLD}${CYAN}========================================================================${RESET}\n"
    printf " Time: %s | Uptime: %s\n\n" "$curr_time" "$uptime_str"

    # CPU Section
    printf "${BOLD}${MAGENTA}[1] CPU (8× Cortex-A55, ARMv8.2-A FP16 + i8sdot)${RESET}\n"
    printf "  Overall Usage : "
    draw_bar "$cpu_usage"
    printf "\n"
    printf "  Little Cluster: Cores 0-3 @ %4d MHz [%s]  Temp: %b\n" "$freq_cpul" "$gov_cpul" "$(format_temp "$raw_cpul_temp")"
    printf "  Big Cluster   : Cores 4-7 @ %4d MHz [%s]  Temp: %b\n\n" "$freq_cpub" "$gov_cpub" "$(format_temp "$raw_cpub_temp")"

    # GPU Section
    printf "${BOLD}${GREEN}[2] GPU (ARM Mali-G57 MC1, Panfrost + Rusticl OpenCL 3.1)${RESET}\n"
    printf "  Overall Usage : "
    draw_bar "$gpu_load"
    printf "\n"
    printf "  Core Clock    : %4d MHz / 696 MHz max [%s]\n" "$freq_gpu" "$gov_gpu"
    printf "  Temperature   : %b\n\n" "$(format_temp "$raw_gpu_temp")"

    # NPU Section
    printf "${BOLD}${YELLOW}[3] NPU (VeriSilicon VIP9000 2.0 TOPS)${RESET}\n"
    printf "  Overall Usage : "
    draw_bar "$npu_load"
    printf "\n"
    printf "  Driver Node   : %s\n" "$npu_node"
    printf "  Core Clock    : %4d MHz\n" "$freq_npu"
    printf "  Power State   : %b\n" "$npu_state"
    printf "  Temperature   : %b\n\n" "$(format_temp "$raw_npu_temp")"

    # Memory Section
    printf "${BOLD}${BLUE}[4] MEMORY & SYSTEM THERMALS${RESET}\n"
    printf "  RAM Usage     : "
    draw_bar "$mem_pct"
    printf " (%d MB / %d MB, %d MB available)\n" "$mem_used_mb" "$mem_total_mb" "$mem_avail_mb"
    if [ "$freq_ddr" -gt 0 ]; then
        printf "  DDR Clock     : %4d MHz\n" "$freq_ddr"
    fi
    printf "  DDR Temp      : %b\n" "$(format_temp "$raw_ddr_temp")"

    printf "\n${GRAY}Press [Ctrl+C] to exit monitor (Usage: ./hardware_monitor.sh [interval_sec] or --once)${RESET}\n"

    if [ "$RUN_ONCE" = true ]; then
        break
    fi
done
