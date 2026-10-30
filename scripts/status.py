#!/usr/bin/env python3
"""Exact done/left status for the start of every orchestrator session, plus the stage marker used by the run modes.

Usage:
  status.py --repo <repo root> --plan-id <PLAN_ID> [--plan <plan file>] [--json] [--stale-hours 6]
  status.py --repo <repo root> --plan-id <PLAN_ID> --set-stage <STAGE> [--next-mode "review B14+B15"] [--note "..."]

Counts plan tasks, phases and runs so the opening status line is computed rather than estimated:
- Tasks: a task heading (`### Task 1.2 …`) is ONE task. It is done when its own status line (`Status: ✅ …`,
  `**Status:** done`) says ✅, "done", "complete" or "closed"; with no status line it is done when every checkbox
  inside the heading's section is ticked. Checkboxes (`- [x]` / `- [ ]`) inside a counted task are its steps and are
  not counted again. Checkboxes outside any counted task are tasks of their own.
- Effort: an optional tag on the task line or heading, `[effort: 3]` / `(effort 2h)` / `[S]` `[M]` `[L]` `[XL]`
  (S=1, M=2, L=4, XL=8). Tasks without a tag weigh 1.
- Phases: the progress.md roadmap table (✅ closed · 🔄 open · ⬜ not started).
- Runs: runs/<id>/START without result.json = RUNNING (STALE when older than --stale-hours or when runs/<id>/pid
  names a dead process); result.json without a review report = AWAITING REVIEW; a review report without the
  `<ids>-OWNER_REPORT_SENT` marker = AWAITING OWNER REPORT.
- Worktrees: the parallel-pair worktrees of this plan (see scripts/worktree.py).
- Stage: the last `--set-stage` value in <plan>/state.json (set by the run modes).
"""
import argparse
import datetime
import json
import os
import re
import sys
import time
from pathlib import Path

CHECKBOX = re.compile(r"^\s*[-*] \[( |x|X)\] (.+)$")
HEADING = re.compile(r"^(#{2,4})\s+(?:Task|Step)\s+[A-Za-z]{0,3}\d")
ANY_HEADING = re.compile(r"^(#{1,6})\s")
STATUS = re.compile(r"^\s*(?:[-*]\s+)?\**status\**\s*:\**\s*(.*)$", re.IGNORECASE)
# A status counts as done only when it STARTS with a done mark or word ("❌ not complete" / "pending (done when …)" do not).
DONE = re.compile(r"^[\s*_`>~-]*(?:✅|✔|☑|(?:done|complete(?:d)?|closed|finished|merged|shipped)\b)", re.IGNORECASE)
EFFORT = re.compile(r"\[effort:?\s*(\d+(?:\.\d+)?)h?\]|\(effort:?\s*(\d+(?:\.\d+)?)h?\)|\[(S|M|L|XL)\]")
SIZES = {"S": 1, "M": 2, "L": 4, "XL": 8}
STAGES = ("NONE", "PLANNED", "IMPLEMENTED-UNREVIEWED", "REVIEWED-UNCOMMITTED", "FIX-ROUND-NEEDED", "COMMITTED")
REPORT_SUFFIX = "-review-report.md"


def weight(text: str) -> float:
    """Return the effort weight tagged on a task line (default 1)."""
    m = EFFORT.search(text)
    if not m:
        return 1.0
    return float(m.group(1) or m.group(2)) if (m.group(1) or m.group(2)) else float(SIZES[m.group(3)])


def section_end(lines: list, start: int, level: int) -> int:
    """Return the index of the first line after `start` that is a heading of the same or a higher level."""
    for k in range(start + 1, len(lines)):
        m = ANY_HEADING.match(lines[k])
        if m and len(m.group(1)) <= level:
            return k
    return len(lines)


def mask_fences(lines: list) -> list:
    """Blank out fenced code blocks so example checkboxes and headings in them are not counted."""
    out, inside = [], False
    for line in lines:
        if line.lstrip().startswith(("```", "~~~")):
            inside = not inside
            out.append("")
        else:
            out.append("" if inside else line)
    return out


def task_from_heading(lines: list, start: int, end: int):
    """Return True/False (done/open) for the task heading at `start`, or None when the Task/Step children are the tasks.

    Order of evidence: the task's OWN status line (before its first nested heading), then every checkbox in its
    section (done when all are ticked), then nothing: a task without any signal counts as open.
    """
    body = lines[start + 1:end]
    first_child = next((k for k, l in enumerate(body) if ANY_HEADING.match(l)), len(body))
    status = next((STATUS.search(l).group(1) for l in body[:first_child] if STATUS.search(l)), None)
    if status is not None:
        return bool(DONE.search(status))
    boxes = [CHECKBOX.match(l) for l in body if CHECKBOX.match(l)]
    if boxes:
        return all(b.group(1).lower() == "x" for b in boxes)
    if any(HEADING.match(l) for l in body[first_child:]):
        return None
    return False


