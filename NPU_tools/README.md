# Orange Pi 4A (Allwinner T527 ARM64) Acceleration Stack: Build & Deployment Guide

This document provides a comprehensive, reproducible reference for cross-compiling and deploying the hardware acceleration stack for the **Orange Pi 4A** (Allwinner T527 SoC, featuring an 8-core Cortex-A55 CPU, Mali-G57 MC1 GPU with Panfrost/Rusticl OpenCL 3.0, and VeriSilicon VIP9000 2 TOPS NPU).

---

## 1. Architecture Overview

- **Target Architecture:** `aarch64` (ARM64 Little Endian)
- **Target OS:** Debian Trixie 13 / Ubuntu 22.04/24.04 on Orange Pi 4A
- **GPU Architecture:** ARM Mali-G57 MC1 (Valhall generation 1 / v9)
- **GPU OpenCL Driver:** Mesa Gallium Panfrost + Rusticl (OpenCL 3.0 Conformant)
- **Inference Engine:** Alibaba MNN (Mobile Neural Network) with OpenCL GPU acceleration + ARM82 FP16 vectorization
- **NPU:** VeriSilicon VIP9000 2.0 TOPS NPU (via TIM-VX / OpenVX runtime)

---

## 2. Host Build System Setup (Ubuntu x86_64 LXC / Host)

### 2.1 Multiarch Repositories & Cross-Toolchain Installation
Add ARM64 multiarch ports and install the complete GNU cross-compilation toolchain:

```bash
# Add ARM64 architecture to dpkg
dpkg --add-architecture arm64

# Configure Ubuntu Ports for ARM64 dependencies
cat << "PORTS_EOF" > /etc/apt/sources.list.d/arm64-ports.list
deb [arch=arm64] http://ports.ubuntu.com/ubuntu-ports/ jammy main restricted universe multiverse
deb [arch=arm64] http://ports.ubuntu.com/ubuntu-ports/ jammy-updates main restricted universe multiverse
deb [arch=arm64] http://ports.ubuntu.com/ubuntu-ports/ jammy-security main restricted universe multiverse
PORTS_EOF

# Update package cache
apt-get update

# Install host tools & cross-compilers
apt-get install -y \
    build-essential gcc-aarch64-linux-gnu g++-aarch64-linux-gnu binutils-aarch64-linux-gnu \
    pkg-config-aarch64-linux-gnu qemu-user-static cmake ninja-build git python3-pip python3-mako \
    bison flex llvm-15-dev libclang-15-dev clang-15 curl libssl-dev

# Install modern Meson (>= 1.1.0)
pip3 install meson==1.12.0

# Install Rust & ARM64 target
curl --proto "=https" --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
source "$HOME/.cargo/env"
rustup target add aarch64-unknown-linux-gnu
cargo install cbindgen bindgen-cli
```

### 2.2 ARM64 Target Development Libraries
Install the required target libraries for OpenCL, Gallium, and display backends:

```bash
apt-get install -y \
    libdrm-dev:arm64 libelf-dev:arm64 libexpat1-dev:arm64 libzstd-dev:arm64 \
    libunwind-dev:arm64 zlib1g-dev:arm64 libwayland-dev:arm64 wayland-protocols \
    libwayland-egl-backend-dev:arm64 libx11-dev:arm64 libxext-dev:arm64 \
    libxdamage-dev:arm64 libxfixes-dev:arm64 libx11-xcb-dev:arm64 libxcb-glx0-dev:arm64 \
    libxcb-dri2-0-dev:arm64 libxcb-dri3-dev:arm64 libxcb-present-dev:arm64 \
    libxcb-sync-dev:arm64 libxshmfence-dev:arm64 libxrandr-dev:arm64
```

---

## 3. Cross-Compiling the Acceleration Components

Create the working directory:
```bash
mkdir -p /root/builds/orangepi4a && cd /root/builds/orangepi4a
```

### 3.1 Khronos SPIRV-Headers & SPIRV-Tools
> [!IMPORTANT]
> Always compile `SPIRV-Tools` with `-DCMAKE_BUILD_TYPE=Release` to ensure debug assertions (`assert`) in the SPIR-V pass manager are disabled.

