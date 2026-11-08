# Files, Tools & Prebuilt Packages for Orange Pi 4A (Ubuntu Jammy & Newer)

## 1. MediaFire FUSE & Shell Tools (`mediafire-fuse`)
Production FUSE filesystem driver and interactive shell for MediaFire cloud storage on ARM64 (`mediafire-tools_0.60+patched5_arm64.deb`).
- **Directory:** [`./mediafire-fuse/`](./mediafire-fuse/)
- **Features:** Complete aarch64 deb artifact, unified patch (`mediafire-fuse-0.60+patched5.patch`), patched source tree, and full documentation on mounting MediaFire storage (including support for `restic` backups).
- **Documentation:** See [`mediafire-fuse/README.md`](./mediafire-fuse/README.md).

---

## 2. Glide Hardware-Accelerated Media Player (`glide`)
Modern GStreamer + GTK4 + Rust media player featuring Cedar VPU hardware decoding for H.264, HEVC / H.265, and VP9.
- **Directory:** [`./glide/`](./glide/)
- **Features:** Prebuilt aarch64 deb package (`glide_0.6.9_arm64.deb`), real-time VPU telemetry support in `opi-mon`, and patch resolving Wayland window-sizing behavior (`glide_bug/`).
- **Documentation:** See [`glide/README.md`](./glide/README.md) and [`glide/GLIDE-VPU.md`](./glide/GLIDE-VPU.md).

---

## 3. Flow-Desktop YouTube Player with Clapper VPU Integration (`flow`)
Privacy-first desktop client for YouTube (Tauri 2 + React) patched to delegate video playback to Clapper for Cedar VPU hardware acceleration (`Flow_0.1.0-beta3_arm64.deb`).
- **Directory:** [`./flow/`](./flow/)
- **Features:** Prebuilt arm64 deb, Rust Tauri backend patch (`patch-flow-clapper.py`), React settings schema, and test automation scripts.
- **Documentation:** See [`flow/README.md`](./flow/README.md) and [`flow/FLOW-VPU-CLAPPER-INTEGRATION.md`](./flow/FLOW-VPU-CLAPPER-INTEGRATION.md).

---

## 4. FreeTube YouTube Player with Clapper VPU Integration (`freetube`)
Feature-rich, private desktop YouTube player (Electron 44 / ARM64) configured to launch Clapper for Cedar hardware VPU decoding (`freetube_0.26.0_beta_arm64.deb`).
- **Directory:** [`./freetube/`](./freetube/)
- **Features:** Prebuilt arm64 deb package, single-representation DASH stream optimization scripts (`clapper_yt_dlp_dash.py`, `clapper_yt_dlp_overrides.py`), and setup guide.
- **Documentation:** See [`freetube/README.md`](./freetube/README.md) and [`freetube/freetube-patch.md`](./freetube/freetube-patch.md).

---

## 5. Restic / Rustic MediaFire Cloud Backup Suite (`restic`)
Automated, client-side encrypted, deduplicated cloud backup suite using `restic` (or `rustic`) to backup local directories directly to MediaFire cloud storage mounted via `mediafire-fuse` at `/media/mediafire/backup`.
- **Directory:** [`./restic/`](./restic/) (also symlinked as [`./rustic/`](./rustic/))
- **Features:** Automated mount-aware backup script (`restic-mediafire-backup.sh`), integrity verification (`--verify-data`), retention policy & pruning (`--prune`), full restore instructions, and deep technical plan (`restic-mediafire-plan.json`).
- **Engine Support:** Uses standard `restic` from Ubuntu default repos (`sudo apt install restic`), with full drop-in compatibility for `rustic-rs`.
- **Documentation:** See [`restic/README.md`](./restic/README.md).

---

## 6. SQLiteStudio for ARM64 (`SQLiteStudio-3.4.17`)
Desktop database manager for SQLite on Ubuntu ARM64:
- Main repository: [john-black-3k/sqlitestudio-linux-arm64](https://github.com/john-black-3k/sqlitestudio-linux-arm64)

### Extraction & Installation
```bash
# Extract multi-volume 7z archive
7z x SQLiteStudio-3.4.17.7z.001

# Install runtime dependencies
sudo apt install -y libsqlite3-dev libxcb-cursor0

# Configure desktop launcher
# Edit sqlitestudio.desktop with appropriate path, then:
gio launch sqlitestudio.desktop # verify it runs
sudo cp sqlitestudio.desktop /usr/local/share/applications/
```
