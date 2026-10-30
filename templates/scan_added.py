#!/usr/bin/env python3
"""Scan ADDED lines of a unified diff against `rule|regex` patterns (forbidden patterns and secret patterns).

Usage: scan_added.py --diff <diff file> --rules <patterns file> [--allow <allow file>]
- The diff holds `+++ b/<path>` headers and `+<line>` additions (git diff -U0 output; untracked files appended whole).
- Patterns file: one `rule|regex` per line (`#` comments and blank lines ignored). Regexes are POSIX-style ERE as the
  profiles write them; `[[:space:]]`-type classes are translated for Python. A rule name that starts with `~` matches
  CODE only: string literals, trailing `//` comments and whole-line comments are removed first, so `!` inside a message
  or a TODO-like word inside a comment does not trip it. Other rules match the raw line.
- Allow file: `path|rule|ruling` lines (the `~` is not part of the rule name). A hit on an allowed (path, rule) is ignored.
Prints `[rule] path: line` for every hit (at most 10 per rule) and exits 1 when anything was found, 0 otherwise.
"""
import argparse
import re
import sys

POSIX = {"[:space:]": r"\s", "[:alpha:]": "A-Za-z", "[:digit:]": "0-9", "[:alnum:]": "A-Za-z0-9",
         "[:upper:]": "A-Z", "[:lower:]": "a-z", "[:punct:]": r"!-/:-@\[-`{-~", "[:blank:]": r" \t"}
STRINGS = re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|`[^`]*`')
LINE_COMMENT = re.compile(r"//.*$|/\*.*?\*/")
COMMENT_START = ("//", "#", "*", "/*", "<!--")


def translate(regex: str) -> str:
    """Rewrite POSIX bracket classes so Python's re understands them."""
    for posix, python in POSIX.items():
        regex = regex.replace(posix, python)
    return regex


def read_lines(path):
    """Return the non-comment, non-blank lines of a text file (empty list when it is missing)."""
    if not path:
        return []
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return [l.rstrip("\n") for l in fh if l.strip() and not l.lstrip().startswith("#")]
    except OSError:
        return []


def load_rules(path):
    """Parse `rule|regex` lines into (name, code_only, compiled regex); a bad regex is reported and skipped."""
    rules = []
    for line in read_lines(path):
        name, _, regex = line.partition("|")
        code_only = name.startswith("~")
        try:
            rules.append((name.lstrip("~"), code_only, re.compile(translate(regex))))
        except re.error as err:
            print(f"[{name}] invalid regex ({err}): {regex}", file=sys.stderr)
    return rules


def code_only(line: str) -> str:
    """Strip string literals and comments from a source line; whole-line comments become empty."""
    if line.lstrip().startswith(COMMENT_START):
        return ""
    return LINE_COMMENT.sub("", STRINGS.sub('""', line))


def added_lines(diff_path):
    """Yield (path, line) for every added line of the diff."""
    path = "?"
    with open(diff_path, encoding="utf-8", errors="replace") as fh:
        for raw in fh:
            raw = raw.rstrip("\n")
            if raw.startswith("+++ b/"):
                path = raw[6:]
            elif raw.startswith("+++ /dev/null"):
                path = "?"
            elif raw.startswith("+"):  # a content line such as `+++i;` (source `++i;`) is NOT a header
                yield path, raw[1:]


def main() -> int:
    """Run every rule over every added line and print the hits."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--diff", required=True)
    ap.add_argument("--rules", required=True)
    ap.add_argument("--allow", default=None)
    args = ap.parse_args()
    rules = load_rules(args.rules)
    allowed = {tuple(l.split("|")[:2]) for l in read_lines(args.allow) if l.count("|") >= 1}
    hits = {}
    for path, line in added_lines(args.diff):
        stripped = None
        for name, only_code, regex in rules:
            if (path, name) in allowed:
                continue
            if only_code and stripped is None:
                stripped = code_only(line)
            if regex.search(stripped if only_code else line):
                hits.setdefault(name, []).append(f"{path}: {line.strip()[:160]}")
    for name, found in hits.items():
        print(f"[{name}]")
        for item in found[:10]:
            print(f"  {item}")
        if len(found) > 10:
            print(f"  … and {len(found) - 10} more")
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
