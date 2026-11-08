# mediafire-tools (0.60+patched5) for aarch64 / ARM64

**Target Architecture:** `arm64` / `aarch64` (Orange Pi 4A, Allwinner T527, Raspberry Pi, Ubuntu 22.04 / 24.04 / 26.04)  
**Upstream Project:** [mediafire-fuse](https://github.com/xorgy/mediafire-fuse) (Base commit `6b17698`, 2015-01-21)  
**Package Version:** `0.60+patched5`  
**License:** GPL-3.0  

---

## 1. Overview

`mediafire-tools` provides two command-line utilities for interacting with MediaFire cloud storage on Linux:
- **`mediafire-fuse`**: Mounts your MediaFire account as a standard local FUSE filesystem.
- **`mediafire-shell`**: An interactive FTP-like shell for navigating and managing files.

### Why the `+patched5` Patch is Essential

The unpatched 2015 upstream code suffers from several severe issues that make it unusable on modern Linux distributions or as a storage backend for backup utilities (such as `restic`):
1. **Mount-time crash (`SIGSEGV`):** Fails during `folder_tree_housekeep()` when trash items reference a missing parent folder.
2. **`fsync` / `fsyncdir` fatal error:** Upstream returned `-ENOSYS`, causing modern applications (e.g. `restic`) to abort immediately upon writing files.
3. **Mount freezes on HTTP stalls:** Missing curl transfer timeouts allowed a single hung API call to freeze the entire FUSE mount.
4. **Asynchronous upload / rename race:** Upstream deleted temporary file paths before upload completion, causing immediate `rename()` lookups to fail with `ENOENT`.
5. **Transient API errors:** Intermittent `file/update` and `folder/update` failures were not retried.
6. **Severe log bloat:** Full-tree debug dumps flooded stderr with ~7 MB of logs per run.
7. **Modern compiler rejection:** GCC 14/15 failed on 2015-era warnings due to `-Werror`.

The included `+patched5` release resolves all seven problems while maintaining full compatibility with the MediaFire API.

---

## 2. Directory Contents

| Artifact | Description |
| :--- | :--- |
| **`mediafire-tools_0.60+patched5_arm64.deb`** | Prebuilt binary package containing stripped `/usr/bin/mediafire-fuse` and `/usr/bin/mediafire-shell`. |
| **`mediafire-fuse-0.60+patched5.patch`** | Single unified patch (+262 / −91 across 5 files) against upstream commit `6b17698`. |
| **`mediafire-fuse-0.60+patched5/`** | Complete, clean source code tree with the patch already applied and ready to build. |
| **`mediafire-fuse-0.60+patched5-PATCHED-FILES.md`** | In-depth audit reference detailing every modified function and symbol. |

---

## 3. Quick Installation (Prebuilt `.deb`)

### Step 1: Install Dependencies

On Ubuntu 24.04 / 26.04:
```bash
sudo apt-get update
sudo apt-get install -y libfuse2t64 libjansson4 libssl3t64 libcurl4t64
```

*(On Ubuntu 20.04 / 22.04 or Debian, use `libfuse2 libjansson4 libssl3 libcurl4`)*

### Step 2: Install Package

```bash
sudo dpkg -i mediafire-tools_0.60+patched5_arm64.deb
```

Verify installation:
```bash
mediafire-fuse --version || true
which mediafire-fuse mediafire-shell
```

---

## 4. Configuration & Account Setup

`mediafire-fuse` and `mediafire-shell` read login credentials from `$XDG_CONFIG_HOME/mediafire-tools/config` (defaults to `~/.config/mediafire-tools/config`).

### Step 1: Create Secure Config Directory

```bash
mkdir -p ~/.config/mediafire-tools
chmod 700 ~/.config/mediafire-tools
```

### Step 2: Create Credentials File

Create `~/.config/mediafire-tools/config` with your account details:

```text
--username your_email@example.com
--password 'your_mediafire_password'
```

Secure the file so other users cannot read your credentials:
```bash
chmod 600 ~/.config/mediafire-tools/config
```

*(Note: You can also pass `--username` and `--password` via the command line or enter the password interactively when prompted, but using the config file mode `600` is recommended to avoid exposing credentials in process tables like `ps`.)*

---

## 5. Mounting & Usage

### 5.1 Mount MediaFire as Local Filesystem

```bash
# Create mountpoint directory in your home folder
mkdir -p ~/mediafire

# Mount in background
mediafire-fuse ~/mediafire

# Check mount status
ls -la ~/mediafire
```

### 5.2 Unmount Cleanly

```bash
fusermount3 -u ~/mediafire
# or on older FUSE versions:
# fusermount -u ~/mediafire
```

If the mount is busy or stale, force unmount with:
```bash
fusermount3 -uz ~/mediafire
```

### 5.3 Interactive Shell (`mediafire-shell`)

To browse and manage your account in an FTP-style CLI:
```bash
mediafire-shell
```

---

## 6. Local Cache & Troubleshooting

`mediafire-fuse` stores a local copy of your account folder tree in:
```text
~/.cache/mediafire-tools/<account-key>/directorytree
```

### Refreshing a Stale or Corrupted Cache

If remote files were added or removed from another client and do not appear locally, or if the mount hangs during initialization:

```bash
# 1. Unmount first
fusermount3 -u ~/mediafire 2>/dev/null || fusermount3 -uz ~/mediafire

# 2. Ensure daemon has terminated
pgrep -ax mediafire-fuse || echo "Daemon stopped"

# 3. Move old cache aside
mv ~/.cache/mediafire-tools ~/.cache/mediafire-tools.bak.$(date +%s)

# 4. Remount to pull a fresh directory tree from the MediaFire API
mediafire-fuse ~/mediafire
```

### Operational Tips & Caveats
- **Filesystem queries:** Do not rely on `stat -f` or `df` on the mountpoint; `statfs` is not implemented by the underlying upstream driver.
- **Large directory listings:** Avoid running coreutils `ls` on directories containing thousands of items simultaneously due to upstream readdir offset limits.
- **Security:** MediaFire API session tokens are generated during runtime. Never share FUSE debug logs publicly without scrubbing session tokens.

---

## 7. Compiling from Source

### Prerequisites

Install build essentials and library headers:
```bash
sudo apt-get update
sudo apt-get install -y build-essential cmake libfuse-dev libjansson-dev libssl-dev libcurl4-openssl-dev
```

### Option A: Build Using Bundled Patched Source

```bash
cd files_tools/mediafire-fuse/mediafire-fuse-0.60+patched5

# Configure with CMake (CMake >= 4 requires CMAKE_POLICY_VERSION_MINIMUM)
cmake -S . -B build \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_POLICY_VERSION_MINIMUM=3.5

# Compile binaries
cmake --build build --target mediafire-fuse mediafire-shell -j$(nproc)

# Strip debug symbols (optional, reduces binary size)
strip build/mediafire-fuse build/mediafire-shell

# Test run locally
./build/mediafire-fuse --help
```

### Option B: Build from Upstream Repository with Patch

```bash
git clone https://github.com/xorgy/mediafire-fuse
cd mediafire-fuse
git checkout 6b17698276a6ad56b97082cf9a263a8f28ca7ceb
git apply ../mediafire-fuse-0.60+patched5.patch

cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DCMAKE_POLICY_VERSION_MINIMUM=3.5
cmake --build build -j$(nproc)
```

---

## 8. Summary of Bug Fixes in `+patched5`

| # | Issue in Upstream 0.60 | Root Cause | Solution in `+patched5` | Source File |
| :--- | :--- | :--- | :--- | :--- |
| **1** | Mount crash (`SIGSEGV`) | `folder_tree_housekeep()` dereferences missing parent on trash items | Disabled housekeeping pass (safe for backup/mount workloads) | `fuse/hashtbl.c` |
| **2** | `fsync` / `fsyncdir` fatal error | Callbacks returned `-ENOSYS` | Returns `0` (success), enabling `restic` support | `fuse/operations.c` |
| **3** | Mount freezes on hung HTTP | Missing curl transfer limits | Set `CURLOPT_TIMEOUT` (900s data / 30s metadata) and low-speed abort | `utils/http.c` |
| **4** | Upload/rename race (`ENOENT`) | Temp file path unlinked before upload completion | Retains temp entry in `sv_writefiles` and reloads parent dir via `folder/get_content` | `fuse/operations.c`, `fuse/hashtbl.c` |
| **5** | Transient API failures | Sporadic MediaFire server errors | Added retry loop (20 × 5s) with automatic key re-resolution | `fuse/operations.c` |
| **6** | ~7 MB log bloat per run | Unconditional full-tree debug dumps | Removed debug dumps; replaced with targeted directory reloads | `fuse/hashtbl.c` |
| **7** | GCC 14/15 build failure | Modern warnings treated as errors | Dropped `-Werror` from compiler flags | `CMakeLists.txt` |
