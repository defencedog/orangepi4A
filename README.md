# Builds, binaries, tutorials for OrangePi 4A AllWinner device

## Hardware Acceleration & NPU Modules
- [**NPU Modules for Linux 6.18.44 (NPU_modules_opi4a_6.18.44)**](./NPU_modules_opi4a_6.18.44): Production activation suite for the VeriSilicon VIP9000 NPU on Allwinner T527 (Orange Pi 4A). Includes patched etnaviv.ko kernel module, out-of-tree source, patched Mesa Teflon delegate (libteflon.so), on-demand NPU controller (NPU_enable.sh), dynamic telemetry dashboard (opi-mon), and automated installer (install.sh).
- [**NPU Applications Suite for Linux 6.18.44 (NPU_proj_opi4a_6.18.44)**](./NPU_proj_opi4a_6.18.44): Production edge AI applications for the Orange Pi 4A (Allwinner T527 VIP9000). Includes sub-millisecond thermodynamic neural surrogates (IAPWS-97 steam tables), real-time vision AI (MobileNet V1 classification & SSD MobileNet object detection), and edge face clustering & identity indexing (SCRFD + MobileFaceNet + SQLite).
- [**Vendor NPU & Hardware Acceleration Tools (NPU_tools_vendor)**](./NPU_tools_vendor): Legacy vendor kernel acceleration stack, hardware monitoring utilities, and acceleration reports for the vendor Allwinner BSP.
