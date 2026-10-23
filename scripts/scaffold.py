#!/usr/bin/env python3
"""Generate a project's .superpowers/sdd/<PLAN_ID>/ folder for the es-orchestrator workflow.

Usage:
  scaffold.py --answers answers.json --repo <repo root> [--force] [--only <file>]

Reads answers.json (schema: references/answers-schema.md), merges the stack profile defaults (generic first, then each
profile in PROFILES order, answers last), renders templates/ and the profile checklists, and prints every setup
placeholder it could not fill. Existing files are never overwritten without --force (or --only); overwritten files are
backed up as <file>.bak-<date>.
"""
import argparse
import datetime
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
TEMPLATES = SKILL / "templates"
PROFILES = SKILL / "profiles"
PLACEHOLDER = re.compile(r"\{\{([A-Z][A-Z0-9_]*)\}\}")
# Templates copied as-is into the plan folder (decisions-table.md is embedded in the handoff instead).
COPY_FILES = ["ORCHESTRATOR_HANDOFF.md", "progress.md", "brief-template.md", "survey-brief-template.md",
              "review-full-template.md", "review-light-template.md", "review-lessons-self-check.md",
              "NEXT_SESSION_PROMPT.md", "reviewer-agent.md", "check.sh", "fnlen.py", "locale_parity.py",
              "fnlen-allow.txt", "forbidden-allow.txt", "forbidden-patterns.txt", "known-test-failures.txt"]
EXECUTABLE = {"check.sh", "fnlen.py", "locale_parity.py"}
# Files whose <angle> fields and descriptive {{NAME — hint}} placeholders are filled by hand during setup.
HAND_FILL_FILES = {"ORCHESTRATOR_HANDOFF.md", "progress.md", "NEXT_SESSION_PROMPT.md"}
HAND_FIELD = re.compile(r"(?<!\()<(?:sha|total|phase 1|scope|state|n(?: [^>]*)?)>|\{\{[A-Z_]+ — [^}]*\}\}")
RULES_MODES = {"default": "profile defaults, unchanged", "edit": "profile defaults, edited with the owner",
               "replace": "the owner's own rules replace the defaults", "repo": "the repo's rules file only"}
SCHEMA_KEYS = {"PROJECT_NAME", "PLAN_ID", "PLAN_TITLE", "PLAN_FILE", "RULES_FILES", "CONTRACT_DOCS", "BASE_BRANCH",
               "WORK_BRANCH", "SOURCE_DIRS", "TEST_DIRS", "BUILD_CMD", "LINT_CMD", "TEST_CMD", "E2E_CMD",
               "LIVE_CHECK", "FN_MAX_LINES", "LANGUAGES", "LOCALE_FILES", "REVIEWER_MODEL", "REVIEWER_EFFORT",
               "REVIEWER_AGENT", "HELPER_MODEL", "BATCH_MINUTES", "STAGE_PATHS", "NEVER_STAGE", "FORBIDDEN_GIT",
               "OWNER_NAME", "STACK_SUMMARY", "SRC_PATTERN", "MIGRATIONS_GLOB", "FORMAT_CHECK",
               "TEST_FAILURES_EXTRACT"}


def read(path: Path) -> str:
    """Read a UTF-8 text file, or return "" when it does not exist."""
    return path.read_text(encoding="utf-8") if path.exists() else ""


def profile_list(answers: dict) -> list:
    """Return the profiles to apply: generic first, then the requested ones (deduplicated, validated)."""
    names = ["generic"] + [p for p in answers.get("PROFILES", []) if p != "generic"]
    for name in names:
        if not (PROFILES / name).is_dir():
            sys.exit(f"unknown profile '{name}' (have: {', '.join(p.name for p in PROFILES.iterdir())})")
    return list(dict.fromkeys(names))


def merged_values(answers: dict, profiles: list) -> dict:
    """Merge profile defaults (in order) with the answers; collect forbidden rules from every profile."""
    values, rules, summaries = {}, [], []
    for name in profiles:
        defaults = json.loads(read(PROFILES / name / "defaults.json") or "{}")
        rules += defaults.pop("FORBIDDEN_RULES", [])
        if name != "generic" or len(profiles) == 1:
            summaries.append(defaults.get("STACK_SUMMARY", name))
        values.update(defaults)
    values["STACK_SUMMARY"] = " + ".join(summaries)
    values.update({k: v for k, v in answers.items() if not isinstance(v, (list, dict))})
    values["PROFILE_FORBIDDEN_RULES"] = "\n".join(dict.fromkeys(rules))
    return values


