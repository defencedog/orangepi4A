# Allwinner T527 Hardware PWM8 (Pin 7 / PB4) & Fan Control Suite (Linux 6.18.44)

**Target Board:** Orange Pi 4A (Allwinner T527 / `sun55iw3` / `sun55i-t527`)  
**Hardware Block:** Allwinner `pwm0` Controller (`2000c00.pwm`, MMIO `0x02000c00`, 16 channels `0–15`)  
**Active Header Pin:** Physical **Pin 7** (`PB4`, `gpiochip1` line `36`, `PWM8` = channel `8`, `ALT5` / `allwinner,pinmux = <0x05>`)  
**Kernel Target:** Mainline Linux `6.18.44-g61025ec85b88` (`aarch64`)  
**Driver Stack:** Out-of-tree `pwm-sun55i-t527.ko` → `/sys/class/pwm/pwmchip0/pwm8`  
**Thermal Fan Daemon:** `opi4a-fan-pwm.service` (`/usr/local/bin/opi4a-fan-pwm.sh`)

---

## 1. Overview

Mainline Linux `6.18.44` on the Orange Pi 4A only includes `pwm-sun4i.ko` (legacy `sun4i`–`sun50i-h6` PWM IP) and has no `pwm@2000c00` node in the base Device Tree. Meanwhile, legacy 5.15 BSP `.dtbo` overlays are incompatible with mainline `sun55i-a523` Device Tree bindings and the custom U-Boot `boot.cmd` script.

This directory provides a complete, zero-CPU-overhead hardware PWM enablement and temperature-controlled fan suite that **preserves the G2D (`5440000.g2d`) DTB patches**:

- **Out-of-Tree Hardware PWM Driver (`kernel/pwm-sun55i-t527.ko` & `kernel/src/`):**
  - Implements the Linux `6.18.44` `pwm_chip` APIs (`devm_pwmchip_alloc`, `devm_pwmchip_add`, `pwm_ops.apply`, `pwm_ops.get_state`) for the Allwinner T527 `sunxi-pwm-v201` controller (`0x02000c00`).
  - Uses `CLK_BUS_PWM0` (`69`), `RST_BUS_PWM0` (`15`), `osc24M-clk` (24 MHz `hosc`), and optional `CLK_APB0` (`42`), exposing 16 hardware channels via `/sys/class/pwm/pwmchip0`.
- **G2D + PWM8 Device Tree (`dtb/sun55i-t527-orangepi-4a-audio.dtb` & `.dts`):**
  - Layered directly on top of the G2D-enabled Device Tree (`g2d_enable/dtb/sun55i-t527-orangepi-4a-audio.dts`).
  - Adds `pwm0-8-pins` (`PB4`, `function = "pwm0_8"`, `allwinner,pinmux = <0x05>`, `drive-strength = <0x0a>`) under `/soc/pinctrl@2000000`.
  - Adds `/soc/pwm@2000c00` (`status = "okay"`) binding to `pwm-sun55i-t527.ko`.
- **Sysfs Fan Control Service (`scripts/opi4a-fan-pwm.sh`, `config/opi4a-fan-pwm.service`, `config/opi4a-fan-pwm.conf`):**
  - Drives Physical Pin 7 (`pwmchip0/pwm8`) at **20 kHz** (`period = 50000` ns) with **`normal` polarity** (for a non-inverting low-side NPN transistor switch driving a 2-wire DC fan).
  - Continuously tracks the **maximum temperature** across all `/sys/class/thermal/thermal_zone*` sensors (`cpub-thermal`, `cpul-thermal`, `gpu-thermal`, `npu-thermal`, `ddr-thermal`).
  - Includes 3 °C step-down hysteresis and a 2-second 60% kick-start pulse when spinning up from 0%.
- **Pin 7 Verification Script (`scripts/test_pwm_pin7.sh`):**
  - Validates module load, `/sys/class/pwm/pwmchip0`, `PB4` `ALT5` (`pwm0_8`) pinmux, sysfs `period`/`duty_cycle`/`polarity`/`enable` readback, and live hardware counter (`PCNTR8`) progression via `/dev/mem`.

---

## 2. Directory Structure

