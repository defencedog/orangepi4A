# Files, Tools & Prebuilt Packages for Orange Pi 4A (Ubuntu Jammy & Newer)

## 1. MediaFire FUSE & Shell Tools (`mediafire-fuse`)
Production FUSE filesystem driver and interactive shell for MediaFire cloud storage on ARM64 (`mediafire-tools_0.60+patched5_arm64.deb`).
- **Directory:** [`./mediafire-fuse/`](./mediafire-fuse/)
- **Features:** Complete aarch64 deb artifact, unified patch (`mediafire-fuse-0.60+patched5.patch`), patched source tree, and full documentation on mounting MediaFire storage (including support for `restic` backups).
- **Documentation:** See [`mediafire-fuse/README.md`](./mediafire-fuse/README.md).

---

## 2. SQLiteStudio for ARM64 (`SQLiteStudio-3.4.17`)
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
