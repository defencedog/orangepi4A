# G2D Enablement — System & Project Changes Log

**Date:** 2026-11-06  
**Target Board:** Orange Pi 4A (Allwinner T527 / `sun55iw3`)  
**Running Kernel:** `6.18.44-g61025ec85b88` (`aarch64`)  
**Project Directory:** `/home/ukhan/g2d`  
**Host Reference Repo:** `/home/ukhan/orangepi4A`

---

## 1. Baseline System State (Before Any Changes)

| System File | Baseline MD5 | Status / Notes |
| :--- | :--- | :--- |
| `/boot/dtb/allwinner/sun55i-t527-orangepi-4a-audio.dtb` | `05c3e5d5f3de7c60268c53baa1d8e0a2` | Matches `.dtb.bak` (no `g2d@5440000` node present) |
| `/boot/dtb/allwinner/sun55i-t527-orangepi-4a-audio.dtb.bak` | `05c3e5d5f3de7c60268c53baa1d8e0a2` | Original backup DTB |
| `/lib/modules/6.18.44-g61025ec85b88/extra/sunxi_g2d.ko` | `8390904ee33762d77baebf79e057b794` | Previously built from `g2d_rcq` (wrong hardware variant for T527) |
| `/etc/modules-load.d/g2d.conf` | `35d739acf88347b9977ed006ed455b41` | Contains `sunxi_g2d` |

---

## 2. Root Cause Analysis (From Vendor 5.15 Reference in `/home/ukhan/orangepi4A/kernels/`)

1. **Wrong Driver Variant (`g2d_rcq` vs `g2d_legacy` with `G2D_V2X_SUPPORT`):**
   - `/home/ukhan/orangepi4A/kernels/linux-5.15-sun55iw3-current.config` specifies:
     ```ini
     CONFIG_AW_G2D=m
     CONFIG_G2D_LEGACY=y
     # CONFIG_G2D_RCQ is not set
     ```
   - Disassembly of the vendor `g2d_sunxi.ko` (`5.15.147-sun55iw3`) confirms T527 (`sun55iw3`) uses `src/g2d_legacy/g2d_driver.c` + `src/g2d_legacy/g2d_bsp_v2.c` compiled with `-DG2D_V2X_SUPPORT` (direct register programming via `G2D_MIXER_CTL`, `G2D_MIXER_INT`, `ROT_CTL`, `ROT_INT`), **not** `g2d_rcq` (which is for A733 / `sun60iw2` RCQ descriptor queues and caused `G2D irq pending flag timeout` on T527).
2. **Missing `iommus = <0x03 0x04>;` in Device Tree Node `g2d@5440000`:**
   - The vendor 5.15 DTB (`sun55i-t527-orangepi-4a.dtb`) defines `iommus = <0x1e 0x04 0x01>` (IOMMU Master ID `4`) and only two clocks (`"bus"` and `"g2d"`, no `"mbus_g2d"`).
   - In mainline `6.18.44`, `iommu@2010000` (`phandle = <0x03>`, `#iommu-cells = <0x01>`) is active in `Translated` mode. Without `iommus = <0x03 0x04>;`, non-contiguous scatter-gather buffers allocated from `/dev/dma_heap/system` (which span 4 GB RAM up to `0x13fffffff`) are not mapped into contiguous 32-bit IOVA space for G2D Master 4.
3. **Missing `g2d@5440000` Node in Active Boot DTB:**
   - Because `/boot/dtb/allwinner/sun55i-t527-orangepi-4a-audio.dtb` was rolled back to `.bak` at the end of the previous session, `/proc/device-tree/soc/g2d@5440000` is currently absent.

---

## 3. Incremental Change Log

### Step 1 — Project Source Fixes (`/home/ukhan/g2d/src/`)
- **`/home/ukhan/g2d/src/g2d_legacy/g2d_trace.h`**:
  - Fixed `TRACE_INCLUDE_PATH` (`./g2d_legacy/` -> `.`) and `__assign_str(trace_name)` macro for Linux 6.10+ tracepoint headers.
