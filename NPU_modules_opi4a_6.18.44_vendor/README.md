# Allwinner T527 VIPCore & VIPLite Vendor NPU Suite (Linux 6.18.44)

**Target Board:** Orange Pi 4A (Allwinner T527 / `sun55iw3`)  
**NPU Silicon:** VeriSilicon Vivante VIP9000nano-di (`ChipID: 0x9000`, `Revision: 0x9003`, `ProductID: 0x5090009`, `CustomerID: 0x10000016`)  
**Kernel Target:** Mainline Linux `6.18.44-g61025ec85b88` (aarch64)  
**NPU Generation:** Hardware `v2` | Software Stack `v1.13`  
**Toolchain:** GCC 13/15 (glibc 2.17+ / 2.29+ compatible)  

---

> [!IMPORTANT]
> ### Mandatory Prerequisite: Install Mainline Teflon Pathway First
> Before installing or deploying this vendor VIPCore suite, you **must first install the open-source Mainline Teflon pathway** from [`NPU_modules_opi4a_6.18.44`](../NPU_modules_opi4a_6.18.44):
> ```bash
> cd ~/NPU_modules_opi4a_6.18.44
> sudo ./install.sh
> ```
> **Why this foundational installation is required:**
> 1. **Foundational Udev Rules & Device Access:** `NPU_modules_opi4a_6.18.44` deploys `/etc/udev/rules.d/99-etnaviv-npu.rules` and automatically provisions standard `render` group permissions required for hardware NPU access without root.
> 2. **Base Open-Source Driver & LiteRT Runtime:** It installs the stable mainline `etnaviv.ko` kernel driver and `libteflon.so` (Google LiteRT delegate), establishing the verified baseline platform.
> 3. **Seamless Dual-Driver Hot-Switching:** The unified driver manager (`npu` / `npu-switch`) dynamically alternates between the Mainline Teflon DRM node (`/dev/dri/renderD129`) and the Vendor VIPCore character device (`/dev/vipcore`). Having both stacks installed gives you the ability to hot-swap between standard INT8 `.tflite` models and vendor compiled `.nb` graphs on demand without rebooting.

---

## 1. Root Cause Analysis & Hardware Fixes

During the initial bringup of the Allwinner T527 VIPCore driver on mainline Linux 6.18, two major hardware/kernel-level failure modes were diagnosed and resolved:

### 1.1 ABI Layout Mismatch (`VIPLite v2.0` vs `v1.13`, `status=-11`)
- **Symptom**: Userspace initialization failed during memory allocation with `fail to allocate video memory from Dynamic Allocate, size=0x422, alloc_flag=0x10 status=-11`.
- **Root Cause**:
  - The driver initially ported (`skitzo2000/a7s-linux-drivers`) was VIPLite v2.0.3 designed for Allwinner A733 (`sun60iw2`). In v2.0, the ioctl struct `vipdrv_allocation_t` is 56 bytes.
  - The T527 userspace libraries (`ZIFENG278/ai-sdk`) are VIPLite v1.13 (`0x00010d00`), where `gckvip_allocation_t` is 32 bytes:
    ```c
    typedef struct _gckvip_allocation {
        vip_uint64_t logical;     /* 8 bytes */
        vip_uint32_t handle;      /* 4 bytes */
        vip_uint32_t physical;    /* 4 bytes */
        vip_uint32_t size;        /* 4 bytes */
        vip_uint32_t align;       /* 4 bytes */
        vip_uint32_t alloc_flag;  /* 4 bytes */
    } gckvip_allocation_t;        /* 32 bytes total */
    ```
  - When userspace invoked `VIPDRV_ALLOCATION`, the 56-byte kernel struct parsed the userspace `alloc_flag` (0x422) as `size`, and uninitialized kernel stack data (65535) as `align`, causing allocator alignment checks to reject the buffer (`status=-11`).
- **Resolution**: Ported the official Allwinner T527 vendor driver (`drivers/npu/aw_nna_vip/` from `radxa/allwinner-bsp`, branch `product-t527-linux`, driver version `1.13.0.0-AW-2023-01-09`).

### 1.2 Mainline Linux Power Domain (`genpd`) & CCU Clock Disablement (`idleState=0x0` Timeout)
- **Symptom**:
  The driver loaded `/dev/vipcore`, but running `vpm_run` hung at `gckvip_mmu_enable` (`gc_vip_kernel_mmu.c:841`), outputting:
  ```text
  DMA Address = 0x00000000
     dmaLow   = 0x00000000
     dmaHigh  = 0x00000000
  COMMAND BUF DUMP
  BF188000 : 0801006B FFFE0000 08010E12 00490000 08010E02 00000701 48000000 00000701
  BF188020 : 10000000 00000000
  failed to setup MMU, idleState=0x0
  core0 mmu enable fail for command mode
  fail to enable MMU, status=-1.
  ```
