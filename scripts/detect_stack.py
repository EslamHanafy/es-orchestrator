#!/usr/bin/env python3
"""Detect a repo's stack(s) for es-orchestrator setup and print suggested answers.json values as JSON.

Usage: detect_stack.py <repo root>
It scans up to three levels deep for build markers (pubspec.yaml, package.json, *.csproj, go.mod, …), maps each to
a profile (backend / mobile / web) with suggested gate commands, and also reports locale files, rules files, plan
candidates and test folders. Everything it prints is a SUGGESTION: the owner confirms or overrides it.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

SKIP_DIRS = {".git", "node_modules", "build", "dist", "bin", "obj", ".dart_tool", ".gradle", "Pods", ".venv",
             "venv", "__pycache__", ".superpowers", ".idea", ".vscode", "coverage", "target"}
NODE_MOBILE = ("react-native", "expo")
NODE_WEB = ("@angular/core", "react", "vue", "next", "svelte", "nuxt", "solid-js")
NODE_BACKEND = ("express", "@nestjs/core", "fastify", "koa", "hono")
PY_BACKEND = ("django", "fastapi", "flask", "starlette")


def walk(root: Path, depth: int = 3):
    """Yield files up to `depth` directory levels below root, skipping vendor/build folders."""
    stack = [(root, 0)]
    while stack:
        folder, level = stack.pop()
        try:
            entries = list(folder.iterdir())
        except OSError:
            continue
        for entry in entries:
            if entry.is_dir() and entry.name not in SKIP_DIRS and level < depth:
                stack.append((entry, level + 1))
            elif entry.is_file():
                yield entry


def rel(root: Path, path: Path) -> str:
    """Return a repo-relative path ('.' for the root itself)."""
    text = str(path.relative_to(root))
    return text if text else "."


def node_stack(pkg: Path):
    """Classify a package.json as mobile, web or backend, with npm-script based commands."""
    try:
        data = json.loads(pkg.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
    scripts = data.get("scripts", {})
    kind = "mobile" if any(d in deps for d in NODE_MOBILE) else \
        "web" if any(d in deps for d in NODE_WEB) else "backend" if any(d in deps for d in NODE_BACKEND) else None
    if not kind:
        return None
    run = lambda name, fallback: f"npm run {name}" if name in scripts else fallback
    return kind, {"BUILD_CMD": run("build", "none"), "LINT_CMD": run("lint", "npx eslint ."),
                  "FORMAT_CHECK": "npx prettier --check", "TEST_CMD": run("test", "none")}


def classify(root: Path, f: Path):
    """Map one marker file to (profile, tool, suggested commands) or None."""
    name, folder = f.name, rel(root, f.parent)
    if name == "pubspec.yaml":
        return "mobile", "flutter", {"BUILD_CMD": "none", "LINT_CMD": "flutter analyze",
                                     "FORMAT_CHECK": "dart format --output=none --set-exit-if-changed",
                                     "TEST_CMD": "flutter test", "SRC_PATTERN": "^lib/.*\\.dart$"}
    if name == "package.json":
        found = node_stack(f)
        return (found[0], "node", found[1]) if found else None
    if name.endswith((".sln", ".csproj")) and not re.search(r"(Test|Tests)\.csproj$", name):
        return "backend", "dotnet", {"BUILD_CMD": f"dotnet build {folder} --no-incremental",
                                     "LINT_CMD": "dotnet format style --verify-no-changes", "TEST_CMD": "dotnet test",
                                     "MIGRATIONS_GLOB": "**/Migrations/**"}
    if name == "go.mod":
        return "backend", "go", {"BUILD_CMD": "go build ./...", "LINT_CMD": "golangci-lint run",
                                 "FORMAT_CHECK": "gofmt -l", "TEST_CMD": "go test ./..."}
    if name in ("build.gradle", "build.gradle.kts"):
        android = "com.android" in f.read_text(encoding="utf-8", errors="ignore")
        return ("mobile" if android else "backend"), "gradle", {"BUILD_CMD": "./gradlew assemble",
                                                                "TEST_CMD": "./gradlew test"}
    if name == "pom.xml":
        return "backend", "maven", {"BUILD_CMD": "mvn -q compile", "TEST_CMD": "mvn -q test"}
    if name in ("pyproject.toml", "requirements.txt"):
        text = f.read_text(encoding="utf-8", errors="ignore").lower()
        if any(p in text for p in PY_BACKEND):
            return "backend", "python", {"LINT_CMD": "ruff check .", "FORMAT_CHECK": "ruff format --check",
                                         "TEST_CMD": "pytest -q"}
    if name == "Gemfile" and "rails" in f.read_text(encoding="utf-8", errors="ignore"):
        return "backend", "rails", {"TEST_CMD": "bin/rails test", "MIGRATIONS_GLOB": "db/migrate/**"}
    if name == "Cargo.toml":
        return "backend", "rust", {"BUILD_CMD": "cargo build", "LINT_CMD": "cargo clippy -- -D warnings",
                                   "TEST_CMD": "cargo test"}
    if name.endswith(".xcodeproj") or name == "Package.swift":
        return "mobile", "swift", {"LINT_CMD": "swiftlint"}
    return None


def collapse(stacks: list) -> list:
    """Drop a stack nested under another stack of the same tool and profile (e.g. projects under a solution)."""
    def nested(inner, outer):
        return (inner is not outer and inner["tool"] == outer["tool"] and inner["profile"] == outer["profile"]
                and (outer["root"] == "." or inner["root"].startswith(outer["root"] + "/")))
    def platform_shell(inner):
        # android/ and ios/ folders of a cross-platform app belong to that app, not to a second stack.
        for app in stacks:
            if app["tool"] in ("flutter", "node") and app["profile"] == "mobile":
                base = "" if app["root"] == "." else app["root"] + "/"
                if re.match(rf"^{re.escape(base)}(android|ios|macos)(/|$)", inner["root"]):
                    return True
        return False
    return [s for s in stacks if not any(nested(s, o) for o in stacks) and not platform_shell(s)]


def git_default_branch(root: Path) -> str:
    """Best-effort current branch name."""
    out = subprocess.run(["git", "-C", str(root), "branch", "--show-current"], capture_output=True, text=True)
    return out.stdout.strip() or "main"


def main():
    """Scan the repo and print the suggestions as JSON."""
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    stacks, locales, rules, plans, tests = [], [], [], [], set()
    for f in walk(root):
        hit = classify(root, f)
        if hit:
            stacks.append({"profile": hit[0], "tool": hit[1], "root": rel(root, f.parent), "commands": hit[2]})
        low = str(f.relative_to(root)).lower()
        if re.search(r"(i18n|l10n|lang|languages|locales?|translations)/[^/]*\.(json|arb)$", low):
            locales.append(rel(root, f))
        if f.name in ("AGENTS.md", "CLAUDE.md", "CONTRIBUTING.md", "GEMINI.md"):
            rules.append(rel(root, f))
        if f.suffix == ".md" and re.search(r"plan|roadmap|spec", f.name.lower()) and "docs" in low:
            plans.append(rel(root, f))
        if f.parent.name in ("test", "tests", "__tests__", "spec"):
            tests.add(rel(root, f.parent))
    stacks = collapse(stacks)
    profiles = list(dict.fromkeys(s["profile"] for s in stacks)) or ["generic"]
    print(json.dumps({"PROFILES": profiles, "stacks": stacks, "LOCALE_FILES": ",".join(sorted(locales)) or "none",
                      "RULES_FILES": ", ".join(sorted(rules)) or "none", "plan_candidates": sorted(plans),
                      "TEST_DIRS": " ".join(sorted(tests)) or "none", "BASE_BRANCH": git_default_branch(root),
                      "monorepo": len({s["root"] for s in stacks}) > 1}, indent=2))


if __name__ == "__main__":
    main()
