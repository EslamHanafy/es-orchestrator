#!/usr/bin/env python3
"""Git worktrees for PARALLEL pairs: batches A and B are implemented at the same time, each in its own worktree.

Usage (the orchestrator runs these; implementers and reviewers never do):
  worktree.py add      --repo . --plan-id P --id A [--id B ...]   create worktrees at HEAD (clean tree required)
  worktree.py snapshot --repo . --plan-id P --id A                commit the worktree's changes as one WIP commit
  worktree.py land     --repo . --plan-id P --id A --id B         apply the snapshots to the main tree, uncommitted
  worktree.py remove   --repo . --plan-id P (--id A ... | --all) [--force]
  worktree.py list     --repo . --plan-id P

Flow: add → dispatch each implementer with `--cd <worktree>` → snapshot each → land both → from then on the main tree
holds A+B uncommitted, exactly like a sequential pair, so the combined gate, the review and the commit are unchanged.
The WIP commits live on throw-away branches `es/<plan>/<id>`; the work branch only ever receives the real commits.

State per batch is kept in <plan>/runs/<id>/: WORKTREE.json (path, branch, base), SNAPSHOT.json (sha, files, whether
the implementer's gate log is newer than every file), files.txt (the batch's changed files, used for pair file
ownership instead of mtimes), LANDED. Settings come from <plan>/config.json (written by scaffold.py):
WORKTREE_DIR, WORKTREE_SETUP_CMD, WORKTREE_COPY_FILES.

Exit codes: 0 ok · 2 usage or precondition · 3 setup command failed (worktree kept) · 4 stale gate evidence ·
5 patches do not apply cleanly (nothing was changed).
"""
import argparse
import datetime
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
BOT = ["-c", "user.name=es-orchestrator", "-c", "user.email=es-orchestrator@localhost"]


def die(message: str, code: int = 2):
    """Print an error and exit with `code` (2 = usage or precondition, see the module docstring)."""
    print(message, file=sys.stderr)
    sys.exit(code)


def now() -> str:
    """Current local time, ISO format, second precision."""
    return datetime.datetime.now().isoformat(timespec="seconds")


# Stable output whatever the user's git config says: real UTF-8 file names, a/ b/ diff prefixes, no external diff tool.
GIT_FLAGS = ["-c", "core.quotepath=off", "-c", "diff.noprefix=false", "-c", "diff.mnemonicPrefix=false",
             "-c", "core.autocrlf=false"]
DIFF_FLAGS = ["--no-ext-diff", "--src-prefix=a/", "--dst-prefix=b/"]


def git(cwd: Path, *args, check: bool = True, stdin: str = None) -> subprocess.CompletedProcess:
    """Run git in `cwd` (text mode); exit with git's message when `check` is set and it fails."""
    out = subprocess.run(["git", *GIT_FLAGS, "-C", str(cwd), *args], capture_output=True, text=True,
                         encoding="utf-8", errors="surrogateescape", input=stdin)
    if check and out.returncode != 0:
        die(f"git {' '.join(args[:3])} failed in {cwd}:\n{out.stderr.strip() or out.stdout.strip()}")
    return out


def git_bytes(cwd: Path, *args, stdin: bytes = None) -> subprocess.CompletedProcess:
    """Run git in `cwd` with raw bytes in and out (patches must survive CRLF and non-UTF-8 content untouched)."""
    return subprocess.run(["git", *GIT_FLAGS, "-C", str(cwd), *args], capture_output=True, input=stdin)


def plan_dir(repo: Path, plan_id: str) -> Path:
    """Return the plan folder, or exit when it does not exist."""
    folder = repo / ".superpowers" / "sdd" / plan_id
    if not folder.is_dir():
        die(f"plan folder not found: {folder}")
    return folder