```text
pwm_enable/
├── README.md                                 # This documentation
├── install.sh                                # Automated installer (DTB, kmod, conf, systemd service)
├── uninstall.sh                              # Clean uninstaller & DTB rollback
├── config/
│   ├── pwm-sun55i-t527.conf                  # /etc/modules-load.d/pwm-sun55i-t527.conf
│   ├── opi4a-fan-pwm.conf                    # /etc/default/opi4a-fan-pwm (thresholds & duty curve)
│   └── opi4a-fan-pwm.service                 # /etc/systemd/system/opi4a-fan-pwm.service
├── dtb/
│   ├── sun55i-t527-orangepi-4a-audio.dtb     # Prebuilt G2D + PWM8 Device Tree Blob
│   ├── sun55i-t527-orangepi-4a-audio.dts     # Uncompiled patched DTS source
│   └── pwm8-pb4.patch                        # Minimal diff vs G2D baseline DTS
├── kernel/
│   ├── pwm-sun55i-t527.ko                    # Prebuilt module for 6.18.44-g61025ec85b88
│   ├── install_kmod.sh                       # Installs module to /lib/modules/$(uname -r)/extra/
│   └── src/
│       ├── pwm-sun55i-t527.c                 # Out-of-tree driver source
│       ├── Makefile
│       └── Kbuild
└── scripts/
    ├── opi4a-fan-pwm.sh                      # Sysfs PWM fan control daemon (/usr/local/bin/)
    └── test_pwm_pin7.sh                      # Live Pin 7 (PB4 / PWM8) hardware verification script
```

---

## 3. Hardware & Pin Mapping

The Orange Pi 4A 40-pin header exposes **three** hardware PWM-capable pins, all belonging to the `pwm0@2000c00` controller (`pwmchip0`, channels `0–15`):

| Signal | Physical Pin | SoC Pin | `gpiochip1` Line | `pwmchip0` Channel | `allwinner,pinmux` | `gpio readall` Mode | Status in This Build |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `PWM8` | **Pin 7** | `PB4` | `36` | `pwm8` (`8`) | `0x05` (`pwm0_8`) | `ALT5` | **Enabled** |
| `PWM12` | **Pin 32** | `PI11` | `267` | `pwm12` (`12`) | `0x04` (`pwm0_12`) | `ALT4` | Unused (`GPIO`/free) |
| `PWM13` | **Pin 33** | `PI12` | `268` | `pwm13` (`13`) | `0x04` (`pwm0_13`) | `ALT4` | Unused (`GPIO`/free) |

> **Note:** Only **Pin 7 (`PB4` / `PWM8`)** is pinmuxed in the included `.dtb` so Pins 32 and 33 remain free as normal GPIOs (and note `PI11`/`PI12` also share `uart3` if UART3 is ever enabled).

### Enabling the Other PWM Pins (`PWM12` / `PWM13`) in `.dts`

Because `pwm-sun55i-t527.ko` already exposes all 16 channels (`0–15`) on `/sys/class/pwm/pwmchip0`, no driver change is needed to use Pin 32 or Pin 33—only the pinmux in `dtb/sun55i-t527-orangepi-4a-audio.dts` (or `dtb/pwm8-pb4.patch`) needs updating:

1. Inside `/soc/pinctrl@2000000`, add pinmux node(s) with unused phandles (e.g., `0x5d`, `0x5e`):
   ```dts
   pwm0-12-pins {
       pins = "PI11";
       function = "pwm0_12";
       allwinner,pinmux = <0x04>;
       drive-strength = <0x0a>;
       phandle = <0x5d>;
   };

   pwm0-13-pins {
       pins = "PI12";
       function = "pwm0_13";
       allwinner,pinmux = <0x04>;
       drive-strength = <0x0a>;
       phandle = <0x5e>;
   };
   ```
2. Add those phandles to `/soc/pwm@2000c00`:
   ```dts
   pinctrl-0 = <0x5b 0x5d 0x5e>;
   ```
3. Recompile with `dtc -I dts -O dtb -o sun55i-t527-orangepi-4a-audio.dtb sun55i-t527-orangepi-4a-audio.dts`, install to `/boot/dtb/allwinner/sun55i-t527-orangepi-4a-audio.dtb`, and reboot. You can then export channel `12` (`pwm12`) or `13` (`pwm13`) under `/sys/class/pwm/pwmchip0/`.