```bash
# 1. SPIRV-Headers
git clone https://github.com/KhronosGroup/SPIRV-Headers.git
mkdir -p SPIRV-Headers/build && cd SPIRV-Headers/build
cmake .. -G Ninja -DCMAKE_INSTALL_PREFIX=/usr
ninja install
cd /root/builds/orangepi4a

# 2. SPIRV-Tools (Target ARM64 - Release Mode)
git clone https://github.com/KhronosGroup/SPIRV-Tools.git
mkdir -p SPIRV-Tools/build_aarch64 && cd SPIRV-Tools/build_aarch64
cmake .. -G Ninja \
    -DCMAKE_SYSTEM_NAME=Linux \
    -DCMAKE_SYSTEM_PROCESSOR=aarch64 \
    -DCMAKE_C_COMPILER=aarch64-linux-gnu-gcc \
    -DCMAKE_CXX_COMPILER=aarch64-linux-gnu-g++ \
    -DSPIRV-Headers_SOURCE_DIR=/root/builds/orangepi4a/SPIRV-Headers \
    -DSPIRV_SKIP_TESTS=ON \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_INSTALL_PREFIX=/usr \
    -DCMAKE_INSTALL_LIBDIR=lib/aarch64-linux-gnu
ninja -j$(nproc) install
cd /root/builds/orangepi4a

# 3. SPIRV-Tools (Host x86_64 for mesa_clc shader compiler)
mkdir -p SPIRV-Tools/build_x86 && cd SPIRV-Tools/build_x86
cmake .. -G Ninja \
    -DSPIRV-Headers_SOURCE_DIR=/root/builds/orangepi4a/SPIRV-Headers \
    -DSPIRV_SKIP_TESTS=ON \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_INSTALL_PREFIX=/usr \
    -DCMAKE_INSTALL_LIBDIR=lib/x86_64-linux-gnu
ninja -j$(nproc) install
cd /root/builds/orangepi4a
```

### 3.2 Khronos SPIRV-LLVM-Translator
Translates LLVM IR to SPIR-V bytecode for OpenCL C kernel compilation:

```bash
git clone -b release_150 https://github.com/KhronosGroup/SPIRV-LLVM-Translator.git

# Target ARM64 Build:
mkdir -p SPIRV-LLVM-Translator/build_aarch64 && cd SPIRV-LLVM-Translator/build_aarch64
cmake .. -G Ninja \
    -DCMAKE_SYSTEM_NAME=Linux \
    -DCMAKE_SYSTEM_PROCESSOR=aarch64 \
    -DCMAKE_C_COMPILER=aarch64-linux-gnu-gcc \
    -DCMAKE_CXX_COMPILER=aarch64-linux-gnu-g++ \
    -DLLVM_DIR=/usr/lib/llvm-15/cmake \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_CXX_STANDARD=17 \
    -DCMAKE_INSTALL_PREFIX=/usr \
    -DCMAKE_INSTALL_LIBDIR=lib/aarch64-linux-gnu
ninja -j$(nproc) install
cd /root/builds/orangepi4a

# Host x86_64 Build:
mkdir -p SPIRV-LLVM-Translator/build_x86 && cd SPIRV-LLVM-Translator/build_x86
cmake .. -G Ninja \
    -DLLVM_DIR=/usr/lib/llvm-15/cmake \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_CXX_STANDARD=17 \
    -DCMAKE_INSTALL_PREFIX=/usr \
    -DCMAKE_INSTALL_LIBDIR=lib/x86_64-linux-gnu
ninja -j$(nproc) install
cd /root/builds/orangepi4a
```

---

### 3.3 Alibaba MNN (Mobile Neural Network) Engine
Cross-compile MNN with ARM82 FP16 vectorization, OpenCL backend, OpenCV integration, and LLM demo:

```bash
git clone --depth 1 https://github.com/alibaba/MNN.git
cd MNN && mkdir build_aarch64 && cd build_aarch64

cmake .. \
    -DCMAKE_SYSTEM_NAME=Linux \
    -DCMAKE_SYSTEM_PROCESSOR=aarch64 \
    -DCMAKE_C_COMPILER=aarch64-linux-gnu-gcc \
    -DCMAKE_CXX_COMPILER=aarch64-linux-gnu-g++ \
    -DMNN_BUILD_SHARED_LIBS=ON \
    -DMNN_OPENCL=ON \
    -DMNN_ARM82=ON \
    -DMNN_BUILD_LLM=ON \
    -DMNN_BUILD_OPENCV=ON \
    -DMNN_IMGCODECS=ON \
    -DMNN_LOW_MEMORY=ON \
    -DCMAKE_BUILD_TYPE=Release

make -j$(nproc)

# Stage MNN binaries and headers
mkdir -p /root/builds/orangepi4a/dist/opt/mnn/lib /root/builds/orangepi4a/dist/opt/mnn/bin /root/builds/orangepi4a/dist/opt/mnn/include
cp libMNN.so /root/builds/orangepi4a/dist/opt/mnn/lib/
cp llm_demo /root/builds/orangepi4a/dist/opt/mnn/bin/
cp -r ../include/* /root/builds/orangepi4a/dist/opt/mnn/include/
cd /root/builds/orangepi4a
```

---

### 3.4 Mesa Panfrost + Rusticl OpenCL 3.0 Driver

#### 3.4.1 Native Host Tools (`mesa_clc` & `vtn_bindgen2`)
Mesa compiles internal OpenCL shaders into SPIR-V at build time using `mesa_clc`. Building `mesa_clc` natively avoids QEMU CPU emulation bottlenecks:

