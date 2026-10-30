#!/usr/bin/env python3
"""Detect a repo's stack(s) for es-orchestrator setup and print suggested answers.json values as JSON.

Usage: detect_stack.py <repo root> [--draft-answers]
With --draft-answers it prints a complete answers.json draft instead (see references/answers-schema.md): every value
detection can fill, safe defaults for the rest, and `_confirm` notes listing what the owner should check. This is the
"quick setup" path.
It scans up to three levels deep for build markers (pubspec.yaml, package.json, *.csproj, go.mod, …), maps each to
a profile (backend / mobile / web) with suggested gate commands, and also reports locale files, rules files, plan
candidates and test folders. Everything it prints is a SUGGESTION: the owner confirms or overrides it.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

DELEGATE_DIRS = (Path.home() / ".claude" / "skills", Path.home() / ".agents" / "skills")

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
            if entry.is_dir() and entry.name.endswith(".xcodeproj"):
                yield entry  # an Xcode project is a folder; report it as a marker, do not descend
            elif entry.is_dir() and entry.name not in SKIP_DIRS and level < depth:
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
    install = "npm ci" if (pkg.parent / "package-lock.json").exists() else "npm install"
    return kind, {"BUILD_CMD": run("build", "none"), "LINT_CMD": run("lint", "npx eslint ."),
                  "FORMAT_CHECK": "npx prettier --check", "TEST_CMD": run("test", "none"),
                  "WORKTREE_SETUP_CMD": install}


def classify(root: Path, f: Path):
    """Map one marker file to (profile, tool, suggested commands) or None."""
    name, folder = f.name, rel(root, f.parent)
    if name == "pubspec.yaml":
        format_check = "dart format --output=none --set-exit-if-changed"
        if not re.search(r"sdk:\s*flutter", f.read_text(encoding="utf-8", errors="ignore")):
            # A plain Dart package or server: not a mobile app, so it uses the generic profile.
            return "generic", "dart", {"LINT_CMD": "dart analyze", "FORMAT_CHECK": format_check,
                                       "TEST_CMD": "dart test", "SRC_PATTERN": "^(lib|bin)/.*\\.dart$",
                                       "WORKTREE_SETUP_CMD": "dart pub get"}
        return "mobile", "flutter", {"BUILD_CMD": "none", "LINT_CMD": "flutter analyze", "FORMAT_CHECK": format_check,
                                     "TEST_CMD": "flutter test", "SRC_PATTERN": "^lib/.*\\.dart$",
                                     "WORKTREE_SETUP_CMD": "flutter pub get"}
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
    if name.endswith(".xcodeproj") or name == "Package.swift":  # .xcodeproj arrives as a directory marker
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


def installed_delegates(root: Path) -> dict:
    """Map delegate skill name -> skill directory for every `*-delegate` skill found with a relay script."""
    found = {}
    for base in (*DELEGATE_DIRS, root / ".claude" / "skills", root / ".agents" / "skills"):
        if base.is_dir():
            for d in sorted(base.glob("*-delegate")):
                if (d / "scripts" / "relay.mjs").is_file():
                    found.setdefault(d.name, str(d.resolve()))
    return found


def draft_lanes(delegates: dict) -> list:
    """Propose the implementer lanes: claude-delegate when installed, else the plain Agent-tool lane."""
    agent_lane = {"id": "S", "name": "Agent tool (sonnet)", "when": "every batch",
                  "command": "Agent tool: subagent_type general-purpose, model sonnet, run_in_background",
                  "resume": "SendMessage to the agent id", "fallback": "none"}
    if "claude-delegate" not in delegates:
        return [agent_lane]
    relay = f"node {delegates['claude-delegate']}/scripts/relay.mjs"
    return [{"id": "H", "name": "Haiku high via /claude-delegate", "when": "every batch and fix round",
             "command": f"{relay} --brief <b> --cd <tree> --model claude-haiku-5-5 --effort high --timeout 2h "
                        "--out-dir <runs/id>",
             "resume": "--session <sessionId from result.json>", "fallback": "S"}, agent_lane]


def draft_answers(root: Path, info: dict) -> dict:
    """Build a complete answers.json draft from the detection result; `_confirm` lists what the owner must check."""
    commands = {}
    for stack in info["stacks"]:
        for key, value in stack["commands"].items():
            commands.setdefault(key, value)
    plans = info["plan_candidates"]
    plan_file = plans[0] if plans else "none"
    stem = re.sub(r"^\d{4}-\d{2}-\d{2}-|[-_]plan$", "", Path(plan_file).stem) if plans else root.name
    plan_id = re.sub(r"[^A-Z0-9]+", "_", stem.upper()).strip("_") or "PLAN"
    if len(plan_id) < 2 or not plan_id[0].isalpha():  # PLAN_ID must be 2+ chars and start with a letter
        plan_id = re.sub(r"[^A-Z0-9]+", "_", f"PLAN_{root.name}_{plan_id}".upper()).strip("_")
    src_dirs = " ".join(d for d in ("src", "lib", "app", "backend", "frontend", "server", "web") if (root / d).is_dir())
    tests = "" if info["TEST_DIRS"] == "none" else info["TEST_DIRS"]
    delegates = installed_delegates(root)
    locales = [] if info["LOCALE_FILES"] == "none" else info["LOCALE_FILES"].split(",")
    answers = {
        "PROJECT_NAME": root.name, "PLAN_ID": plan_id, "PLAN_TITLE": f"{stem.replace('-', ' ').replace('_', ' ')}",
        "PROFILES": info["PROFILES"], "PLAN_FILE": plan_file, "RULES_FILES": info["RULES_FILES"],
        "CONTRACT_DOCS": "none", "BASE_BRANCH": info["BASE_BRANCH"], "WORK_BRANCH": info["BASE_BRANCH"],
        "SOURCE_DIRS": src_dirs or "src", "TEST_DIRS": tests or "tests",
        "BUILD_CMD": commands.get("BUILD_CMD", "none"), "LINT_CMD": commands.get("LINT_CMD", "none"),
        "TEST_CMD": commands.get("TEST_CMD", "none"), "E2E_CMD": "none",
        "LANGUAGES": "EN" if len(locales) < 2 else f"{len(locales)} languages", "LOCALE_FILES": ",".join(locales) or "none",
        "REVIEWER_MODEL": "opus", "REVIEWER_EFFORT": "medium", "REVIEWER_AGENT": f"{plan_id.lower().replace('_', '-')}-reviewer",
        "HELPER_MODEL": "sonnet", "BATCH_MINUTES": 30,
        "STAGE_PATHS": " ".join(x for x in (src_dirs, tests, "docs") if x),
        "NEVER_STAGE": ".env*, secrets/*, *.bak-*",
        "FORBIDDEN_GIT": "stash, checkout, restore, reset, switch, clean, push (unless asked)",
        "OWNER_NAME": "the owner", "LANES": draft_lanes(delegates),
        "OWNER_RESERVED": ["user-visible behaviour or copy", "contract/API deviations",
                           "data-loss or security trade-offs", "real scope, cost or schedule changes",
                           "touching real config, secrets or production"],
        "CODING_RULES": {"mode": "default"}, "PARALLEL_PAIRS": "auto",
        "WORKTREE_SETUP_CMD": commands.get("WORKTREE_SETUP_CMD", "none"), "GATE_TIMEOUT_SECONDS": 1800,
        "REVIEWER_AGENT_SCOPE": "project",
    }
    for key in ("FORMAT_CHECK", "SRC_PATTERN", "MIGRATIONS_GLOB"):
        if key in commands:
            answers[key] = commands[key]
    answers["_confirm"] = [
        "plan file and PLAN_ID" if plans else "no plan file found: write one first (superpowers:writing-plans)",
        "gate commands (build / lint / format / tests) and the e2e / live check",
        "coding rules mode (default / edit / replace / repo)",
        "implementer lanes" + (f" (other delegate skills found: {', '.join(sorted(delegates))})" if delegates else
                               " (no delegate skill installed: the Agent tool is the only lane)"),
        "reviewer model and effort, batch size",
        "parallel pairs and the worktree setup command",
    ]
    return answers


def main():
    """Scan the repo and print the suggestions (or the answers.json draft) as JSON."""
    argv = [a for a in sys.argv[1:] if not a.startswith("--")]
    root = Path(argv[0] if argv else ".").resolve()
    stacks, locales, rules, plans, tests = [], [], [], [], set()
    for f in walk(root):
        hit = classify(root, f)
        if hit:
            stacks.append({"profile": hit[0], "tool": hit[1], "root": rel(root, f.parent), "commands": hit[2]})
        if f.is_dir():
            continue
        low = str(f.relative_to(root)).lower()
        if re.search(r"(i18n|l10n|lang|languages|locales?|translations)/[^/]*\.(json|arb|properties|strings)$", low):
            locales.append(rel(root, f))
        if f.name in ("AGENTS.md", "CLAUDE.md", "CONTRIBUTING.md", "GEMINI.md"):
            rules.append(rel(root, f))
        if f.suffix == ".md" and re.search(r"plan|roadmap|spec", low) and "docs" in low:
            plans.append(rel(root, f))
        if f.parent.name in ("test", "tests", "__tests__", "spec"):
            tests.add(rel(root, f.parent))
    stacks = collapse(stacks)
    profiles = list(dict.fromkeys(s["profile"] for s in stacks)) or ["generic"]
    info = {"PROFILES": profiles, "stacks": stacks, "LOCALE_FILES": ",".join(sorted(locales)) or "none",
            "RULES_FILES": ", ".join(sorted(rules)) or "none", "plan_candidates": sorted(plans),
            "TEST_DIRS": " ".join(sorted(tests)) or "none", "BASE_BRANCH": git_default_branch(root),
            "monorepo": len({s["root"] for s in stacks}) > 1}
    print(json.dumps(draft_answers(root, info) if "--draft-answers" in sys.argv else info, indent=2,
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