- **Diagnostic Findings**:
  1. Inspecting `/sys/kernel/debug/pm_genpd/pm_genpd_summary` revealed the NPU power domain was powered off:
     ```text
     NPU                             off-0                           0
         7122000.npu                 suspended                   0           SW
     ```
  2. Inspecting `/sys/kernel/debug/clk/clk_summary` revealed all three NPU clocks had `enable_count = 0`:
     ```text
     npu               0  0  0  480000000 ... N npu@7122000 core
     bus-npu-aclk      0  0  0  200000000 ... N npu@7122000 bus
     bus-npu-hclk      0  0  0  200000000 ... N npu@7122000 reg
     ```
  3. In `linux/allwinner/gc_vip_kernel_drv_platform.c`, runtime power management and clock enablement were compiled out because they were wrapped in `#if IS_ENABLED(CONFIG_AW_PM_DOMAINS)` (an Allwinner downstream BSP macro not present in mainline Linux).
  4. With zero power and no clocking, register writes to `0x00654` (command buffer address) and `0x003A4` (size/trigger) were ignored by the silicon, and register `0x00004` (Idle Status) remained locked at `0x0`.
- **Hardware Fix**:
  - Replaced `#if IS_ENABLED(CONFIG_AW_PM_DOMAINS)` with standard Linux generic power domain calls (`pm_runtime_enable(&pdev->dev)`).
  - In `set_vip_power_clk(CLK_ON)`:
    - Calls `pm_runtime_resume_and_get(&pdev->dev)` to power up the CCU NPU power domain.
    - Implemented `npu_clk_init()` to prepare and enable `bus` (`clk_bus`), `reg` (`ahb_gate`), and `core` (`mclk`) clocks, and deassert `rst`.
  - In `set_vip_power_clk(CLK_OFF)`:
    - Implemented `npu_clk_uninit()` to assert resets, unprepare/disable clocks, and call `pm_runtime_put_sync(&pdev->dev)`.

### 1.3 Mainline Device Tree Unnamed Reset Fallback
- **Symptom**: Mainline Device Tree node `npu@7122000` has `resets = <&ccu RST_BUS_NPU>;` without `reset-names`. Driver crashed or failed if querying `"core"`.
- **Resolution**: Updated reset lookup in `gckvip_drv_adjust_param()` to fall back through `devm_reset_control_get(&pdev->dev, "core")` $\rightarrow$ `devm_reset_control_get(&pdev->dev, NULL)` $\rightarrow$ `devm_reset_control_get_by_index(&pdev->dev, 0)`.

---

## 2. Directory Structure

```text
~/NPU_modules_opi4a_6.18.44_vendor/
├── NPU_enable.sh               # Canonical dual-stack driver manager (symlinked to /usr/local/bin/npu and /usr/local/bin/npu-switch)
├── NPU_enable.md               # Operations manual for dual-stack switching & telemetry
├── opi-mon                     # 37-col terminal monitoring dashboard (tracks NPU load)
├── opi-mon.md                  # Hardware telemetry guide for dual etnaviv & vipcore monitoring
├── bin/
│   └── vpm_run                 # Self-contained NBG model runner (built for T527 with rpath)
├── config/
│   ├── 99-vipcore.rules        # Udev rule for /dev/vipcore rw permissions
│   └── blacklist-etnaviv.conf  # Modprobe config to isolate etnaviv when using vipcore
├── include/
│   ├── vip_lite.h              # VIPLite C API header
│   └── vip_lite_common.h       # VIPLite hardware & buffer definitions
├── kernel/
│   ├── install_kmod.sh         # Script to install vipcore.ko to kernel extra/
│   ├── vipcore.ko              # Patched & compiled kernel module for Linux 6.18.44
│   └── src/                    # Out-of-tree C source code with 6.18 & DT reset patches
├── lib/
│   ├── install_lib.sh          # Installs libraries to /usr/local/lib
│   ├── libVIPlite.so           # High-level NBG graph execution runtime (ARM64)
│   └── libVIPuser.so           # Low-level hardware interface & /dev/vipcore IOCTL layer
├── sample/
│   ├── input_0.dat             # Sample input tensor data
│   ├── network_binary.nb       # Pre-compiled T527 (v2) NBG machine code model
│   └── sample.txt              # Execution configuration file for vpm_run
├── scripts/
│   ├── load_vipcore.sh         # Safely unloads etnaviv and initializes /dev/vipcore
│   ├── unload_vipcore.sh       # Unloads vipcore module
│   └── run_test.sh             # End-to-end inference verification script
└── README.md
```