### T527 `pwm0@2000c00` Register Summary (Channel 8)

- `PWM_PCCR89` (`0x02000c30`): Clock source (`[8:7]`: `0` = 24 MHz HOSC, `1` = APB0) & pre-divider `div_m` (`[3:0]`).
- `PWM_PCGR` (`0x02000c40`): Per-channel clock gating (`BIT(8)` for `PWM8`).
- `PWM_PER` (`0x02000c80`): Per-channel enable (`BIT(8)` for `PWM8`).
- `PWM_PCR8` (`0x02000e00`): Prescaler `K` (`[7:0]`), active polarity `ACT_STA` (`BIT(8)`), `PERIOD_RDY` (`BIT(11)`).
- `PWM_PPR8` (`0x02000e04`): Entire cycles `- 1` (`[31:16]`), active cycles (`[15:0]`). At 20 kHz (`50000` ns) on 24 MHz HOSC: `entire = 1200` (`0x04af` stored), e.g. 50% duty `active = 600` (`0x0258`).
- `PWM_PCNTR8` (`0x02000e08`): Live 16-bit hardware counter (`0..1199`).

---

## 4. Installation

### Quick Install (Prebuilt Artifacts)

```bash
cd /home/ukhan/orangepi4A/pwm_enable
sudo ./install.sh
sudo reboot
```

After reboot, verify Pin 7 hardware PWM:

```bash
sudo /home/ukhan/orangepi4A/pwm_enable/scripts/test_pwm_pin7.sh
sudo systemctl status opi4a-fan-pwm.service
```

### Rebuilding the Driver or DTB from Source

```bash
# Rebuild kernel module
cd /home/ukhan/orangepi4A/pwm_enable/kernel/src
make clean && make
cp pwm-sun55i-t527.ko ../

# Recompile Device Tree Blob
cd /home/ukhan/orangepi4A/pwm_enable/dtb
dtc -I dts -O dtb -o sun55i-t527-orangepi-4a-audio.dtb sun55i-t527-orangepi-4a-audio.dts
```

---

## 5. Fan Control Curve & Tuning (`/etc/default/opi4a-fan-pwm`)

Default settings for 20 kHz (`PERIOD_NS=50000`), `POLARITY=normal` (NPN transistor):

| Max Sensor Temp (`thermal_zone*`) | Duty Cycle (ns) | Fan Speed | Notes |
| --- | --- | --- | --- |
| `< 55 °C` (step-down `< 52 °C`) | `0` | `0%` (Off) | 3 °C hysteresis |
| `>= 55 °C` | `20000` | `40%` | 2 s `30000` ns (60%) kick-start from `0%` |
| `>= 65 °C` | `30000` | `60%` | Medium cooling |
| `>= 73 °C` | `40000` | `80%` | High cooling |
| `>= 80 °C` | `50000` | `100%` | Full speed |

Edit `/etc/default/opi4a-fan-pwm` and restart the service to adjust thresholds:

```bash
sudo nano /etc/default/opi4a-fan-pwm
sudo systemctl restart opi4a-fan-pwm.service
journalctl -u opi4a-fan-pwm.service -f
```

---

## 6. Manual Sysfs Usage

```bash
echo 8 | sudo tee /sys/class/pwm/pwmchip0/export
echo 50000 | sudo tee /sys/class/pwm/pwmchip0/pwm8/period
echo normal | sudo tee /sys/class/pwm/pwmchip0/pwm8/polarity
echo 25000 | sudo tee /sys/class/pwm/pwmchip0/pwm8/duty_cycle
echo 1 | sudo tee /sys/class/pwm/pwmchip0/pwm8/enable
```

---

## 7. Rollback / Uninstall

```bash
cd /home/ukhan/orangepi4A/pwm_enable
sudo ./uninstall.sh
sudo reboot
```

`uninstall.sh` disables `opi4a-fan-pwm.service`, removes the installed script/module/autoload configs, and restores `/boot/dtb/allwinner/sun55i-t527-orangepi-4a-audio.dtb` from `.bak.pre_pwm`.
