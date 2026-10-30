#!/usr/bin/env python3
"""Locale key parity for the es-orchestrator gate.

Usage: locale_parity.py "path/en.json,path/ar.json[,…]"
Reads .json, Flutter .arb ("@" metadata keys ignored), Java-style .properties and Apple .strings files, and fails when
- a file misses a key another file has, or holds an empty value;
- the same key uses different placeholders in different files ({name}, {}, {{name}}, %s, %d, %1$s, ${name}).
A single file is only checked for empty values. An empty file list exits 2 (a misconfigured LOCALE_FILES must not pass silently).
Exit 0 = parity, 1 = differences (printed), 2 = unreadable or unsupported file (YAML, .po and others are reported, not
skipped silently).
"""
import json
import re
import sys

PLACEHOLDER = re.compile(r"\{\{\s*\w+\s*\}\}|\$\{\s*\w+\s*\}|\{\w*\}|%\d*\$?[sdfi@]")
PROPERTIES_LINE = re.compile(r"^\s*([^#!=:\s][^=:]*?)\s*[=:]\s*(.*)$")
STRINGS_LINE = re.compile(r'^\s*"((?:\\.|[^"\\])*)"\s*=\s*"((?:\\.|[^"\\])*)"\s*;')


def flatten(node, prefix=""):
    """Return {dotted.key: value} for nested dicts; lists and scalars are leaves."""
    out = {}
    if isinstance(node, dict):
        for key, value in node.items():
            if key.startswith("@"):
                continue  # .arb metadata
            if isinstance(value, dict):
                out.update(flatten(value, f"{prefix}{key}."))
            else:
                out[f"{prefix}{key}"] = value
    return out


def parse_lines(text, pattern):
    """Parse `key = value` style files line by line (comments and blank lines are skipped)."""
    out = {}
    for line in text.splitlines():
        match = pattern.match(line)
        if match:
            out[match.group(1)] = match.group(2).strip()
    return out


def load(path):
    """Load and flatten one locale file, or exit 2 when it cannot be read or its format is unsupported."""
    suffix = path[path.rfind("."):].lower() if "." in path else ""
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        if suffix in (".json", ".arb"):
            return flatten(json.loads(text))
        if suffix == ".properties":
            return parse_lines(text, PROPERTIES_LINE)
        if suffix == ".strings":
            return parse_lines(text, STRINGS_LINE)
    except (OSError, ValueError) as err:
        print(f"cannot read {path}: {err}")
        sys.exit(2)
    print(f"unsupported locale format '{suffix}' for {path}: use .json/.arb/.properties/.strings or add a gate snippet")
    sys.exit(2)


def placeholders(value):
    """Return the sorted placeholder tokens of a string value (positional %1$s and %s compare as written)."""
    return sorted(PLACEHOLDER.findall(value)) if isinstance(value, str) else []


def main():
    """Compare every locale file against the union of keys and against each other's placeholders."""
    paths = [p.strip() for p in sys.argv[1].split(",") if p.strip()] if len(sys.argv) > 1 else []
    if not paths:
        print("LOCALE_FILES is empty: list the locale files, or set it to 'none'")
        return 2
    tables = {p: load(p) for p in paths}
    union = set().union(*[set(t) for t in tables.values()])
    bad = False
    for path, table in tables.items():
        missing = sorted(union - set(table))
        empty = sorted(k for k, v in table.items() if isinstance(v, str) and not v.strip())
        for key in missing:
            print(f"{path}: missing {key}")
        for key in empty:
            print(f"{path}: empty {key}")
        bad = bad or bool(missing or empty)
    reference, others = paths[0], paths[1:]
    for key in sorted(union):
        base = placeholders(tables[reference].get(key))
        for path in others:
            if key in tables[path] and key in tables[reference] and placeholders(tables[path][key]) != base:
                print(f"{path}: placeholders of {key} differ from {reference}: {placeholders(tables[path][key])} vs {base}")
                bad = True
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