def render_lanes(lanes: list) -> dict:
    """Render the implementer lanes as the list (ROLES), the command table (Workflow) and a one-line summary."""
    as_list, table, short = [], [], []
    for lane in lanes:
        trust = " — evidence UNTRUSTED: orchestrator pre-checks it, reviewer re-runs every gate" \
            if lane.get("untrusted_evidence") else ""
        as_list.append(f"  - **{lane['id']}** = {lane['name']} ({lane.get('when', 'any batch')}); "
                       f"fallback: {lane.get('fallback', 'none')}{trust}")
        table.append(f"- **{lane['id']}** {lane['name']}: `{lane.get('command', '<command>')}` · resume "
                     f"`{lane.get('resume', '<resume flag>')}` · fallback: {lane.get('fallback', 'none')}")
        short.append(f"{lane['id']} = {lane['name']}")
    return {"LANES_LIST": "\n".join(as_list) or "  - {{LANES}}",
            "LANES_TABLE": "\n".join(table) or "- {{LANES}}",
            "LANES_SHORT": "; ".join(short) or "{{LANES}}"}


def derived_values(answers: dict, profiles: list, repo: Path) -> dict:
    """Compute the values the templates need but the owner does not type."""
    plan_id = answers.get("PLAN_ID", "PLAN")
    reserved = answers.get("OWNER_RESERVED", [])
    derived = {
        "PLAN_DIR": f".superpowers/sdd/{plan_id}",
        "TODAY": datetime.date.today().isoformat(),
        "REPO_ROOT": str(repo),
        "PROFILE_NAMES": ", ".join(profiles),
        "OWNER_RESERVED_LIST": "\n".join(f"   - {item}" for item in reserved) or "   - {{OWNER_RESERVED}}",
        "PROFILE_CHECKPOINTS": "\n".join(read(PROFILES / p / "checkpoints.md").strip() for p in profiles).strip(),
        "PROFILE_SELF_CHECK": "\n\n".join(read(PROFILES / p / "self-check.md").strip() for p in profiles).strip(),
        "DECISIONS_TABLE": read(TEMPLATES / "decisions-table.md").strip(),
        "CODING_RULES_SUMMARY": RULES_MODES.get(answers.get("CODING_RULES", {}).get("mode", "default"), "custom"),
    }
    derived.update(render_lanes(answers.get("LANES", [])))
    return derived


def coding_rules(answers: dict, profiles: list, repo: Path) -> str:
    """Build coding-rules.md per CODING_RULES.mode: default/edit = profile rules, replace = the owner's file, repo = none."""
    spec = answers.get("CODING_RULES", {"mode": "default"})
    mode = spec.get("mode", "default")
    if mode == "repo":
        return ""
    if mode == "replace":
        own = repo / spec.get("file", "")
        if not spec.get("file") or not own.is_file():
            sys.exit("CODING_RULES.mode=replace needs CODING_RULES.file (a path inside the repo)")
        return read(own)
    parts = [read(PROFILES / p / "coding-rules.md").strip() for p in profiles]
    return "\n\n".join(part for part in parts if part) + "\n"


def gate_snippets(answers: dict, profiles: list) -> dict:
    """Map gates.d/<name>.sh to the snippet text for every EXTRA_GATES entry found in the chosen profiles."""
    found = {}
    for name in answers.get("EXTRA_GATES", []):
        hits = [PROFILES / p / "gate-snippets" / f"{name}.sh" for p in profiles]
        hit = next((h for h in hits if h.is_file()), None)
        if hit is None:
            sys.exit(f"EXTRA_GATES: no snippet '{name}' in profiles {', '.join(profiles)}")
        found[f"gates.d/{name}.sh"] = read(hit)
    return found


def performance_checklist(profiles: list) -> str:
    """Use the stack profiles' performance groups; fall back to the generic list when only generic is chosen."""
    specific = [p for p in profiles if p != "generic"] or ["generic"]
    return "\n\n".join(read(PROFILES / p / "performance-checklist.md").strip() for p in specific) + "\n"


def shell_quote(value: str) -> str:
    """Escape a value for use inside a single-quoted bash string."""
    return value.replace("'", "'\\''")


def substitute(text: str, values: dict, shell: bool) -> str:
    """Replace {{KEY}} placeholders repeatedly (values may contain placeholders themselves)."""
    for _ in range(4):
        new = PLACEHOLDER.sub(lambda m: (shell_quote(str(values[m.group(1)])) if shell else str(values[m.group(1)]))
                              if m.group(1) in values else m.group(0), text)
        if new == text:
            break
        text = new
    return text


def unfilled(name: str, text: str, setup_keys: set) -> list:
    """List setup placeholders left in a rendered file (per-batch placeholders like {{BASE}} are expected)."""
    return [f"{name}:{n}: {{{{{m}}}}}" for n, line in enumerate(text.splitlines(), 1)
            for m in PLACEHOLDER.findall(line) if m in setup_keys]


