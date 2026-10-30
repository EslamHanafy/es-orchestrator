#!/usr/bin/env python3
"""Trim the handoff and the progress ledger into archive files at the end of a session.

Usage: archive.py --repo <repo root> --plan-id <PLAN_ID> --session <N> [--keep-sessions 2] [--apply]
Without --apply it only prints what would move (dry run). With --apply it backs up both files
(*.bak-<date>s<N>) and then:
- handoff: every LIVE STATUS block line that starts with "**▶" except the FIRST END STATE block and the FIRST live line
  in file order (blocks are written newest first, so the first ones are the newest)
  (with any lines that follow each moved block up to the next block) → archive-ORCHESTRATOR_HANDOFF-through-s<N>.md;
- progress: ledger lines tagged "(s<k>)" with k <= N - keep_sessions → archive-progress-through-s<N>.md.
Protected sections (HARD RULE, ROLES, DECISIONS, RULE CHECKLIST, Workflow, Checklists, Key paths) are never touched.
"""
import argparse
import datetime
import re
import shutil
import sys
from pathlib import Path

LIVE_HEADING = re.compile(r"^## ▶ LIVE STATUS")
BLOCK_START = re.compile(r"^\*\*▶")
END_STATE = re.compile(r"END STATE")
SESSION_TAG = re.compile(r"\(s(\d+)\)")


def split_live(lines: list):
    """Return (start, end) line indexes of the LIVE STATUS section body."""
    heading = next((i for i, l in enumerate(lines) if LIVE_HEADING.match(l)), None)
    if heading is None:
        sys.exit("no '## ▶ LIVE STATUS' heading in the handoff; add it (see templates/ORCHESTRATOR_HANDOFF.md) and retry.")
    start = heading + 1
    end = next((i for i in range(start, len(lines)) if lines[i].startswith("## ")), len(lines))
    return start, end


def live_blocks(body: list) -> list:
    """Group the LIVE STATUS body into blocks, each starting at a '**▶' line; the preamble is block 0."""
    blocks, current = [], []
    for line in body:
        if BLOCK_START.match(line) and current:
            blocks.append(current)
            current = []
        current.append(line)
    blocks.append(current)
    return blocks


def keep_block(block: list, kept: dict) -> bool:
    """Keep the preamble, the first END STATE block and the first non-END-STATE live block; archive the rest."""
    head = block[0]
    if not BLOCK_START.match(head):
        return True
    kind = "end" if END_STATE.search(head) else "live"
    if kind in kept:
        return False
    kept[kind] = True
    return True


def trim_handoff(text: str):
    """Return (new handoff text, archived lines)."""
    lines = text.splitlines()
    start, end = split_live(lines)
    kept_flags, keep, moved = {}, [], []
    for block in live_blocks(lines[start:end]):
        (keep if keep_block(block, kept_flags) else moved).extend(block)
    if moved:
        keep.insert(1, "(Older session blocks moved to the archive file on "
                       f"{datetime.date.today().isoformat()}; consult it only for archaeology.)")
    return "\n".join(lines[:start] + keep + lines[end:]) + "\n", moved


def trim_progress(text: str, cutoff: int):
    """Return (new progress text, archived ledger lines) for sessions <= cutoff."""
    keep, moved = [], []
    for line in text.splitlines():
        tag = SESSION_TAG.search(line) if line.startswith("- ") else None
        (moved if tag and int(tag.group(1)) <= cutoff else keep).append(line)
    return "\n".join(keep) + "\n", moved


def append_archive(path: Path, title: str, lines: list):
    """Append moved lines to an archive file under a dated heading."""
    with path.open("a", encoding="utf-8") as fh:
        fh.write(f"\n## {title} — archived {datetime.date.today().isoformat()}\n" + "\n".join(lines) + "\n")


def main():
    """Plan or apply the trim."""
    ap = argparse.ArgumentParser(description="es-orchestrator archive trimming")
    ap.add_argument("--repo", type=Path, default=Path("."))
    ap.add_argument("--plan-id", required=True)
    ap.add_argument("--session", type=int, required=True, help="the session that is ending")
    ap.add_argument("--keep-sessions", type=int, default=2, help="ledger sessions kept live")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    d = a.repo / ".superpowers" / "sdd" / a.plan_id
    handoff, progress = d / "ORCHESTRATOR_HANDOFF.md", d / "progress.md"
    for needed in (handoff, progress):
        if not needed.is_file():
            sys.exit(f"not found: {needed}. Check --repo / --plan-id.")
    new_h, moved_h = trim_handoff(handoff.read_text(encoding="utf-8"))
    new_p, moved_p = trim_progress(progress.read_text(encoding="utf-8"), a.session - a.keep_sessions)
    print(f"handoff: {len(moved_h)} lines to archive · progress: {len(moved_p)} ledger lines to archive")
    if not a.apply or not (moved_h or moved_p):
        print("dry run — re-run with --apply to move them" if not a.apply else "nothing to move")
        return
    stamp = f"{datetime.date.today().isoformat()}s{a.session}"
    for f in (handoff, progress):
        shutil.copy2(f, f.with_name(f"{f.name}.bak-{stamp}"))
    if moved_h:
        append_archive(d / f"archive-ORCHESTRATOR_HANDOFF-through-s{a.session}.md", "LIVE STATUS blocks", moved_h)
        handoff.write_text(new_h, encoding="utf-8")
    if moved_p:
        append_archive(d / f"archive-progress-through-s{a.session}.md", "Ledger lines", moved_p)
        progress.write_text(new_p, encoding="utf-8")
    print(f"applied; backups *.bak-{stamp}")


if __name__ == "__main__":
    main()
