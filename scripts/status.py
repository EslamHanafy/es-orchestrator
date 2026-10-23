#!/usr/bin/env python3
"""Exact done/left status for the start of every orchestrator session.

Usage: status.py --repo <repo root> --plan-id <PLAN_ID> [--plan <plan file>] [--json]
Counts plan tasks, phases and runs so the opening status line is computed rather than estimated:
- Tasks: markdown checkboxes (`- [x]` / `- [ ]`) and task headings (`### Task 1.2 …`) whose own section has a status
  line (`Status: ✅ …`, `**Status:** done`). A heading counts as done when its status line has ✅, "done",
  "complete" or "closed".
- Effort: an optional tag on the task line or heading, `[effort: 3]` / `(effort 2h)` / `[S]` `[M]` `[L]` `[XL]`
  (S=1, M=2, L=4, XL=8). Tasks without a tag weigh 1.
- Phases: the progress.md roadmap table (✅ closed · 🔄 open · ⬜ not started).
- Runs: runs/<id>/START without result.json = RUNNING; result.json without a review report = AWAITING REVIEW.
"""
import argparse
import json
import re
from pathlib import Path

CHECKBOX = re.compile(r"^\s*[-*] \[( |x|X)\] (.+)$")
HEADING = re.compile(r"^#{2,4}\s+(?:Task|Step)\s+[\w.\-]+")
STATUS = re.compile(r"status\**\s*:\**\s*(.*)", re.IGNORECASE)
DONE = re.compile(r"✅|\bdone\b|\bcomplete(d)?\b|\bclosed\b", re.IGNORECASE)
EFFORT = re.compile(r"\[effort:?\s*(\d+(?:\.\d+)?)h?\]|\(effort:?\s*(\d+(?:\.\d+)?)h?\)|\[(S|M|L|XL)\]")
SIZES = {"S": 1, "M": 2, "L": 4, "XL": 8}


def weight(text: str) -> float:
    """Return the effort weight tagged on a task line (default 1)."""
    m = EFFORT.search(text)
    if not m:
        return 1.0
    return float(m.group(1) or m.group(2)) if (m.group(1) or m.group(2)) else float(SIZES[m.group(3)])


def plan_tasks(lines: list) -> list:
    """Return [(title, weight, done)] for every checkbox and every status-bearing task heading."""
    tasks = []
    for i, line in enumerate(lines):
        box = CHECKBOX.match(line)
        if box:
            tasks.append((box.group(2)[:70], weight(line), box.group(1).lower() == "x"))
        elif HEADING.match(line):
            section = lines[i + 1:i + 40]
            end = next((k for k, l in enumerate(section) if l.startswith("#")), len(section))
            status = next((STATUS.search(l).group(1) for l in section[:end] if STATUS.search(l)), None)
            if status is not None:
                tasks.append((line.strip("# ").strip()[:70], weight(line), bool(DONE.search(status))))
    return tasks


def roadmap(progress: str) -> dict:
    """Count roadmap rows by status mark in progress.md."""
    rows = [l for l in progress.splitlines() if l.startswith("|") and not set(l) <= set("|- ")]
    marks = {"closed": "✅", "open": "🔄", "not_started": "⬜"}
    return {k: sum(1 for r in rows if v in r) for k, v in marks.items()}


def runs(plan_dir: Path) -> dict:
    """Classify run folders: running (START, no result.json) and awaiting review (result, no review report)."""
    state = {"running": [], "awaiting_review": []}
    for run in sorted((plan_dir / "runs").glob("*/")):
        if (run / "START").exists() and not (run / "result.json").exists():
            state["running"].append(run.name)
        elif (run / "result.json").exists() and not list(plan_dir.glob(f"*{run.name}*review-report.md")):
            state["awaiting_review"].append(run.name)
    return state


def pct(part: float, whole: float) -> int:
    """Whole-number percentage, 0 when there is nothing to count."""
    return round(100 * part / whole) if whole else 0


def main():
    """Compute and print the status block (or JSON)."""
    ap = argparse.ArgumentParser(description="es-orchestrator status")
    ap.add_argument("--repo", type=Path, default=Path("."))
    ap.add_argument("--plan-id", required=True)
    ap.add_argument("--plan", type=Path, help="plan file (default: read from the handoff Key paths)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    plan_dir = args.repo / ".superpowers" / "sdd" / args.plan_id
    handoff = (plan_dir / "ORCHESTRATOR_HANDOFF.md").read_text(encoding="utf-8")
    plan = args.plan or args.repo / re.search(r"Plan: `([^`]+)`", handoff).group(1)
    tasks = plan_tasks(plan.read_text(encoding="utf-8").splitlines())
    done = [t for t in tasks if t[2]]
    total_w, done_w = sum(t[1] for t in tasks), sum(t[1] for t in done)
    progress = (plan_dir / "progress.md").read_text(encoding="utf-8")
    result = {"tasks_done": len(done), "tasks_total": len(tasks), "pct_count": pct(len(done), len(tasks)),
              "pct_effort": pct(done_w, total_w), "phases": roadmap(progress), **runs(plan_dir),
              "next_open": [t[0] for t in tasks if not t[2]][:5]}
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return
    print(f"DONE {result['tasks_done']}/{result['tasks_total']} tasks ≈ {result['pct_count']} % by count, "
          f"≈ {result['pct_effort']} % by effort · LEFT {100 - result['pct_count']} % / {100 - result['pct_effort']} %")
    ph = result["phases"]
    print(f"PHASES closed {ph['closed']} · open {ph['open']} · not started {ph['not_started']}")
    print(f"RUNNING: {', '.join(result['running']) or 'none'} · AWAITING REVIEW: {', '.join(result['awaiting_review']) or 'none'}")
    print("NEXT OPEN TASKS: " + ("; ".join(result["next_open"]) or "none"))


if __name__ == "__main__":
    main()