def hand_fill(name: str, text: str) -> list:
    """List the fields the orchestrator fills by hand after the baseline (<sha>, <total>, {{STATE — …}} …)."""
    if name not in HAND_FILL_FILES:
        return []
    return [f"{name}:{n}: {', '.join(sorted(set(HAND_FIELD.findall(line))))}"
            for n, line in enumerate(text.splitlines(), 1) if HAND_FIELD.search(line)]


def write_file(target: Path, text: str, overwrite: bool) -> bool:
    """Write one file; back up an existing one first. Returns False when it exists and overwrite is off."""
    if target.exists():
        if not overwrite:
            return False
        shutil.copy2(target, target.with_name(f"{target.name}.bak-{datetime.date.today().isoformat()}"))
    target.write_text(text, encoding="utf-8")
    if target.name in EXECUTABLE or target.suffix == ".sh":
        target.chmod(0o755)
    return True


def sources(answers: dict, profiles: list, repo: Path) -> dict:
    """Map every output file name to its unrendered text."""
    out = {name: read(TEMPLATES / name) for name in COPY_FILES}
    out["review-checklist.md"] = read(PROFILES / "generic" / "review-checklist.md")
    out["performance-checklist.md"] = performance_checklist(profiles)
    rules = coding_rules(answers, profiles, repo)
    if rules:
        out["coding-rules.md"] = rules
    out.update(gate_snippets(answers, profiles))
    return out


def report_environment(repo: Path, plan_dir: Path, values: dict):
    """Print the follow-up steps the orchestrator must do by hand (gitignore, reviewer agent)."""
    ignored = subprocess.run(["git", "-C", str(repo), "check-ignore", "-q", str(plan_dir)],
                             capture_output=True).returncode == 0
    print(f"gitignore: {'OK, .superpowers is ignored' if ignored else 'NOT IGNORED — propose adding .superpowers/ to .gitignore'}")
    agent = Path.home() / ".claude" / "agents" / f"{values.get('REVIEWER_AGENT', 'reviewer')}.md"
    state = "already installed" if agent.exists() else "not installed — copy reviewer-agent.md there after the owner's OK"
    print(f"reviewer agent: {agent} ({state})")


def main():
    """Parse arguments, render every file, and print the result summary."""
    parser = argparse.ArgumentParser(description="Generate the es-orchestrator plan folder.")
    parser.add_argument("--answers", required=True, type=Path)
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--force", action="store_true", help="overwrite existing files (backups kept)")
    parser.add_argument("--only", help="regenerate just this output file (backup kept)")
    args = parser.parse_args()

    answers = json.loads(args.answers.read_text(encoding="utf-8"))
    repo = args.repo.resolve()
    profiles = profile_list(answers)
    values = merged_values(answers, profiles)
    values.update(derived_values(answers, profiles, repo))
    plan_dir = repo / values["PLAN_DIR"]
    files = sources(answers, profiles, repo)
    values["REPO_RULES_FILES"] = values.get("RULES_FILES", "{{RULES_FILES}}")
    if "coding-rules.md" in files:
        values["RULES_FILES"] = f"{values['REPO_RULES_FILES']}, {values['PLAN_DIR']}/coding-rules.md"
    if plan_dir.exists() and not (args.force or args.only):
        sys.exit(f"{plan_dir} exists — refusing to overwrite (use --only <file> or --force with the owner's OK)")
    for sub in ("runs/baseline", "gates.d"):
        (plan_dir / sub).mkdir(parents=True, exist_ok=True)

    setup_keys = SCHEMA_KEYS | {"LANES", "OWNER_RESERVED"} | set(values)
    written, skipped, leftovers, by_hand = [], [], [], []
    for name, raw in files.items():
        if args.only and name != args.only:
            continue
        text = substitute(raw, values, shell=name == "check.sh")
        leftovers += unfilled(name, text, setup_keys)
        by_hand += hand_fill(name, text)
        (written if write_file(plan_dir / name, text, args.force or bool(args.only)) else skipped).append(name)

    print(f"plan folder: {plan_dir}\nprofiles: {', '.join(profiles)}\nwritten: {len(written)} files")
    if skipped:
        print("skipped (exist): " + ", ".join(skipped))
    print("UNFILLED:" if leftovers else "UNFILLED: none")
    for item in leftovers:
        print(f"  {item}")
    print("FILL BY HAND (after the baseline gate):" if by_hand else "FILL BY HAND: none")
    for item in by_hand:
        print(f"  {item}")
    report_environment(repo, plan_dir, values)
    return 0


if __name__ == "__main__":
    sys.exit(main())