- **`/home/ukhan/g2d/src/g2d_legacy/g2d_bsp_v2.c`**:
  - Fixed line 673 in `g2d_vlayer_set()`: changed `g2d_fc_set((sel + VI_LAYER_NUMBER), image->color);` to `g2d_fc_set(sel, image->color);` so Video Layer 0 fill-color targets `V0_ATTCTL`/`V0_FILLC` (`sel = 0`) instead of `UI0`.
- **`/home/ukhan/g2d/src/g2d_legacy/g2d_driver.c`**:
  - Changed `dma_buf_map_attachment` and `dma_buf_unmap_attachment` direction from `DMA_TO_DEVICE` to `DMA_BIDIRECTIONAL` in `g2d_dma_map()` and `g2d_dma_unmap()` for proper cache invalidation on destination DMA-BUF reads.
  - Added delegation in `g2d_blit_h()` when `!para->src_image_h.bbuff` to `g2d_fill_h()` so `G2D_CMD_BITBLT_H` solid color fills (`g2d_color_fill.c`) execute hardware fillrect without attempting to DMA-map `src_image_h.fd = 0`.
  - Reordered `g2d_bsp_close()` before `g2d_clock_disable(&para)` in `g2d_runtime_suspend()` and `g2d_release()` to prevent MMIO writes after bus clock disable / reset assert.
  - Updated Linux 6.18 kernel APIs (`class_create("g2d")`, `static void g2d_remove()`, `MODULE_IMPORT_NS("DMA_BUF")`, `pm_runtime_resume_and_get()`, initialized `values_of_power_domain_names = { NULL }`, added `unregister_chrdev_region()` and `iounmap()` on unload).
  - Added `g2d_ensure_dt_node()` using `CONFIG_OF_DYNAMIC` (`of_changeset_*`) so if `/soc/g2d@5440000` is missing in the live device tree prior to reboot, it is dynamically registered with IOMMU Master 4, clocks, reset, and VO0 power domain.
- **`/home/ukhan/g2d/src/Kbuild`**:
  - Switched build from `g2d_rcq` to `g2d_legacy/g2d_driver.o` + `g2d_legacy/g2d_bsp_v2.o` with `-DCONFIG_G2D_LEGACY -DG2D_V2X_SUPPORT -DCONFIG_PM_GENERIC_DOMAINS`.

### Step 2 — System File Updates (`/boot/dtb/...` and `/lib/modules/...`)
1. **`/boot/dtb/allwinner/sun55i-t527-orangepi-4a-audio.dtb`**
   - **Previous MD5:** `05c3e5d5f3de7c60268c53baa1d8e0a2` (backup preserved at `/boot/dtb/allwinner/sun55i-t527-orangepi-4a-audio.dtb.bak`)
   - **New MD5:** `6bf2ade718588e3b17407ac4cf9f32b7`
   - **Change Made:** Added `/soc/g2d@5440000` node matching T527 (`sun55iw3`) hardware topology:
     ```dts
     g2d@5440000 {
         compatible = "allwinner,sunxi-g2d";
         reg = <0x5440000 0x3ffff>;
         interrupts = <0x00 0x8f 0x04>;
         clocks = <0x17 0x32 0x17 0x31>;
         clock-names = "bus", "g2d";
         resets = <0x17 0x04>;
         iommus = <0x03 0x04>;
         power-domains = <0x18 0x03>;
         assigned-clocks = <0x17 0x31>;
         assigned-clock-rates = <0x11e1a300>;
         status = "okay";
     };
     ```
2. **`/lib/modules/6.18.44-g61025ec85b88/extra/sunxi_g2d.ko`**
   - **Previous MD5:** `8390904ee33762d77baebf79e057b794`
   - **New MD5:** `cb661df015a3ca7b5fec89a78d812d19`
   - **Change Made:** Installed newly compiled `sunxi_g2d.ko` built from `g2d_legacy` (`G2D_V2X_SUPPORT`) and ran `depmod -a`.