```bash
git clone --depth 1 https://gitlab.freedesktop.org/mesa/mesa.git
cd mesa

# Build native shader tools on x86_64 host
mkdir -p build_host && cd build_host
meson setup . .. \
    -Dgallium-drivers=softpipe \
    -Dvulkan-drivers= \
    -Dglx=disabled \
    -Dplatforms= \
    -Dllvm=enabled \
    -Dmesa-clc=enabled \
    -Dinstall-mesa-clc=true \
    -Dmesa-clc-bundle-headers=enabled \
    -Dbuildtype=release

ninja src/compiler/clc/mesa_clc src/compiler/spirv/vtn_bindgen2
cp src/compiler/clc/mesa_clc /usr/local/bin/mesa_clc
cp src/compiler/spirv/vtn_bindgen2 /usr/local/bin/vtn_bindgen2
cd /root/builds/orangepi4a/mesa
```

#### 3.4.2 Meson Cross-File (`cross_aarch64.txt`)
Create the cross-compilation definition file:

```ini
[binaries]
c = aarch64-linux-gnu-gcc
cpp = aarch64-linux-gnu-g++
ar = aarch64-linux-gnu-ar
strip = aarch64-linux-gnu-strip
pkg-config = aarch64-linux-gnu-pkg-config
llvm-config = /usr/bin/llvm-config-15
rust = [/root/.cargo/bin/rustc, --target, aarch64-unknown-linux-gnu, -C, linker=aarch64-linux-gnu-gcc]
exe_wrapper = /usr/bin/qemu-aarch64-static
mesa-clc = /usr/local/bin/mesa_clc
vtn_bindgen2 = /usr/local/bin/vtn_bindgen2

[properties]
needs_exe_wrapper = true

[host_machine]
system = linux
cpu_family = aarch64
cpu = aarch64
endian = little
```

#### 3.4.3 ARM64 Mesa Compilation & Staging
```bash
rm -rf build_aarch64 && mkdir -p build_aarch64 && cd build_aarch64

meson setup . .. \
    --cross-file /root/builds/orangepi4a/cross_aarch64.txt \
    -Dgallium-drivers=panfrost \
    -Dvulkan-drivers= \
    -Dgallium-rusticl=true \
    -Dgallium-rusticl-enable-drivers=panfrost \
    -Drust_std=2021 \
    -Dllvm=enabled \
    -Dmesa-clc=system \
    -Dplatforms=wayland,x11 \
    -Dprefix=/opt/mesa \
    -Dbuildtype=release

DESTDIR=/root/builds/orangepi4a/dist ninja -j$(nproc) install
```

---

## 4. Release Packaging

Bundle `/opt/mesa` and `/opt/mnn` into a standalone deployment tarball:

```bash
cd /root/builds/orangepi4a/dist
tar -czvf /root/builds/orangepi4a/orangepi4a-acceleration-stack.tar.gz opt/
```

---

## 5. Deployment on Orange Pi 4A (Allwinner T527)

### 5.1 Transfer & Extract
Copy the tarball to your Orange Pi 4A:
```bash
# On your local machine or build server:
scp /root/builds/orangepi4a/orangepi4a-acceleration-stack.tar.gz ukhan@<orangepi4a_ip>:~/Downloads/

# On Orange Pi 4A:
sudo tar -xzvf ~/Downloads/orangepi4a-acceleration-stack.tar.gz -C /
```

### 5.2 Install Runtime Dependencies on Board
```bash
sudo apt update
sudo apt install -y ocl-icd-libopencl1 clinfo libdrm2 libelf1 libexpat1 libzstd1 libunwind8 libclc-15
```

### 5.3 Register OpenCL Rusticl ICD
Register the Rusticl OpenCL driver with the system ICD loader:
```bash
echo "/opt/mesa/lib/libRusticlOpenCL.so.1" | sudo tee /etc/OpenCL/vendors/rusticl.icd
```

### 5.4 Environment Configuration
Add to `/etc/profile.d/acceleration.sh` or `~/.bashrc`:
```bash
export RUSTICL_ENABLE=panfrost
export LD_LIBRARY_PATH=/opt/mesa/lib:/opt/mnn/lib:$LD_LIBRARY_PATH
export PATH=/opt/mnn/bin:$PATH
```

### 5.5 Verification

Verify OpenCL 3.0 detection on Mali-G57:
```bash
clinfo | grep -E "Platform Name|Device Name|OpenCL C version|Driver Version"
```
*Expected Output:*
- **Platform Name:** `Rusticl`
- **Device Name:** `Mali-G57 (Panfrost)`
- **OpenCL C Version:** `OpenCL C 3.0`

Run MNN LLM on Mali-G57 GPU via OpenCL:
```bash
llm_demo /path/to/qwen2-0.5b-instruct.mnn /path/to/config.json
```

---

## 6. VeriSilicon VIP9000 NPU Acceleration (2.0 TOPS)

The Allwinner T527 includes a VeriSilicon VIP9000 NPU. To execute quantized INT8/FP16 models:
1. Ensure the kernel module `galcore.ko` is loaded:
   ```bash
   lsmod | grep galcore || sudo modprobe galcore
   ```
2. Convert ONNX models using the VeriSilicon Acuity Toolkit / TIM-VX runtime for sub-millisecond INT8 inference.