def plan_tasks(lines: list) -> list:
    """Return [(title, weight, done)]: one entry per task heading and per checkbox outside any task heading."""
    lines = mask_fences(lines)
    tasks, i = [], 0
    while i < len(lines):
        line = lines[i]
        head = HEADING.match(line)
        if head:
            end = section_end(lines, i, len(head.group(1)))
            verdict = task_from_heading(lines, i, end)
            if verdict is not None:
                tasks.append((line.strip("# ").strip()[:70], weight(line), verdict))
                i = end
                continue
        box = CHECKBOX.match(line)
        if box:
            tasks.append((box.group(2)[:70], weight(line), box.group(1).lower() == "x"))
        i += 1
    return tasks


def roadmap(progress: str) -> dict:
    """Count roadmap rows by status mark in progress.md."""
    rows = [l for l in progress.splitlines() if l.startswith("|") and not set(l) <= set("|- ")]
    marks = {"closed": "✅", "open": "🔄", "not_started": "⬜"}
    return {k: sum(1 for r in rows if v in r) for k, v in marks.items()}


def pid_alive(pid: int) -> bool:
    """True when a process with this pid exists (signal 0 probe)."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def reviewed_ids(plan_dir: Path) -> list:
    """Stems of the review reports (`<A>+<B>` or legacy `<A>-<B>-<C>`): a run counts as reviewed when its id appears as a whole token."""
    return [r.name[:-len(REPORT_SUFFIX)] for r in plan_dir.glob(f"*{REPORT_SUFFIX}")]


def is_reviewed(run_id: str, stems: list) -> bool:
    """True when `run_id` is a whole token (delimited by start, end, '+' or '-') of some review report stem."""
    pattern = re.compile(rf"(?:^|[+\-]){re.escape(run_id)}(?:$|[+\-])")
    return any(pattern.search(stem) for stem in stems)


def runs(plan_dir: Path, stale_hours: float) -> dict:
    """Classify run folders: running / stale, awaiting review, and reviews not yet sent to the owner."""
    state = {"running": [], "stale": [], "awaiting_review": [], "awaiting_owner_report": []}
    reviewed = reviewed_ids(plan_dir)
    for run in sorted((plan_dir / "runs").glob("*/")):
        start, result = run / "START", run / "result.json"
        if start.exists() and not result.exists():
            age_h = (time.time() - start.stat().st_mtime) / 3600
            pid_file = run / "pid"
            dead = pid_file.exists() and pid_file.read_text().strip().isdigit() \
                and not pid_alive(int(pid_file.read_text().strip()))
            if dead or age_h > stale_hours:
                state["stale"].append(f"{run.name} ({'process gone' if dead else f'{age_h:.0f} h old'})")
            else:
                state["running"].append(run.name)
        elif result.exists() and not is_reviewed(run.name, reviewed):
            state["awaiting_review"].append(run.name)
    reports = sorted(plan_dir.glob(f"*{REPORT_SUFFIX}"), key=lambda r: r.stat().st_mtime)
    if reports:  # only the newest review can still be waiting for the owner; older ones (and legacy plans) are history
        stem = reports[-1].name[:-len(REPORT_SUFFIX)]
        if not (plan_dir / f"{stem}-OWNER_REPORT_SENT").exists():
            state["awaiting_owner_report"].append(stem)
    return state


def worktrees(plan_dir: Path) -> list:
    """List this plan's live parallel-pair worktrees with their state (see scripts/worktree.py)."""
    found = []
    for marker in sorted((plan_dir / "runs").glob("*/WORKTREE.json")):
        try:
            info = json.loads(marker.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if info.get("removed"):
            continue
        run = marker.parent
        state = "landed" if (run / "LANDED").exists() else "snapshotted" if (run / "SNAPSHOT.json").exists() \
            else "in progress"
        found.append(f"{info.get('id', run.name)} {state} at {info.get('path', '?')}")
    return found


def read_state(plan_dir: Path) -> dict:
    """Load state.json (stage marker); an empty dict when it does not exist or is unreadable."""
    try:
        return json.loads((plan_dir / "state.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def set_stage(plan_dir: Path, stage: str, next_mode: str, note: str) -> dict:
    """Write the stage marker the run modes use to hand work from one mode (or session) to the next."""
    if stage not in STAGES:
        sys.exit(f"unknown stage '{stage}' (use one of: {', '.join(STAGES)})")
    state = {"stage": stage, "next_mode": next_mode, "note": note,
             "updated": datetime.datetime.now().isoformat(timespec="seconds")}
    (plan_dir / "state.json").write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return state


def load(path: Path, what: str) -> str:
    """Read a required file, or exit with a message that says what is missing and how to fix it."""
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        sys.exit(f"{what} not found: {path}. Run setup first, or check --repo / --plan-id.")


def plan_path(repo: Path, handoff: str, given):
    """Resolve the plan file from --plan or from the handoff's `Plan: `path`` line."""
    if given:
        return given
    m = re.search(r"Plan: `([^`]+)`", handoff)
    if not m:
        sys.exit("no 'Plan: `<path>`' line in ORCHESTRATOR_HANDOFF.md; pass --plan <plan file>.")
    return repo / m.group(1)


def pct(part: float, whole: float) -> int:
    """Whole-number percentage, 0 when there is nothing to count."""
    return round(100 * part / whole) if whole else 0


def report(result: dict, plan_dir: Path):
    """Print the human-readable status block."""
    if not result["tasks_total"]:
        print("DONE: no tasks recognised in the plan file. Use `### Task N …` headings with a `Status:` line, or `- [ ]` checkboxes.")
    else:
        print(f"DONE {result['tasks_done']}/{result['tasks_total']} tasks ≈ {result['pct_count']} % by count, "
              f"≈ {result['pct_effort']} % by effort · LEFT {100 - result['pct_count']} % / {100 - result['pct_effort']} %")
    ph = result["phases"]
    print(f"PHASES closed {ph['closed']} · open {ph['open']} · not started {ph['not_started']}")
    st = result["state"]
    if st:
        print(f"STAGE: {st.get('stage', 'NONE')} · NEXT MODE: {st.get('next_mode') or '—'} · {st.get('note') or ''}".rstrip(" ·"))
    for key, label in (("running", "RUNNING"), ("stale", "STALE (check or re-dispatch)"),
                       ("awaiting_review", "AWAITING REVIEW"), ("awaiting_owner_report", "AWAITING OWNER REPORT")):
        print(f"{label}: {', '.join(result[key]) or 'none'}")
    if result["worktrees"]:
        print("WORKTREES: " + "; ".join(result["worktrees"]))
    print("NEXT OPEN TASKS: " + ("; ".join(result["next_open"]) or "none"))


def main():
    """Compute and print the status block (or JSON), or record the stage marker."""
    ap = argparse.ArgumentParser(description="es-orchestrator status")
    ap.add_argument("--repo", type=Path, default=Path("."))
    ap.add_argument("--plan-id", required=True)
    ap.add_argument("--plan", type=Path, help="plan file (default: read from the handoff Key paths)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--stale-hours", type=float, default=6.0)
    ap.add_argument("--set-stage", choices=STAGES, help="record the stage reached (run modes call this)")
    ap.add_argument("--next-mode", default="", help="with --set-stage: the mode to run next, e.g. 'review B14+B15'")
    ap.add_argument("--note", default="", help="with --set-stage: a short free-text note")
    args = ap.parse_args()
    plan_dir = args.repo / ".superpowers" / "sdd" / args.plan_id
    if args.set_stage:
        if not plan_dir.is_dir():
            sys.exit(f"plan folder not found: {plan_dir}")
        print(json.dumps(set_stage(plan_dir, args.set_stage, args.next_mode, args.note), ensure_ascii=False))
        return
    handoff = load(plan_dir / "ORCHESTRATOR_HANDOFF.md", "handoff")
    plan = plan_path(args.repo, handoff, args.plan)
    tasks = plan_tasks(load(plan, "plan file").splitlines())
    done = [t for t in tasks if t[2]]
    total_w, done_w = sum(t[1] for t in tasks), sum(t[1] for t in done)
    progress = load(plan_dir / "progress.md", "progress ledger")
    result = {"tasks_done": len(done), "tasks_total": len(tasks), "pct_count": pct(len(done), len(tasks)),
              "pct_effort": pct(done_w, total_w), "recognised": bool(tasks), "phases": roadmap(progress), "state": read_state(plan_dir),
              **runs(plan_dir, args.stale_hours), "worktrees": worktrees(plan_dir),
              "next_open": [t[0] for t in tasks if not t[2]][:5]}
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return
    report(result, plan_dir)


if __name__ == "__main__":
    main()
