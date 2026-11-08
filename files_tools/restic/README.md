# Restic / Rustic MediaFire Cloud Backup Suite

Automated, encrypted, and deduplicated backup suite for Orange Pi 4A (and other Linux hosts) backing up local directories directly to a [MediaFire](https://www.mediafire.com/) cloud storage account via FUSE (`mediafire-fuse`).

---

## 1. Overview & Architecture

This backup suite uses **[restic](https://restic.net/)** (or its fast Rust counterpart **`rustic`**) to perform client-side encrypted, compressed, and deduplicated backups. 

Data is encrypted locally *before* being written to the FUSE mount at `/media/mediafire/backup`. MediaFire only receives opaque, encrypted pack blobs—it never sees plaintext files or filenames.

```text
  Local Directories
  ├── /home/user/Documents ──┐
  ├── /home/user/projects  ──┼──► restic / rustic (encrypt + compress + dedupe)
  └── /home/user/...       ──┘             │
                                           ▼
                             /media/mediafire/backup
                             (fuse.mediafire-fuse)
                                           │  MediaFire REST API
                                           ▼
                                 MediaFire Cloud Storage
```

---

## 2. Prerequisites

### 1. Install `restic` (or `rustic`)
`restic` is available in standard Ubuntu / Debian repositories:
```bash
sudo apt update
sudo apt install restic
```
*(Optional)* If you prefer **`rustic`** (the fast Rust client), it is fully compatible with the exact same repository format and commands.

### 2. Install Patched `mediafire-tools`
The stock `mediafire-fuse` daemon crashes on `fsync` and suffers from race conditions during file renames. You must install the patched binary (`0.60+patched5`) provided in [**`files_tools/mediafire-fuse`**](../mediafire-fuse/):
```bash
sudo apt install /path/to/files_tools/mediafire-fuse/mediafire-tools_0.60+patched5_arm64.deb
```

### 3. Configure MediaFire Credentials
Create your MediaFire authentication file at `~/.config/mediafire-tools/config`:
```ini
--username your_email@example.com
--password your_mediafire_password
```
Ensure safe permissions:
```bash
chmod 600 ~/.config/mediafire-tools/config
```

---

## 3. Configuration

Open [`restic-mediafire-backup.sh`](restic-mediafire-backup.sh) to configure your paths and settings:

### A. Add or Modify Local Directories to Back Up
In the `SOURCES=( ... )` array, specify the directories you want to include:
```bash
SOURCES=(
    "$HOME/Documents"
    "$HOME/projects"
    "/home/ukhan/claude_ukhan"
    "/home/ukhan/gemini"
)
```

### B. Configure Repository Encryption Password
Restic uses symmetric client-side encryption. **If you lose this password, your backup data cannot be decrypted or recovered.**

You can configure the password in either of two ways:
1. **Via Environment Variable (Recommended for security):**
   ```bash
   export RESTIC_PASSWORD="YourStrongSecurePasswordHere"
   ```
2. **Directly inside the script:**
   Edit line 58 of `restic-mediafire-backup.sh`:
   ```bash
   export RESTIC_PASSWORD="${RESTIC_PASSWORD:-YourStrongSecurePasswordHere}"
   ```
   *Note: Always keep the script set to `chmod 700` if storing the password inside it.*

### C. FUSE Mount & Repository Paths
The script defaults to mounting MediaFire at `/media/mediafire` and locating the repository under `/media/mediafire/backup`:
```bash
MOUNT="/media/mediafire"
REPO="/media/mediafire/backup"
```

---

## 4. One-Time Repository Initialization (`restic init`)

Before running automated backups, initialize the repository on MediaFire once.

### Step 1: Mount MediaFire
```bash
mkdir -p /media/mediafire
nohup /usr/bin/mediafire-fuse -f /media/mediafire > /tmp/mf-init.log 2>&1 &
sleep 5
timeout 10 ls /media/mediafire
```

### Step 2: Pre-create Layout (Recommended)
Because creating 256 individual subdirectories through FUSE can trigger API rate-limits and stalls, pre-create the `data/00` to `data/ff` structure using `mediafire-shell`:
```bash
mediafire-shell -c 'mkdir backup'
# Navigate to the backup directory and create metadata folders:
mediafire-shell -c 'cd backup; mkdir data; mkdir index; mkdir keys; mkdir locks; mkdir snapshots'
```

### Step 3: Initialize Restic
```bash
export RESTIC_REPOSITORY="/media/mediafire/backup"
export RESTIC_PASSWORD="YourStrongSecurePasswordHere"

restic init
```
This writes the encrypted `config` file and master keys.

---

## 5. How to Back Up

Make the backup script executable:
```bash
chmod 700 restic-mediafire-backup.sh
```

### Standard Backup Run
```bash
./restic-mediafire-backup.sh
```
* **What it does**:
  1. Checks and locks with `flock` to prevent concurrent backups.
  2. Verifies `/media/mediafire` mount health; auto-mounts via `mediafire-fuse` if unmounted.
  3. Verifies repository readability.
  4. Runs incremental backup with `--skip-if-unchanged` and `--one-file-system`.
  5. Scans FUSE logs for any network/API transmission errors.
  6. Runs a metadata integrity check (`restic check`).

### Deep Data Verification Run
To verify 10% of the actual encrypted pack payload data over the cloud mount:
```bash
./restic-mediafire-backup.sh --verify-data
```

### Backup + Pruning Old Snapshots
To apply the retention policy (`7 daily, 4 weekly, 6 monthly`) and clean unreferenced pack files:
```bash
./restic-mediafire-backup.sh --prune
```

### Automated Daily Scheduling (Cron)
Add a crontab entry (`crontab -e`):
```cron
# Run backup every night at 3:15 AM
15 3 * * * RESTIC_PASSWORD="YourPassword" /home/ukhan/orangepi4A/files_tools/restic/restic-mediafire-backup.sh >> /home/ukhan/.local/state/restic-mediafire/cron.log 2>&1
```

---

## 6. How to Restore

Restoring files from the MediaFire repository can be done at any time on any Linux machine with `restic` and `mediafire-tools` installed.

### Step 1: Ensure Mount is Active
```bash
mountpoint -q /media/mediafire || nohup /usr/bin/mediafire-fuse /media/mediafire > /tmp/mf-restore.log 2>&1 &
sleep 5
```

### Step 2: Set Credentials
```bash
export RESTIC_REPOSITORY="/media/mediafire/backup"
export RESTIC_PASSWORD="YourStrongSecurePasswordHere"
```

### Step 3: List Available Snapshots
```bash
restic snapshots --tag mediafire
```
Output example:
```text
ID        Time                 Host          Tags        Paths
---------------------------------------------------------------------------------
eb7854bc  2026-11-08 22:42:47  orangepi-4a   mediafire   /home/ukhan/gemini, ...
```

### Step 4: Restore Latest Snapshot
Restore the entire snapshot to a destination folder (e.g. `/tmp/restored`):
```bash
mkdir -p /tmp/restored
restic restore latest --target /tmp/restored --tag mediafire
```

### Step 5: Restore Specific Files or Subdirectories
If you only need a single file or project folder:
```bash
restic restore latest \
    --target /tmp/restored \
    --include "/home/ukhan/gemini/important-project"
```

### Step 6: Verify Restore Integrity
Compare the restored files with the original local files:
```bash
diff -r /home/ukhan/gemini/important-project /tmp/restored/home/ukhan/gemini/important-project
# Returns 0 if files are bit-for-bit identical!
```

---

## 7. Using `rustic` as an Alternative Engine

`rustic` is a fast client written in Rust that implements the restic repository specification. It uses the exact same command parameters and format.

To run the backup script using `rustic` instead of `restic`:
```bash
RESTIC_BIN=rustic ./restic-mediafire-backup.sh
```

---

## 8. Troubleshooting & Operational Notes

1. **Mount Health Checks**:
   * **Do not use** `df` or `stat -f /media/mediafire`. The FUSE implementation does not support `statfs` and will return an error even when healthy.
   * Always check mount responsiveness with:
     ```bash
     mountpoint -q /media/mediafire && timeout 10 ls /media/mediafire
     ```
2. **Directory Listing Stalls on `data/`**:
   * The `data/` folder contains 256 subdirectories. Standard `ls` can hang due to readdir cookie limitations. Let restic handle internal path traversals directly.
3. **Session Tokens in Logs**:
   * `mediafire-fuse` logs signed HTTP URLs containing temporary session tokens in `~/.local/state/restic-mediafire/fuse.log`.
   * The log is created with permissions `0600`. Delete it after troubleshooting:
     ```bash
     rm -f ~/.local/state/restic-mediafire/fuse.log
     ```
