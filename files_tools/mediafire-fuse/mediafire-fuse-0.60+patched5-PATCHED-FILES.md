# mediafire-tools 0.60+patched5 — patched-files reference

This documents **every source file the patch touches and exactly what is
changed in each**, so the patched tree can be audited without reading the raw
diff. The raw diff is the authoritative artifact:
`mediafire-fuse-0.60+patched5.patch`.

| | |
| --- | --- |
| Patch | `mediafire-fuse-0.60+patched5.patch` (sha256 `668af188ba305f0880b1a97c2cb40bf436e0783819ce1f3def7c0da450dabfe1`) |
| Upstream | <https://github.com/xorgy/mediafire-fuse> |
| Base commit | `6b17698276a6ad56b97082cf9a263a8f28ca7ceb` (2015-01-21) |
| Patch size | 5 files, **+262 / −91** |
| Patched source tree | `files_tools/mediafire-fuse/mediafire-fuse-0.60+patched5/` |

## Summary of patched files

| File | +/− | Patched symbols | What is patched |
| --- | --- | --- | --- |
| `CMakeLists.txt` | +1/−1 | (flags) | Drop `-Werror` so GCC 15 builds the 2015 code |
| `fuse/hashtbl.h` | +7 | declarations | Declare the two new tree helpers |
| `fuse/hashtbl.c` | +79/−? | `folder_tree_update`, **`folder_tree_reload_dir`** (new), **`folder_tree_rename_entry`** (new), `folder_tree_housekeep` | Disable the crashing housekeeping; add single-directory reload and in-place rename; remove the tree debug dumps |
| `fuse/operations.c` | +253/−? | `mediafirefs_mkdir`, `mediafirefs_release`, `mediafirefs_rename`, `mediafirefs_fsync`, `mediafirefs_fsyncdir` | Deterministic upload publication; async-release wait; API retries; make `fsync` succeed |
| `utils/http.c` | +12 | `http_curl_reset`, `http_get_buf` | Bound every libcurl transfer |

Per-file sha256 of the **patched** files:

```
903822859f07b75437c1de772e684c0a05cf4b4cd007ce85a7f42ca0304eeeda  CMakeLists.txt
7b18195c68da7fe3f7ba81cb759faf6fd5e67395f24434000f6faffa22651cf5  fuse/hashtbl.h
214c60bf3f4401035b56ab81329e0463a7a095c64cdbd96ac8b3656c0cbe4b2a  fuse/hashtbl.c
e56495fbc5590494a496bb404fb0d15f31a3c995f1232179ae0767488634cd2a  fuse/operations.c
7600fdbc56d2db559e4970426c433738902b9e669785ed7815e7c2c88effbc81  utils/http.c
```

---

## 1. `CMakeLists.txt`

- **Line 9.** `set(CMAKE_C_FLAGS "... -std=c99 -Wall -Werror")` →
  `set(CMAKE_C_FLAGS "... -std=c99 -Wall")`.
- **Why.** GCC 15 turns 2015-era warnings (`stringop-truncation`, `format`, …)
  into errors; `-Werror` aborts the build.

## 2. `fuse/hashtbl.h`

- **After line 37.** Two new prototypes:
  ```c
  int folder_tree_reload_dir(folder_tree * tree, mfconn * conn, const char *path);
  int folder_tree_rename_entry(folder_tree * tree, mfconn * conn,
                               const char *oldpath, const char *newpath);
  ```
- **Why.** Declare the reload and in-place-rename helpers added in `hashtbl.c`.

## 3. `fuse/hashtbl.c`

- **Line 42 — new include.** `#include <libgen.h>` (for `basename()` in
  `folder_tree_rename_entry()`).
- **`folder_tree_update()` (line 1415) — removed.** The two `folder_tree_debug()`
  calls that bracketed `folder_tree_housekeep()` (whole-tree dumps to stderr,
  ~7 MB per run) are deleted.
- **`folder_tree_reload_dir()` (new, line 1613).** Looks up `path`; rejects a
  missing entry (`-ENOENT`) or a non-directory (`-ENOTDIR`); calls
  `folder_tree_rebuild_helper()`, which issues `folder/get_content` for that
  one directory. This is the primitive that makes a freshly uploaded file
  visible deterministically.
- **`folder_tree_rename_entry()` (new, line 1635).** Looks up `oldpath` and
  overwrites its `name` with `basename(newpath)`. Used after a same-directory
  rename so the local tree stays correct without a full refresh.
- **`folder_tree_housekeep()` (line 1672) — disabled.** Adds `(void)tree;
  (void)conn; return;` at the top and wraps the original body in `#if 0 … #endif`.
  Avoids the `NULL`-parent dereference (SIGSEGV) on a trash item whose
  `parent_folderkey` has no matching folder.