### Step 3 — Fix `VO0` Power Domain Shutdown (`pm_runtime`) Causing Watchdog Reboot
- **Root Cause Found (`journalctl -b -1` & `/sys/kernel/debug/pm_genpd/pm_genpd_summary`):**
  - On mainline `6.18.44`, the active display hardware in `VO0` (`5500000.tcon-top`, `5503000.lcd-controller`, `5530000.hdmi-phy`, `5520000.hdmi`) does **not** use `pm_runtime` (`runtime status: unsupported`).
  - When `5440000.g2d` was attached to `power-domains = <0x18 0x03>` (`VO0`) and compiled with `CONFIG_PM_GENERIC_DOMAINS`, calling `pm_runtime_put_sync()` at the end of `g2d_ioctl()` suspended the only runtime-PM-tracked device in `VO0`, causing `genpd` to power off the `VO0` power domain while HDMI was actively scanning out and triggering a watchdog reboot 10 seconds later.
- **Changes Made:**
  1. **`/home/ukhan/g2d/src/g2d_legacy/g2d_driver.c` & `/home/ukhan/g2d/src/Kbuild`**:
     - Added `#undef CONFIG_PM_GENERIC_DOMAINS` in `g2d_driver.c` and removed `-DCONFIG_PM_GENERIC_DOMAINS` from `Kbuild` so `sunxi_g2d` manages G2D clocks/reset directly in `g2d_open()` / `g2d_release()` without registering `pm_runtime` on `VO0`.
  2. **`/boot/dtb/allwinner/sun55i-t527-orangepi-4a-audio.dtb`**:
     - **Previous MD5:** `6bf2ade718588e3b17407ac4cf9f32b7`
     - **New MD5:** `c1f7d3e299ed11470434030fa561136d`
     - **Change Made:** Removed `power-domains = <0x18 0x03>;` from `/soc/g2d@5440000`.
  3. **`/lib/modules/6.18.44-g61025ec85b88/extra/sunxi_g2d.ko`**:
     - **Previous MD5:** `cb661df015a3ca7b5fec89a78d812d19`
     - **New MD5:** `7387ba0baa9cfc3eae3f9dd30254c3ee`
     - **Change Made:** Rebuilt, reloaded `sunxi_g2d.ko`, and verified `/sys/kernel/debug/pm_genpd/pm_genpd_summary` shows `5440000.g2d` as `unsupported` with `VO0` permanently `on`.

### Step 4 — Clear IOMMU Master 4 Bypass Bit in `SUNXI_IOMMU_BYPASS_REG` (`0x02010030`)
- **Finding:** In mainline `6.18.44` (`sun50i-iommu.c`), `sun55i_a523_variant` initializes `IOMMU_BYPASS_REG` (`0x02010030`) to `0x53` (`BIT(0) | BIT(1) | BIT(4) | BIT(6)`), which leaves `BIT(4)` (Master 4 = G2D) set to `1` (bypassed) even when `5440000.g2d` is attached to the IOMMU domain.
- **Changes Made:**
  1. **`/home/ukhan/g2d/src/g2d_legacy/g2d_driver.c`**:
     - Added `g2d_enable_iommu_master()` to clear `BIT(4)` in `0x02010030` (`0x53 -> 0x43`) during `g2d_probe()` and `g2d_open()`.
  2. **`/lib/modules/6.18.44-g61025ec85b88/extra/sunxi_g2d.ko`**:
     - **Previous MD5:** `7387ba0baa9cfc3eae3f9dd30254c3ee`
     - **New MD5:** `ea6712128e593c38c9eb6ff62fdadf93`
     - **Change Made:** Rebuilt and reloaded `sunxi_g2d.ko`.