def config(folder: Path) -> dict:
    """Load <plan>/config.json (written by scaffold.py); empty when absent."""
    try:
        return json.loads((folder / "config.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def check_id(batch: str) -> str:
    """Reject ids that would make an unsafe branch or path."""
    if not ID_RE.fullmatch(batch):
        die(f"invalid batch id '{batch}': use letters, digits, '.', '_' or '-'")
    return batch


def read_json(path: Path) -> dict:
    """Load a JSON file or exit with a hint about the step that writes it."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        die(f"missing or unreadable {path}")


def require_clean(repo: Path):
    """The main tree must have no uncommitted tracked changes (untracked and ignored files are fine)."""
    dirty = git(repo, "status", "--porcelain", "--untracked-files=no").stdout.strip()
    if dirty:
        die("the main tree has uncommitted tracked changes; commit the previous pair first "
                 "(parallel worktrees start from HEAD):\n" + dirty)


def copy_files(repo: Path, target: Path, patterns: list):
    """Copy untracked/ignored files the build needs (e.g. .env, local config) into a new worktree."""
    copied = []
    for pattern in patterns:
        for src in sorted(repo.glob(pattern)):
            dst = target / src.relative_to(repo)
            if src.is_dir():
                shutil.copytree(src, dst, dirs_exist_ok=True)
            elif src.is_file():
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
            else:
                continue
            copied.append(str(src.relative_to(repo)))
    return copied


def cmd_add(a, repo: Path, folder: Path):
    """Create one worktree + branch per id at HEAD, copy local files, run the setup command."""
    require_clean(repo)
    cfg, base = config(folder), git(repo, "rev-parse", "HEAD").stdout.strip()
    root = Path(cfg.get("WORKTREE_DIR") or repo.parent / f"{repo.name}.worktrees") / a.plan_id
    setup = (a.setup_cmd if a.setup_cmd is not None else cfg.get("WORKTREE_SETUP_CMD") or "none").strip()
    status = 0
    for batch in map(check_id, a.id):
        path, branch = root / batch, f"es/{a.plan_id.lower()}/{batch.lower()}"
        if path.exists() or git(repo, "rev-parse", "--verify", "--quiet", branch, check=False).returncode == 0:
            die(f"worktree or branch already exists for {batch} ({path}, {branch}); "
                     "run `worktree.py remove --force --id " + batch + "` first")
        path.parent.mkdir(parents=True, exist_ok=True)
        git(repo, "worktree", "add", "-q", "-b", branch, str(path), base)
        copied = copy_files(repo, path, a.copy or cfg.get("WORKTREE_COPY_FILES", []))
        run = folder / "runs" / batch
        run.mkdir(parents=True, exist_ok=True)
        archive_previous_attempt(run)
        setup_ok = True
        if setup and setup != "none":
            with (run / "worktree-setup.log").open("w", encoding="utf-8") as log:
                setup_ok = subprocess.run(["bash", "-c", setup], cwd=path, stdout=log, stderr=subprocess.STDOUT).returncode == 0
        # Files present before the implementer starts (setup output, copied config) must never enter the snapshot.
        preexisting = [f for f in git(path, "ls-files", "--others", "--exclude-standard").stdout.splitlines() if f]
        info = {"id": batch, "path": str(path), "branch": branch, "base": base, "created": now(),
                "copied": copied, "setup_cmd": setup, "setup_ok": setup_ok, "preexisting_untracked": preexisting}
        (run / "WORKTREE.json").write_text(json.dumps(info, indent=2) + "\n", encoding="utf-8")
        print(f"{batch}: {path} (branch {branch}, base {base[:9]}){'' if setup_ok else '  SETUP FAILED: see worktree-setup.log'}")
        status = status or (0 if setup_ok else 3)
    sys.exit(status)


STALE_RUN_FILES = ("SNAPSHOT.json", "files.txt", "LANDED", "gate.log", "live-checks.log", "result.json", "REPORT.md",
                   "START", "pid")


def archive_previous_attempt(run: Path):
    """Move the files of an earlier attempt at this batch id into previous-<time>/ so they cannot be mistaken for new work."""
    old = [run / n for n in STALE_RUN_FILES if (run / n).exists()]
    if old:
        keep = run / ("previous-" + datetime.datetime.now().strftime("%Y%m%dT%H%M%S"))
        keep.mkdir()
        for f in old:
            shutil.move(str(f), str(keep / f.name))


def worktree_problem(info: dict, snap: dict) -> str:
    """Return why the worktree no longer matches its snapshot (edits or commits after it), or '' when it matches."""
    wt = Path(info["path"])
    if not wt.is_dir():
        return f"worktree missing: {wt}"
    if git(wt, "rev-parse", "HEAD").stdout.strip() != snap["sha"]:
        return "the worktree HEAD moved after the snapshot"
    skip = set(info.get("preexisting_untracked", []))
    entries = [e[3:] for e in git(wt, "status", "--porcelain", "-z", "-uall").stdout.split("\0") if e]
    dirty = [e for e in entries if e not in skip]
    return f"edits after the snapshot: {', '.join(dirty[:5])}" if dirty else ""


def newer_than_gate(root: Path, files: list, gate_log: Path) -> list:
    """Files in the worktree modified after the gate log was written (the implementer's gate must be its last step)."""
    if not gate_log.is_file():
        return ["<no gate.log>"]
    limit = gate_log.stat().st_mtime
    return [f for f in files if (root / f).is_file() and (root / f).stat().st_mtime > limit]


def cmd_snapshot(a, repo: Path, folder: Path):
    """Commit the worktree's changes as one WIP commit and record the files and the gate freshness."""
    batch = check_id(a.id[0])
    run = folder / "runs" / batch
    info = read_json(run / "WORKTREE.json")
    wt = Path(info["path"])
    if not wt.is_dir():
        die(f"worktree missing: {wt}")
    git(wt, "add", "-A")
    skip = info.get("preexisting_untracked", [])
    for i in range(0, len(skip), 100):
        git(wt, "reset", "-q", "--", *skip[i:i + 100], check=False)
    if git(wt, "diff", "--cached", "--quiet", check=False).returncode != 0:
        git(wt, *BOT, "commit", "-q", "--no-verify", "-m", f"wip({batch}): es-orchestrator snapshot")
    elif git(wt, "rev-parse", "HEAD").stdout.strip() == info["base"]:
        die(f"nothing to snapshot in {wt}: no changes since the base commit")
    sha = git(wt, "rev-parse", "HEAD").stdout.strip()
    files = [f for f in git(wt, "diff", "--no-renames", "--name-only", *DIFF_FLAGS, info["base"], sha).stdout.splitlines() if f]
    newer = newer_than_gate(wt, files, run / "gate.log")
    snap = {"id": batch, "sha": sha, "base": info["base"], "files": files, "gate_fresh": not newer,
            "newer_than_gate": newer, "created": now()}
    (run / "SNAPSHOT.json").write_text(json.dumps(snap, indent=2) + "\n", encoding="utf-8")
    (run / "files.txt").write_text("\n".join(files) + "\n", encoding="utf-8")
    print(f"{batch}: snapshot {sha[:9]}, {len(files)} files, gate evidence "
          f"{'fresh' if not newer else 'STALE: ' + ', '.join(newer[:5])}")


def cmd_land(a, repo: Path, folder: Path):
    """Apply the snapshots to the main tree as uncommitted changes; all-or-nothing, byte-exact."""
    require_clean(repo)
    head, batches = git(repo, "rev-parse", "HEAD").stdout.strip(), [check_id(b) for b in a.id]
    snaps = {}
    for batch in batches:
        info, snap = read_json(folder / "runs" / batch / "WORKTREE.json"), read_json(folder / "runs" / batch / "SNAPSHOT.json")
        if info["base"] != head:
            die(f"{batch} was cut from {info['base'][:9]} but HEAD is {head[:9]}; the work branch moved. "
                "Re-run the batch sequentially on the new HEAD (see references/parallel-pairs.md).")
        problem = worktree_problem(info, snap)
        if problem:
            die(f"{batch}: {problem}. Run `worktree.py snapshot --id {batch}` again (after the implementer's final gate run).", 4)
        if not snap["gate_fresh"] and not a.allow_stale:
            die(f"{batch}: the implementer edited after its last gate run ({', '.join(snap['newer_than_gate'][:5])}).", 4)
        snaps[batch] = snap
    seen = {}
    for batch in batches:
        for f in snaps[batch]["files"]:
            key = f.casefold()  # macOS and Windows file systems ignore case
            if key in seen:
                die(f"not disjoint: {f} (also {seen[key][1]}) is changed by both {seen[key][0]} and {batch}; a pair needs "
                    "disjoint files. Run them sequentially.")
            seen[key] = (batch, f)
    patches = {b: git_bytes(repo, "diff", "--binary", *DIFF_FLAGS, snaps[b]["base"], snaps[b]["sha"]).stdout for b in batches}
    for batch in batches:
        check = git_bytes(repo, "apply", "--check", "-", stdin=patches[batch])
        if check.returncode != 0:
            die(f"{batch}: patch does not apply cleanly to the main tree:\n{check.stderr.decode(errors='replace').strip()}", 5)
    applied = []
    for batch in batches:
        result = git_bytes(repo, "apply", "-", stdin=patches[batch])
        if result.returncode != 0:  # should not happen after --check; undo what was applied so nothing is half-landed
            for done in reversed(applied):
                git_bytes(repo, "apply", "-R", "-", stdin=patches[done])
            die(f"{batch}: apply failed after the check passed ({result.stderr.decode(errors='replace').strip()}); "
                "everything applied so far was reverted.", 5)
        applied.append(batch)
    for batch in batches:
        (folder / "runs" / batch / "LANDED").write_text(now() + "\n", encoding="utf-8")
        print(f"{batch}: landed {len(snaps[batch]['files'])} files (uncommitted)")
    print("Next: run the combined gate on the main tree, then dispatch the review (references/parallel-pairs.md).")


def cmd_remove(a, repo: Path, folder: Path):
    """Remove worktrees and their WIP branches once their changes are landed (or with --force)."""
    ids = [p.parent.name for p in sorted((folder / "runs").glob("*/WORKTREE.json"))] if a.all else a.id
    for batch in map(check_id, ids):
        run = folder / "runs" / batch
        info = read_json(run / "WORKTREE.json")
        if info.get("removed"):
            if not a.all:
                print(f"{batch}: already removed")
            continue
        if not a.force:
            if not (run / "LANDED").exists():
                die(f"{batch} is not landed; its changes would be lost. Land it, or pass --force to abandon it.")
            snap = read_json(run / "SNAPSHOT.json")
            problem = worktree_problem(info, snap)
            if problem:
                die(f"{batch}: {problem}; removing it would lose that work. Snapshot and land again, or pass --force.")
        if Path(info["path"]).exists():
            git(repo, "worktree", "remove", "--force", info["path"], check=False)
            shutil.rmtree(info["path"], ignore_errors=True)
        git(repo, "branch", "-D", info["branch"], check=False)
        info["removed"] = now()
        (run / "WORKTREE.json").write_text(json.dumps(info, indent=2) + "\n", encoding="utf-8")
        print(f"{batch}: removed")
    git(repo, "worktree", "prune", check=False)


def cmd_list(a, repo: Path, folder: Path):
    """Print every worktree of this plan with its state."""
    rows = []
    for marker in sorted((folder / "runs").glob("*/WORKTREE.json")):
        info, run = read_json(marker), marker.parent
        state = ("removed" if info.get("removed") else "landed" if (run / "LANDED").exists()
                 else "snapshotted" if (run / "SNAPSHOT.json").exists() else "in progress")
        rows.append({"id": info["id"], "state": state, "path": info["path"], "branch": info["branch"]})
    if a.json:
        print(json.dumps(rows, indent=2))
    for row in rows if not a.json else []:
        print(f"{row['id']}: {row['state']} · {row['path']} · {row['branch']}")
    if not rows and not a.json:
        print("no worktrees")


def main():
    """Parse the command line and dispatch to the sub-command."""
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--repo", type=Path, default=Path("."))
    common.add_argument("--plan-id", required=True)
    common.add_argument("--id", action="append", default=[], help="batch id (repeat for several)")
    ap = argparse.ArgumentParser(description="es-orchestrator parallel-pair worktrees")
    sub = ap.add_subparsers(dest="cmd", required=True)
    add = sub.add_parser("add", parents=[common])
    add.add_argument("--setup-cmd", default=None, help="override WORKTREE_SETUP_CMD")
    add.add_argument("--copy", action="append", default=[], help="glob of local files to copy (repeatable)")
    sub.add_parser("snapshot", parents=[common])
    land = sub.add_parser("land", parents=[common])
    land.add_argument("--allow-stale", action="store_true", help="land although the gate evidence is stale")
    rem = sub.add_parser("remove", parents=[common])
    rem.add_argument("--all", action="store_true")
    rem.add_argument("--force", action="store_true")
    lst = sub.add_parser("list", parents=[common])
    lst.add_argument("--json", action="store_true")
    a = ap.parse_args()
    repo = a.repo.resolve()
    if git(repo, "rev-parse", "--is-inside-work-tree", check=False).returncode != 0:
        die(f"{repo} is not a git repository")
    if a.cmd in ("add", "snapshot", "land") and not a.id:
        die(f"{a.cmd}: pass at least one --id")
    if a.cmd == "snapshot" and len(a.id) != 1:
        die("snapshot takes exactly one --id")
    if a.cmd == "remove" and not (a.all or a.id):
        die("remove: pass --id <batch> or --all")
    {"add": cmd_add, "snapshot": cmd_snapshot, "land": cmd_land, "remove": cmd_remove,
     "list": cmd_list}[a.cmd](a, repo, plan_dir(repo, a.plan_id))


if __name__ == "__main__":
    main()