---

## 3. Component Details

### 3.1 Userspace Libraries (`lib/` and `include/`)
Extracted from `ZIFENG278/ai-sdk` (`viplite-tina/lib/glibc-gcc13_2_0/v1.13/`):
- **`libVIPlite.so`**: Provides `vip_init()`, `vip_create_network()`, `vip_set_input()`, `vip_run_network()`, `vip_get_output()`, and `vip_destroy_network()`.
- **`libVIPuser.so`**: Handles physical CMA video memory mapping and direct `ioctl()` calls to `/dev/vipcore`.
- **`vip_lite.h` & `vip_lite_common.h`**: Complete C API prototypes for building custom application runtimes or Python bindings.

### 3.2 Model Runner (`bin/vpm_run`)
Built natively on the Orange Pi 4A targeting **T527 (NPU v2, SW v1.13)**:
- Compiled with transitive dynamic linker search paths (`-Wl,-rpath,'$ORIGIN/../lib' -Wl,--disable-new-dtags`).
- Operates out-of-the-box without requiring `LD_LIBRARY_PATH` or root library installations.

### 3.3 Kernel Module (`kernel/vipcore.ko` & `kernel_t527_v1.13/`)
Ported from genuine Allwinner T527 vendor driver (`drivers/npu/aw_nna_vip` in `radxa/allwinner-bsp`, branch `product-t527-linux`, driver version `1.13.0.0-AW-2023-01-09`) with adaptations for mainline Linux 6.18:
1. Reimplemented `nth_page()` pointer arithmetic and `MAX_PAGE_ORDER` compatibility in `compat618.h`.
2. Handled `platform_driver.remove` returning `void`, `vm_flags_set()` for memory mapping, and `get_user_pages()` 4-argument signature.
3. Added `"vivante,gc"` Device Tree matching compatible with the mainline T527 NPU node (`/sys/firmware/devicetree/base/soc/npu@7122000`).
4. **Mainline Unnamed Reset Patch**: Mainline DT lacks `reset-names = "core"`; patched driver to fallback to unnamed reset phandle index 0 (`devm_reset_control_get_by_index`).
5. **Mainline Power Domain & Clock Management**: Mainline Linux uses standard generic power domains (`CONFIG_PM_GENERIC_DOMAINS=y`). Patched `set_vip_power_clk()` to call `pm_runtime_resume_and_get(&pdev->dev)` and `pm_runtime_put_sync(&pdev->dev)`, and dynamically enabled mainline CCU clocks (`bus`, `reg`, `core`) and deasserted resets upon power on.

---

## 4. Operations & Driver Management

The suite provides both a high-level canonical CLI (`npu` / `npu-switch`) installed to `/usr/local/bin/` and standalone modular scripts in `scripts/`.

### 4.1 System-Wide CLI Symlinks & Canonical `npu` Management Utility

