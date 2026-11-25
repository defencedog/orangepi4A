# Mesa 26.0.8 Teflon / Allwinner T527 VIP9000 source patches

This directory contains the **source-level changes** behind the prebuilt Mesa
Teflon delegate (`lib/libteflon.so`) shipped in
[`NPU_modules_opi4a_6.18.44`](../). The repository previously published only the
built library and the patched kernel driver; this bundle makes the Mesa side
reviewable, reproducible, and upstreamable.

- **Upstream baseline:** Mesa 26.0.8 (`mesa_26.0.8.orig.tar.xz`)
- **Target:** Allwinner T527 (Orange Pi 4A), VeriSilicon VIP9000 NPU
  (`ChipID 0x9000`, `ProductID 0x5090009`)
- **Patch:** [`patches/mesa-26.0.8-vip9000-teflon.patch`](patches/mesa-26.0.8-vip9000-teflon.patch)
- **Apply:** `git apply patches/mesa-26.0.8-vip9000-teflon.patch` from the Mesa
  source root (or `patch -p1 < ...`)
- **Upstream context:** Mesa MR 45078 (VIP9000 / Teflon support)

The patch is intentionally a **patch bundle, not a fork**. Do not commit a full
Mesa source tree to this repository — 26.0.8 plus build artifacts is hundreds of
megabytes and is unnecessary.

## Contents

| Path | Purpose |
|---|---|
| `patches/mesa-26.0.8-vip9000-teflon.patch` | Combined source patch (10 files). |
| `patches/STAT.txt` | `git diff --stat` of the patch. |
| `scripts/make_allwinner_hwdb.py` | Generates `src/etnaviv/hwdb/allwinner/gc_feature_database.h`. |
| `scripts/patch_tfl_device.py` | Applies the `tfl_device.c` reshape/error-path changes (historical helper). |
| `build/build.sh` | Configure + build `libteflon.so` from pristine Mesa 26.0.8. |
| `build/cross_aarch64.txt` | Cross file used for the original x86_64 → aarch64 build. |
| `validation/VALIDATION.md` | Patch/reproduce/smoke-test record. |
| `validation/EXPECTED_SHA256SUMS` | Reference hashes for the artifacts. |
| `MANIFEST.json` | Bundle inventory and hashes. |
| `PLAN.json` | Detailed generation and validation plan. |

## Change summary

| File | Change |
|---|---|
| `src/gallium/drivers/etnaviv/etnaviv_ml.c` | VIP9000 `init_npu()` register setup, multi-VIP sync/stall gated behind `ETNA_ENABLE_STALL`, skip 3D transposes for non-3D tensors, boot-inference batching guard, `ETNA_NN_CORES`/`ETNA_NN_TOKEN` overrides. |
| `src/gallium/drivers/etnaviv/etnaviv_ml_nn.c` | `ETNA_NN_LAYER_TYPE`, `ETNA_NN_NO_Z_OFFSET`, `ETNA_NN_LAYER_FLUSH`, `ETNA_NN_NO_FLUSH` overrides; core-info lookup. |
| `src/gallium/drivers/etnaviv/etnaviv_ml_nn_v8.c` | `ETNA_NN_SUPERBLOCKS` override and VIP9000 weights-per-core superblock heuristic. |
| `src/gallium/drivers/etnaviv/etnaviv_compiler.c` | Null-compiler guard. |
| `src/gallium/drivers/etnaviv/etnaviv_screen.c` | Skip the softpin capability check for NPU-only devices. |
| `src/gallium/frontends/teflon/tfl_device.c` | Correct `RESHAPE` shape handling (tensor vs. builtin params) and robust create/destroy error paths. |
| `src/etnaviv/hwdb/hwdb.h.py` | Fallback HWDB lookups (ChipID+ProductID+CustomerID, then ChipID+ProductID). |
| `src/etnaviv/hwdb/meson.build` | Add the `allwinner/` HWDB directory to the generated `hwdb.h`. |
| `src/etnaviv/hwdb/allwinner/gc_feature_database.h` | New VIP9000 T527 (Formal + Informal) feature database. |
| `src/gallium/winsys/etnaviv/drm/etnaviv_drm_winsys.c` | Keep the selected GPU/NPU core alive (`core == gpu \|\| core == npu`). |

The kernel/etnaviv side is already published in [`../kernel/src`](../kernel/src)
(full patched driver source: `etnaviv_buffer.c`, `etnaviv_gpu.c`,
`etnaviv_hwdb.c`, …) and summarized in [`../README.md`](../README.md) §2.3.

