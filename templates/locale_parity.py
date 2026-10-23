#!/usr/bin/env python3
"""Locale key parity for the es-orchestrator gate.

Usage: locale_parity.py "path/en.json,path/ar.json[,…]"
Flattens nested JSON (and Flutter .arb, ignoring "@" metadata keys) and fails when any file misses a key another
file has, or holds an empty value. Exit 0 = parity, 1 = differences (printed), 2 = unreadable file.
"""
import json
import sys


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


def load(path):
    """Load and flatten one locale file, or exit 2 when it cannot be read."""
    try:
        with open(path, encoding="utf-8") as fh:
            return flatten(json.load(fh))
    except (OSError, ValueError) as err:
        print(f"cannot read {path}: {err}")
        sys.exit(2)


def main():
    """Compare every locale file against the union of keys."""
    paths = [p.strip() for p in sys.argv[1].split(",") if p.strip()] if len(sys.argv) > 1 else []
    if len(paths) < 2:
        print("need at least two locale files")
        return 0
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
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