## 4. `fuse/operations.c`

### `mediafirefs_mkdir()` (line 195)
- After `mfconn_api_folder_create()`, replaces the full
  `folder_tree_update(ctx->tree, ctx->conn, true)` with a targeted
  `folder_tree_reload_dir()` of the parent (`/` when `dirname` is empty).
- Frees `dirname` after use and also on the error path (`free(dirname)` added
  before the early `return -EAGAIN`).
- **Why.** Publishes the new folder immediately, so its key is available to a
  subsequent upload; avoids a heavy full-tree refresh.

### `mediafirefs_release()` (line 524) — the central fix
- **Keeps the temp path in `ctx->sv_writefiles` for the whole upload.** The old
  code deleted the entry *before* uploading and used a redundant duplicate
  check that called `exit(1)`; both are removed. `mediafirefs_getattr()` uses
  that vector to report a not-yet-published temp path as a regular file, so a
  `rename()` delivered during the upload still finds it.
- **Adds a `fdopen()` NULL check** (cleans up and returns `-EACCES`).
- **Consolidates error handling** under a new `local_error:` label, which frees
  `temp1`, `temp2`, `openfile->path`, `openfile`, removes the `sv_writefiles`
  entry, unlocks the mutex and returns `-EACCES`. Also frees `upload_key` on
  upload failure.
- **After a successful upload**, replaces `folder_tree_update(ctx->tree,
  ctx->conn, true)` with `folder_tree_reload_dir(ctx->tree, ctx->conn, dir_name)`
  (reload only the parent directory) before the mutex is released.
- **Removes the `sv_writefiles` entry on every exit path**, including the branch
  where the file already existed remotely (patch upload).

### `mediafirefs_rename()` (line 755)
- Keeps `strdup(oldpath)`/`strdup(newpath)` alive as `temp3`/`temp4` so
  `olddir`/`newdir` are valid for the wait loop and the final tree sync.
- **Wait loop for the async release.** While `folder_tree_path_get_key(oldpath)`
  is `NULL`, loops up to 300 × 200 ms (60 s), dropping `ctx->mutex` while
  sleeping; after ~5 s it forces one `folder_tree_reload_dir(ctx->tree,
  ctx->conn, olddir)`.
- **Fixed the directory check.** The old code tested `if (key == NULL)` after
  resolving `folderkey`; the patch tests `if (folderkey == NULL)` and logs
  `rename: new directory %s not found`.
- **Retries `file/update` / `folder/update`** 20 × 5 s, re-resolving the key
  from the tree each round.
- **Retries `file/move` / `folder/move`** 20 × 5 s when the destination
  directory differs.
- **Local tree sync without a full refresh.** Same directory →
  `folder_tree_rename_entry()`; different directory →
  `folder_tree_reload_dir()` of both `olddir` and `newdir`. Replaces the old
  `folder_tree_update(ctx->tree, ctx->conn, true)`.

### `mediafirefs_fsync()` (line 1018) and `mediafirefs_fsyncdir()` (line 1150)
- Return `0` instead of `-ENOSYS` (log message changed to “is a no-op”).
- **Why.** restic calls `fsync()` on every pack/index before rename and treats
  `-ENOSYS` as fatal. There is nothing to flush at this point — the upload
  happens in `release()`.

## 5. `utils/http.c`

- **`http_curl_reset()` (line 60) — added** (applies to every transfer):
  ```c
  curl_easy_setopt(conn->curl_handle, CURLOPT_LOW_SPEED_LIMIT, 1024L);
  curl_easy_setopt(conn->curl_handle, CURLOPT_LOW_SPEED_TIME, 60L);
  curl_easy_setopt(conn->curl_handle, CURLOPT_TIMEOUT, 900L);
  ```
- **`http_get_buf()` (line 140) — added** for metadata GETs:
  ```c
  curl_easy_setopt(conn->curl_handle, CURLOPT_TIMEOUT, 30L);
  ```
- **Why.** All FUSE operations are serialized behind one mutex, so a single
  stalled MediaFire call freezes the whole mount. Large pack transfers keep the
  generous 900 s cap plus a “below 1 KiB/s for 60 s” abort; metadata GETs are
  capped at 30 s.

---

## How to reproduce the patched tree

```bash
git clone https://github.com/xorgy/mediafire-fuse mediafire-fuse
cd mediafire-fuse
git checkout 6b17698276a6ad56b97082cf9a263a8f28ca7ceb
git apply ../mediafire-fuse-0.60+patched5.patch
```

See `README.md` for compilation and usage instructions.