## Build

### Cross-compile (x86_64 host → aarch64 Orange Pi 4A)

```bash
tar -xf mesa_26.0.8.orig.tar.xz
cd mesa_patches
./build/build.sh ../mesa-26.0.8 --cross ./build/cross_aarch64.txt
```

The original artifact was built with:

- `aarch64-linux-gnu-gcc` 11.4.0 / binutils 2.38 (Ubuntu 22.04 cross)
- Meson 1.12.0, Ninja
- `-Dbuildtype=release -Dgallium-drivers=etnaviv -Dteflon=true
  -Dvulkan-drivers= -Dplatforms= -Dglx=disabled -Dgbm=disabled
  -Degl=disabled -Dgles1=disabled -Dgles2=disabled -Dopengl=false
  -Dshared-glapi=disabled -Dllvm=disabled`
- `build/cross_aarch64.txt` (adjust the `mesa_clc`, `vtn_bindgen2`, rust and
  `exe_wrapper` paths for your host if they differ)

### Native (on the Orange Pi 4A)

```bash
sudo apt install meson ninja-build gcc g++ pkg-config \
  libdrm-dev libexpat1-dev zlib1g-dev libzstd-dev
./build/build.sh ../mesa-26.0.8 --native
```

## Environment variables

The patched code keeps the upstream defaults but exposes the following
overrides for bring-up and debugging:

| Variable | Meaning |
|---|---|
| `ETNA_ENABLE_STALL` | Re-enable the multi-VIP stall/semaphore sequence (default off on VIP9000). |
| `ETNA_NN_TOKEN` | Override the stall token (default `0x30000701`). |
| `ETNA_NN_CORES` | Override `nn_core_count`. |
| `ETNA_NN_CONFIG` | Override the whole `VIVS_GL_NN_CONFIG` word (core count, small-batch, ...). |
| `ETNA_NN_LAYER_TYPE` | Override NN layer type (default `0x0`). |
| `ETNA_NN_NO_Z_OFFSET` | Override no-z-offset (default: NN core version 8). |
| `ETNA_NN_LAYER_FLUSH` | Override NN layer flush (default `0x1`). |
| `ETNA_NN_NO_FLUSH` | Override no-flush (default: off for VIP9000, else NN core version 8). |
| `ETNA_NN_SUPERBLOCKS` | Override the superblock count. |
| `ETNA_NN_SRAM_CACHE` | Override the kernel/image SRAM cache mode. |
| `ETNA_NN_10A4` | Override `VIVS_PS_UNK10A4` (per-operation offset). |
| `ETNA_NN_10A8` | Set `VIVS_PS_MULTI_CLUSTER_UNK10A8`. |
| `ETNA_MAX_OPS` | Stop after N operations (bring-up/bisect aid). |
| `ETNA_START_OP` | Start at operation N (bring-up/bisect aid). |
| `ETNA_ALWAYS_INIT` | Re-run `init_npu()` before every operation (bring-up aid). |

## Validation

See [`validation/VALIDATION.md`](validation/VALIDATION.md) for the full record.
Summary:

- Patch applies cleanly to pristine Mesa 26.0.8 and reproduces the 10 changed
  files byte-for-byte.
- A cross-rebuild from pristine + patch reproduces the shipped
  `../lib/libteflon.so` **byte-for-byte**:
  `sha256 10bd3eae0d08427fecd47527fed8e796aaed2ae75c6d5fa21ad8c8574b009576`
  (11,804,760 bytes, unstripped).
- The shipped artifact executes hardware inference on the T527 VIP9000
  (`conv2d.tflite`, sysfs active-time delta, clean autosuspend).

> To reproduce the exact binary, build in a non-git tree (`MESA_GIT_SHA1`
> empty) and without `libudev` detection, matching the original host. Mesa's
> generated `src/etnaviv/isa/encode.h` is ordered nondeterministically by the
> isaspec generator; reusing the original generated header (or an equivalent
> ordering) gives the identical binary. See `validation/VALIDATION.md`.

## License and credits

- Mesa is MIT-licensed; the new HWDB file carries the Vivante MIT header.
- The T527 VIP9000 stabilization patches were developed for the Orange Pi 4A
  community and are intended to be folded into Mesa MR 45078.
- Kernel-side patches live in [`../kernel/src`](../kernel/src); see
  [`../README.md`](../README.md) §2.3 for the summary table.
