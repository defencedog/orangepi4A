#!/usr/bin/python3
"""Small, line-preserving editor for Falkon's QSettings INI files.

Falkon stores its configuration in Qt's INI format.  Rewriting the whole file
with configparser would drop Qt-specific escapes and reorder keys, so this
helper only touches the requested key and leaves every other byte/line alone.

Usage examples:
    falkon_ini.py get settings.ini "Plugin-Settings" AllowedPlugins
    falkon_ini.py set settings.ini "Plugin-Settings" AllowedPlugins "internal:adblock"
    falkon_ini.py add-list settings.ini "Plugin-Settings" AllowedPlugins "lib:GreaseMonkey.so"
    falkon_ini.py set-bool extensions.ini GreaseMonkey enabled true
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _read(path: Path) -> list[str]:
    # newline='' keeps CRLF as-is; splitlines() removes the line endings and
    # _write() re-joins with the file's dominant newline.
    with path.open("r", encoding="utf-8", newline="") as fh:
        return fh.read().splitlines()


def _newline_for(path: Path) -> str:
    with path.open("rb") as fh:
        data = fh.read(4096)
    return "\r\n" if b"\r\n" in data else "\n"


def _write(path: Path, lines: list[str]) -> None:
    nl = _newline_for(path)
    with path.open("w", encoding="utf-8", newline="") as fh:
        fh.write(nl.join(lines))
        if lines:
            fh.write(nl)


def _section_bounds(lines: list[str], section: str) -> tuple[int, int]:
    header = f"[{section}]"
    start = None
    for i, line in enumerate(lines):
        if line.strip() == header:
            start = i
            break
    if start is None:
        lines.append("")
        lines.append(header)
        start = len(lines) - 1

    end = len(lines)
    for i in range(start + 1, len(lines)):
        stripped = lines[i].strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            end = i
            break
    return start, end


def get_value(path: Path, section: str, key: str) -> str | None:
    lines = _read(path)
    start, end = _section_bounds(lines, section)
    prefix = f"{key}="
    for line in lines[start + 1:end]:
        if line.startswith(prefix):
            return line[len(prefix):]
    return None


def set_value(path: Path, section: str, key: str, value: str) -> tuple[str | None, str]:
    lines = _read(path)
    start, end = _section_bounds(lines, section)
    prefix = f"{key}="
    old = None
    replaced = False
    for i in range(start + 1, end):
        if lines[i].startswith(prefix):
            old = lines[i][len(prefix):]
            lines[i] = prefix + value
            replaced = True
            break
    if not replaced:
        lines.insert(end, prefix + value)
    _write(path, lines)
    return old, value


def add_list_item(path: Path, section: str, key: str, item: str) -> str:
    current = get_value(path, section, key) or ""
    items = [part.strip() for part in current.split(",") if part.strip()]
    if items == ["@Invalid()"]:
        items = []
    if item not in items:
        items.append(item)
    value = ", ".join(items)
    set_value(path, section, key, value)
    return value


def remove_list_item(path: Path, section: str, key: str, item: str) -> str:
    current = get_value(path, section, key) or ""
    items = [part.strip() for part in current.split(",") if part.strip()]
    items = [part for part in items if part != item and part != "@Invalid()"]
    value = ", ".join(items)
    set_value(path, section, key, value)
    return value


def delete_key(path: Path, section: str, key: str) -> bool:
    lines = _read(path)
    start, end = _section_bounds(lines, section)
    prefix = f"{key}="
    new_lines = []
    removed = False
    for i, line in enumerate(lines):
        if start < i < end and line.startswith(prefix):
            removed = True
            continue
        new_lines.append(line)
    _write(path, new_lines)
    return removed


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    p_get = sub.add_parser("get")
    p_get.add_argument("path")
    p_get.add_argument("section")
    p_get.add_argument("key")

    for name in ("set", "add-list", "remove-list"):
        p = sub.add_parser(name)
        p.add_argument("path")
        p.add_argument("section")
        p.add_argument("key")
        p.add_argument("value")

    p_bool = sub.add_parser("set-bool")
    p_bool.add_argument("path")
    p_bool.add_argument("section")
    p_bool.add_argument("key")
    p_bool.add_argument("value", choices=["true", "false", "1", "0"])

    p_delete = sub.add_parser("delete")
    p_delete.add_argument("path")
    p_delete.add_argument("section")
    p_delete.add_argument("key")

    args = parser.parse_args()
    path = Path(args.path).expanduser()

    if args.command == "get":
        value = get_value(path, args.section, args.key)
        if value is None:
            return 1
        print(value)
        return 0

    if args.command == "delete":
        removed = delete_key(path, args.section, args.key)
        print(f"{args.section}/{args.key}: {'deleted' if removed else 'not present'}")
        return 0

    if args.command == "set":
        old, new = set_value(path, args.section, args.key, args.value)
        print(f"{args.section}/{args.key}: {old!r} -> {new!r}")
        return 0

    if args.command == "add-list":
        new = add_list_item(path, args.section, args.key, args.value)
        print(f"{args.section}/{args.key}: {new!r}")
        return 0

    if args.command == "remove-list":
        new = remove_list_item(path, args.section, args.key, args.value)
        print(f"{args.section}/{args.key}: {new!r}")
        return 0

    if args.command == "set-bool":
        value = "true" if args.value in ("true", "1") else "false"
        old, new = set_value(path, args.section, args.key, value)
        print(f"{args.section}/{args.key}: {old!r} -> {new!r}")
        return 0

    return 2


if __name__ == "__main__":
    sys.exit(main())
