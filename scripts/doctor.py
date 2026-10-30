#!/usr/bin/env python3
"""Health check for the es-orchestrator install and for a project's plan folder.

Usage: doctor.py [--repo .] [--plan-id <PLAN_ID>]
Without --plan-id it checks the environment and lists the plans it finds. With it, it also checks the plan folder:
required files, the gate script (syntax, executable), unfilled placeholders, .gitignore, reviewer agent, baseline gate,
LIVE STATUS heading, plan file, stale runs and leftover worktrees.
Prints ✅ ok · ⚠ worth fixing · ❌ broken; exit code 1 when anything is ❌.
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
DELEGATE_CLIS = ("claude", "opencode", "cursor-agent", "agy", "codex", "kimi", "grok")
REQUIRED = ("ORCHESTRATOR_HANDOFF.md", "progress.md", "check.sh", "fnlen.py", "locale_parity.py", "run_timeout.py",
            "scan_added.py", "secret-patterns.txt", "review-checklist.md", "performance-checklist.md",
            "review-lessons-self-check.md", "brief-template.md", "review-full-template.md", "NEXT_SESSION_PROMPT.md",
            "config.json")
PER_BATCH_FILES = {"brief-template.md", "survey-brief-template.md", "review-full-template.md", "review-light-template.md",
                   "reviewer-agent.md"}
SETUP_PLACEHOLDER = re.compile(r"\{\{[A-Z][A-Z0-9_]*\}\}")
HAND_FIELD = re.compile(r"\{\{[A-Z_]+ — [^}]*\}\}")


class Report:
    """Collects the check results and prints them in order."""

    def __init__(self):
        self.bad = 0

    def ok(self, text):
        """Record a passing check."""
        print(f"✅ {text}")

    def warn(self, text):
        """Record something worth fixing."""
        print(f"⚠  {text}")

    def fail(self, text):
        """Record a broken check."""
        self.bad += 1
        print(f"❌ {text}")


def environment(rep: Report, repo: Path):
    """Check the tools the skill and its scripts need."""
    if sys.version_info >= (3, 9):
        rep.ok(f"python {sys.version.split()[0]}")
    else:
        rep.fail(f"python {sys.version.split()[0]} is too old (need 3.9+)")
    for tool, needed in (("git", True), ("bash", True), ("node", False)):
        found = shutil.which(tool)
        (rep.ok if found else rep.fail if needed else rep.warn)(
            f"{tool}: {found or 'not found' + ('' if needed else ' (only needed by the delegate relays)')}")
    head = (SKILL / "SKILL.md").read_text(encoding="utf-8", errors="replace").split("---")
    frontmatter = head[1] if len(head) > 2 else ""
    if re.search(r"^name: es-orchestrator\s*$", frontmatter, re.M) and "description:" in frontmatter:
        rep.ok(f"skill found at {SKILL}")
    else:
        rep.fail(f"{SKILL}/SKILL.md has no valid name/description frontmatter")
    clis = [c for c in DELEGATE_CLIS if shutil.which(c)]
    rep.ok(f"implementer CLIs on PATH: {', '.join(clis)}") if clis else rep.warn(
        "no implementer CLI on PATH (claude, opencode, …): only the Agent-tool lane will work")
    delegates = sorted({d.name for base in (Path.home() / ".claude" / "skills", Path.home() / ".agents" / "skills",
                                            repo / ".claude" / "skills", repo / ".agents" / "skills") if base.is_dir()
                        for d in base.glob("*-delegate")})
    rep.ok(f"delegate skills: {', '.join(delegates)}") if delegates else rep.warn(
        "no *-delegate skill installed (optional; the Agent tool is the fallback lane)")


def git_ok(repo: Path, *args) -> bool:
    """Run a git command quietly and report whether it succeeded."""
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True).returncode == 0


def plan_files(rep: Report, folder: Path):
    """Check the generated files exist, the gate script is sound and no setup placeholder is left."""
    for name in REQUIRED:
        if not (folder / name).exists():
            rep.fail(f"missing {name} (run `scaffold.py --upgrade-static --plan-id <ID>` for helper scripts, or `--only {name}`)")
    check = folder / "check.sh"
    if check.exists():
        rep.ok("check.sh is executable") if check.stat().st_mode & 0o111 else rep.fail("check.sh is not executable")
        syntax = subprocess.run(["bash", "-n", str(check)], capture_output=True, text=True)
        rep.ok("check.sh syntax") if syntax.returncode == 0 else rep.fail(f"check.sh syntax: {syntax.stderr.strip()}")
    left, by_hand = [], []
    for f in sorted(folder.glob("*")):
        if not f.is_file() or f.suffix in (".bak",) or ".bak-" in f.name or f.name in PER_BATCH_FILES or f.name.startswith("archive-"):
            continue
        try:
            text = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        left += [f"{f.name}: {m}" for m in sorted(set(SETUP_PLACEHOLDER.findall(text)))]
        by_hand += [f"{f.name}: {m[:60]}" for m in sorted(set(HAND_FIELD.findall(text)))]
    rep.ok("no unfilled setup placeholders") if not left else rep.fail("unfilled setup placeholders: " + "; ".join(left[:8]))
    rep.ok("no hand-fill fields left") if not by_hand else rep.warn("hand-fill fields still open: " + "; ".join(by_hand[:6]))


def plan_context(rep: Report, repo: Path, folder: Path):
    """Check what surrounds the plan folder: gitignore, plan file, reviewer agent, baseline, runs and worktrees."""
    rep.ok(".superpowers/ is gitignored") if git_ok(repo, "check-ignore", "-q", str(folder)) else rep.warn(
        ".superpowers/ is NOT gitignored: add it to .gitignore")
    handoff = (folder / "ORCHESTRATOR_HANDOFF.md")
    text = handoff.read_text(encoding="utf-8", errors="replace") if handoff.exists() else ""
    rep.ok("handoff has a LIVE STATUS section") if "## ▶ LIVE STATUS" in text else rep.fail("handoff has no '## ▶ LIVE STATUS' heading")
    plan = re.search(r"Plan: `([^`]+)`", text)
    if plan and (repo / plan.group(1)).is_file():
        rep.ok(f"plan file {plan.group(1)}")
    else:
        rep.fail("plan file not found (handoff 'Plan: `path`' line)")
    try:
        config = json.loads((folder / "config.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        config = {}
    agent = config.get("REVIEWER_AGENT")
    if agent:
        where = Path.home() / ".claude" / "agents" if config.get("REVIEWER_AGENT_SCOPE") == "user" else repo / ".claude" / "agents"
        rep.ok(f"reviewer agent {where / (agent + '.md')}") if (where / f"{agent}.md").is_file() else rep.warn(
            f"reviewer agent not installed: copy {folder}/reviewer-agent.md to {where / (agent + '.md')} (ask the owner first)")
    baseline = folder / "runs" / "baseline" / "gate.log"
    if baseline.exists():
        rep.ok("baseline gate passed") if "ALL GATES PASS" in baseline.read_text(errors="replace") else rep.warn(
            "baseline gate did not pass: known failures must be listed in known-test-failures.txt")
    else:
        rep.warn("no baseline gate yet (runs/baseline/gate.log): run check.sh HEAD once")
    for start in sorted((folder / "runs").glob("*/START")):
        run = start.parent
        if not (run / "result.json").exists() and (time.time() - start.stat().st_mtime) / 3600 > 6:
            rep.warn(f"run {run.name} has been RUNNING for over 6 h: check it or re-dispatch")
    live = [m.parent.name for m in sorted((folder / "runs").glob("*/WORKTREE.json"))
            if not json.loads(m.read_text(encoding="utf-8")).get("removed")]
    rep.ok("no leftover worktrees") if not live else rep.warn(
        f"live worktrees: {', '.join(live)} (finish with land, then `worktree.py remove`)")
    if config.get("PARALLEL_PAIRS") not in ("off", None) and shutil.which("git"):
        setup = config.get("WORKTREE_SETUP_CMD")
        rep.ok(f"parallel pairs {config.get('PARALLEL_PAIRS')}, worktree setup `{setup}`") if setup else rep.warn(
            "parallel pairs are on but WORKTREE_SETUP_CMD is empty: use `none` if the stack needs no install step")


def main() -> int:
    """Run the environment checks, then the plan checks when a plan exists."""
    ap = argparse.ArgumentParser(description="es-orchestrator doctor")
    ap.add_argument("--repo", type=Path, default=Path("."))
    ap.add_argument("--plan-id")
    args = ap.parse_args()
    repo, rep = args.repo.resolve(), Report()
    environment(rep, repo)
    base = repo / ".superpowers" / "sdd"
    plans = sorted(p.name for p in base.glob("*") if p.is_dir()) if base.is_dir() else []
    if not args.plan_id:
        print(f"plans in this repo: {', '.join(plans) or 'none (run setup)'}")
        return 1 if rep.bad else 0
    folder = base / args.plan_id
    if not folder.is_dir():
        rep.fail(f"plan folder not found: {folder} (have: {', '.join(plans) or 'none'})")
        return 1
    plan_files(rep, folder)
    plan_context(rep, repo, folder)
    print("—\nALL GOOD" if not rep.bad else f"—\n{rep.bad} problem(s) to fix")
    return 1 if rep.bad else 0


if __name__ == "__main__":
    sys.exit(main())