The canonical management tool [`NPU_enable.sh`](file:///home/ukhan/NPU_modules_opi4a_6.18.44_vendor/NPU_enable.sh) is exposed system-wide via two symlinks in `/usr/local/bin`:
- `/usr/local/bin/npu` $\rightarrow$ `/home/ukhan/NPU_modules_opi4a_6.18.44_vendor/NPU_enable.sh`
- `/usr/local/bin/npu-switch` $\rightarrow$ `/home/ukhan/NPU_modules_opi4a_6.18.44_vendor/NPU_enable.sh`
- `~/NPU_enable.sh` $\rightarrow$ `/home/ukhan/NPU_modules_opi4a_6.18.44_vendor/NPU_enable.sh`

#### Creating / Verifying the System Symlinks
```bash
sudo ln -sf /home/ukhan/NPU_modules_opi4a_6.18.44_vendor/NPU_enable.sh /usr/local/bin/npu
sudo ln -sf /home/ukhan/NPU_modules_opi4a_6.18.44_vendor/NPU_enable.sh /usr/local/bin/npu-switch
ln -sf /home/ukhan/NPU_modules_opi4a_6.18.44_vendor/NPU_enable.sh ~/NPU_enable.sh
```

#### Commands Supported:
```bash
# 1. Query current NPU driver state, device nodes, permissions & telemetry
npu status

# 2. Switch to Vendor VIPCore Stack (/dev/vipcore)
sudo npu vipcore
# (or: sudo npu-switch vipcore)

# 3. Switch back to Mainline Teflon Stack (/dev/dri/renderD129)
sudo npu teflon
# (or: sudo npu-switch teflon)

# 4. Power-gate / disable all NPU drivers (clean idle 0W state)
sudo npu disable

# 5. Run hardware inference smoke-test (auto-detects active driver)
npu test
```

### 4.2 Low-Level Modular Scripts (`scripts/`)
If preferred, individual lifecycle scripts can be invoked directly:
- **Load VIPCore:**
  ```bash
  cd ~/NPU_modules_opi4a_6.18.44_vendor/scripts
  ./load_vipcore.sh
  ```
- **Unload VIPCore & Restore Teflon:**
  ```bash
  cd ~/NPU_modules_opi4a_6.18.44_vendor/scripts
  ./unload_vipcore.sh
  sudo modprobe etnaviv
  ```

### 4.3 Running Sample NBG Inference (`vpm_run`)
Execute the test runner against the pre-compiled T527 NBG model:

```bash
cd ~/NPU_modules_opi4a_6.18.44_vendor/scripts
./run_test.sh
```

Expected output:
```text
[+] Running vpm_run on sample T527 NBG model...
loop_count=1, device_id=0, file_name=sample.txt bypass=1
init vip lite, driver version=0x00010d00...
VIPLite driver software version 1.13.0.0-AW-2023-10-19
vip lite init OK.

cid=0x10000016, device_count=1
  device[0] core_count=1
config file read network count=1
init test resources, task_count: 1 ...
create/prepare networks ...
task i=0, binary name: ./network_binary.nb
nbg name=./network_binary.nb
create network 0: 1281 us.
input 0 dim 224 224 3 1, data_format=2, quant_format=2, name=input[0], scale=0.007843, zero_point=128
ouput 0 dim 2 1 0 0, data_format=2, name=uid_1_out_0, scale=0.065554, zero_point=128
memory pool size=1092608byte
network core count=1
prepare network 0: 1121 us.
golden file count=0
input 0 name: ./input_0.dat
read input and golden 0: 502 us.
task: 0, loop count: 1
start to run network=./network_binary.nb
run time for this network 0: 13142 us.
run network done...
profile inference time=12978us, cycle=6209883
destroy test resource task_count=1
vpm run ret=0
```
- **Inference Time**: **12.98 ms** (~**77 FPS**) on Allwinner T527 VIP9000 hardware!

### 4.4 Real-Time Telemetry & Hardware Monitoring (`opi-mon`)
To monitor NPU hardware execution in real-time while running vendor inference:
```bash
# Launch interactive 1-second refresh dashboard
opi-mon

# Single snapshot query
opi-mon --once
```
`opi-mon` tracks GICv3 hardware interrupts (`vipcore_0`) and active character device bindings on `/dev/vipcore` to report true silicon duty cycle.

---

## 5. Offline Model Compilation Pipeline on Proxmox

To compile custom ONNX, PyTorch, or TensorFlow models into T527 NBG (`.nb`) files:

1. **Launch ACUITY Toolkit Docker on Proxmox (`ssh proxmox`)**:
   ```bash
   # Download Allwinner ACUITY v1.8.13 image (for T527)
   wget https://netstorage.allwinnertech.com:5001/sharing/N6TVlZQVZ -O docker_images_v1.8.x.zip
   unzip docker_images_v1.8.x.zip
   unzip ubuntu-npu_v1.8.13.tar.zip
   docker load -i ubuntu-npu_v1.8.13.tar

   # Start container
   docker run --ipc=host -itd -v $(pwd)/workspace:/workspace --name acuity_t527 ubuntu-npu:v1.8.13 /bin/bash
   docker exec -it acuity_t527 /bin/bash
   ```

2. **Convert, Quantize, and Export inside Container**:
   ```bash
   # Select T527 NPU generation
   source env.sh v2

   # Import model
   pegasus_import.sh MyModel/

   # Quantize to Per-Channel INT8 (PCQ) or INT16
   pegasus_quantize.sh MyModel pcq 10

   # Export NBG machine code
   pegasus_export_ovx.sh MyModel pcq
   ```
   The resulting `network_binary.nb` file can be copied directly to the Orange Pi 4A and executed with `vpm_run`.

---

## 6. Official References & Documentation
- [Radxa Cubie NPU Development Overview](https://docs.radxa.com/en/cubie/a7s/app-dev/npu-dev)
- [Radxa vpm_run Tool Guide](https://docs.radxa.com/en/cubie/a7s/app-dev/npu-dev/cubie-vpm-run)
- [ACUITY Toolkit Usage Guide](https://docs.radxa.com/en/cubie/a7s/app-dev/npu-dev/cubie-acuity-usage)
- [Radxa AI-SDK Repository](https://github.com/ZIFENG278/ai-sdk)
- [Mainline 6.18 VIPCore Kernel Driver Port](https://github.com/skitzo2000/a7s-linux-drivers)