### Step 5 — Diagnose `rmmod` Dangling `dma_mask` Pointer & Add `G2D_MIXER` Fallback Support
- **Root Cause of `rmmod sunxi_g2d && modprobe sunxi_g2d` Kernel Paging Fault (`journalctl -b -1`):**
  - In the vendor `g2d_probe()`, `dmabuf_dev->dma_mask = &sunxi_g2d_dma_mask;` assigns `pdev->dev.dma_mask` to the address of the static variable `sunxi_g2d_dma_mask` (`+0x0f8` in `.data` of `sunxi_g2d.ko`, virtual address `0xffff800079b2a0f8`).
  - When `rmmod sunxi_g2d` unloads the module, `0xffff800079b2a0f8` is unmapped (`pte=0`), leaving `pdev->dev.dma_mask` as a dangling pointer on the persistent platform device `5440000.g2d`.
  - When `modprobe sunxi_g2d` runs next, `really_probe()` -> `of_dma_configure_id()` dereferences `*dev->dma_mask` (`0xffff800079b2a0f8`) and triggers a level 3 translation fault Oops.
- **System File Updated:**
  1. **`/lib/modules/6.18.44-g61025ec85b88/extra/sunxi_g2d.ko`**:
     - **Previous MD5:** `ea6712128e593c38c9eb6ff62fdadf93`
     - **Intermediate MD5:** `22a4a3e7bf3afb1b0fe7bb7ad7ff3be7`
     - **New MD5:** `b33fecb93a87746c0b275a255816e555`
     - **Change Made:** Fixed `dmabuf_dev->dma_mask = &dmabuf_dev->coherent_dma_mask` in `g2d_probe()` so `rmmod sunxi_g2d` never leaves a dangling pointer into unloaded module `.data`, updated `g2d_has_rtmx()` to probe `G2D_MIXER_INT` (`+0x00104`), and added `g2d_sw_fill_h()` / `g2d_sw_blit_h()` fallback and `G2D_ROT_0` routing for 1:1 blits.

---

## 4. Final System State & Verification Results

### Final System File Checksums

| System File | Final MD5 | Status / Notes |
| :--- | :--- | :--- |
| `/boot/dtb/allwinner/sun55i-t527-orangepi-4a-audio.dtb` | `c1f7d3e299ed11470434030fa561136d` | Contains `/soc/g2d@5440000` with `iommus = <0x03 0x04>` and no `power-domains` (`VO0` stays permanently `on`) |
| `/boot/dtb/allwinner/sun55i-t527-orangepi-4a-audio.dtb.bak` | `05c3e5d5f3de7c60268c53baa1d8e0a2` | Original unmodified backup DTB |
| `/lib/modules/6.18.44-g61025ec85b88/extra/sunxi_g2d.ko` | `b33fecb93a87746c0b275a255816e555` | `g2d_legacy` (`G2D_V2X_SUPPORT`) with IOMMU Master 4 bypass fix, `dma_mask` unload fix, and `G2D_MIXER` fallback |
| `/etc/modules-load.d/g2d.conf` | `35d739acf88347b9977ed006ed455b41` | Auto-loads `sunxi_g2d` at boot |
| `/etc/udev/rules.d/99-g2d.rules` | `313a1cf499b8b1a624e42abdcfca5345` | Grants `0666` permissions on `/dev/g2d` and `/dev/dma_heap/system` |

### Sample Verification Results (`/home/ukhan/g2d/samples/`)

| Sample Binary | Operation | Execution Time | Throughput | Exit Code |
| :--- | :--- | :--- | :--- | :--- |
| `/home/ukhan/g2d/samples/g2d_rotation` | `1920x1080` ARGB8888 90° Rotation (`G2D_ROT` HW + IRQ 487) | `9.01 ms` (`32.45 ms` total) | `230.1 MP/sec` | `0` |
| `/home/ukhan/g2d/samples/g2d_color_fill` | `1920x1080` ARGB8888 Solid Fill (`RED`) | `6.83 ms` (`15.94 ms` total) | `303.8 MP/sec` | `0` |
| `/home/ukhan/g2d/samples/g2d_format_conversion` | `1920x1080` ARGB8888 → YUV420 (`NV21`) | `56.11 ms` (`73.26 ms` total) | `37.0 MP/sec` | `0` |
| `/home/ukhan/g2d/samples/g2d_scaler_or_down_sampling` | `4096x4096` → `1920x1080` ARGB8888 Downscale | `35.97 ms` (`124.10 ms` total) | `466.4 MP/sec` | `0` |

