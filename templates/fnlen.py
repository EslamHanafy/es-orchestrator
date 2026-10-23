#!/usr/bin/env python3
"""Stack-agnostic function-length scanner for the es-orchestrator gate.

Reads source file paths on stdin (one per line) and prints "path:function:lines" for every function longer
than --max lines. Brace languages (C#, Java, Kotlin, Swift, Dart, TS/JS, Go, Rust, C/C++, PHP) are measured by
brace matching from the signature line; Python by indentation. It is a heuristic: string/comment braces are
stripped first, and anything it cannot classify is ignored rather than guessed. Replace it with a real AST
scanner when the stack has one (see profiles/<stack>/gate-hooks.md).
"""
import argparse
import re
import sys

BRACE_EXT = {".cs", ".java", ".kt", ".kts", ".swift", ".dart", ".ts", ".tsx", ".js", ".jsx", ".mjs",
             ".go", ".rs", ".c", ".cc", ".cpp", ".h", ".hpp", ".m", ".mm", ".php", ".scala"}
KEYWORDS = {"if", "for", "foreach", "while", "switch", "catch", "using", "lock", "return", "else", "do",
            "try", "finally", "when", "match", "guard", "defer", "new", "class", "struct", "interface",
            "enum", "record", "namespace", "extension", "mixin", "object", "impl", "trait", "module"}
SIG = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\s*(<[^>{}]*>)?\s*\(")
STRIP = re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|`[^`]*`|//.*$')


def strip_line(line: str) -> str:
    """Remove string literals and line comments so their braces are not counted."""
    return STRIP.sub("", line)


def brace_functions(lines):
    """Yield (name, length) for brace-delimited functions found by signature + brace matching."""
    clean = [strip_line(l) for l in lines]
    i = 0
    while i < len(clean):
        m = SIG.search(clean[i])
        name = m.group(1) if m else None
        if name and name not in KEYWORDS:
            # Find the opening brace of the body within the next few lines (multi-line signatures).
            for j in range(i, min(i + 8, len(clean))):
                if ";" in clean[j] and "{" not in clean[j]:
                    break
                if "{" in clean[j]:
                    depth, k = 0, j
                    while k < len(clean):
                        depth += clean[k].count("{") - clean[k].count("}")
                        if depth <= 0:
                            break
                        k += 1
                    yield name, k - i + 1
                    i = j  # continue inside the body so nested local functions are seen too
                    break
        i += 1


def python_functions(lines):
    """Yield (name, length) for Python defs measured by indentation."""
    defs = re.compile(r"^(\s*)(?:async\s+)?def\s+([A-Za-z_][A-Za-z0-9_]*)")
    for i, line in enumerate(lines):
        m = defs.match(line)
        if not m:
            continue
        indent, end = len(m.group(1)), i
        for k in range(i + 1, len(lines)):
            text = lines[k]
            if text.strip() and (len(text) - len(text.lstrip())) <= indent:
                break
            if text.strip():
                end = k
        yield m.group(2), end - i + 1


def scan(path: str, limit: int):
    """Print every function of one file over the limit."""
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            lines = fh.read().splitlines()
    except OSError:
        return
    ext = path[path.rfind("."):] if "." in path else ""
    if ext == ".py":
        found = python_functions(lines)
    elif ext in BRACE_EXT:
        found = brace_functions(lines)
    else:
        return
    seen = set()
    for name, length in found:
        if length > limit and (name, length) not in seen:
            seen.add((name, length))
            print(f"{path}:{name}:{length}")


def main():
    """Entry point: paths on stdin, findings on stdout."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--max", type=int, required=True, help="maximum lines per function")
    args = parser.parse_args()
    for raw in sys.stdin:
        path = raw.strip()
        if path:
            scan(path, args.max)


if __name__ == "__main__":
    main()
