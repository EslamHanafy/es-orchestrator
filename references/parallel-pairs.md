# Parallel pairs (A and B at the same time, in git worktrees)

A normal pair runs A, then B on top of A's uncommitted work. A **parallel pair** runs A and B at the same time, each in
its own git worktree, so a pair takes the time of the slower batch instead of the sum. Everything after the
implementation is unchanged: the two batches are **landed** on the main tree together, gated as a pair, reviewed once
and committed. Only the orchestrator runs `scripts/worktree.py`; implementers and reviewers never touch worktrees.

```
HEAD (clean) ──▶ worktree A ──▶ implementer A ──▶ snapshot A ─┐
             └─▶ worktree B ──▶ implementer B ──▶ snapshot B ─┴─▶ land (A+B uncommitted in the main tree)
                                                   ──▶ combined gate ──▶ review ──▶ commit ──▶ remove worktrees
```

## When a pair may run in parallel

All of these must hold. If one fails, run the pair sequentially (the default behaviour).

1. `PARALLEL_PAIRS` is not `off` (answers.json / decision O-8), and the user did not ask for sequential.
2. The survey tags the pair `PARALLEL-OK`: **disjoint file sets** (also no shared generated file, lockfile, route table,
   DI module, locale file or barrel file that both would edit) and **no dependency** (B does not need A's code).
3. The previous pair is **committed**: the main tree has no uncommitted tracked changes. Worktrees start from HEAD,
   so unreviewed work in the main tree would be invisible to them. (Writing the next briefs while a review runs is
   still fine; only the dispatch waits for the commit.)
4. **No shared runtime resource**: the two batches' tests and live checks do not use the same port, database, container
   stack or emulator. If they must, enable the `pre-stack-lock` gate snippet (serialises gates) and give each brief its own ports
   in the `{{PORTS_AND_SERVICES}}` line, or run sequentially.
5. The worktree **setup command** is known (`WORKTREE_SETUP_CMD`: `npm ci`, `flutter pub get`, …), or the stack needs none.
   Without installed dependencies a fresh worktree cannot build.
6. Both lanes have quota for two simultaneous sessions. When one lane would have to fall back mid-run, say so to the owner.

Mark eligible pairs in the survey's BATCH ORDER (`B14 + B15 — PARALLEL-OK, disjoint: …`). The orchestrator makes this call
(a technical ruling); it is not owner-reserved, except copying real config into a worktree (below).

## Steps

`$ES` = the skill directory (SKILL.md). `$W` = `.superpowers/sdd/<PLAN_ID>`. All commands run from the repo root.

1. **Check** `git status --porcelain --untracked-files=no` is empty and re-check both briefs against the current code (BASE = HEAD).
2. **Create the worktrees**
   `python3 $ES/scripts/worktree.py add --repo . --plan-id <PLAN_ID> --id <A> --id <B>`
   It creates `<WORKTREE_DIR>/<PLAN_ID>/<id>` on branch `es/<plan-lowercase>/<id-lowercase>` at HEAD, copies `WORKTREE_COPY_FILES`
   (local, untracked config the build needs), runs `WORKTREE_SETUP_CMD`, and writes `runs/<id>/WORKTREE.json`.
   Exit 3 means the setup command failed (see `runs/<id>/worktree-setup.log`): fix it or fall back to sequential.
3. **Fill the briefs** with the `<worktree>` block (and delete the `<pair>` block): `{{TREE}}` = the worktree path,
   `{{BRANCH}}`, `{{PARTNER_ID}}`, `{{PORTS_AND_SERVICES}}`. Gate lines use absolute plan paths and `CHECK_ROOT={{TREE}}`; `check.sh` refuses to run inside a different checkout than the one it
   would gate, so a forgotten `CHECK_ROOT` cannot silently gate the main tree.
4. **Dispatch both at once**: `touch $W/runs/<id>/START` for each, then each lane command with `--cd <worktree>` and
   `run_in_background`. Never poll; wait for both notifications. Save each report to `runs/<id>/REPORT.md` and check it
   for completeness as usual.
5. **Snapshot each** finished batch: `python3 $ES/scripts/worktree.py snapshot --repo . --plan-id <PLAN_ID> --id <id>`.
   It makes one WIP commit on the throw-away branch, writes `runs/<id>/files.txt` and `SNAPSHOT.json`, and checks that the
   implementer's `gate.log` is newer than every file it changed (`gate_fresh`). Files that were already in the worktree
   before the implementer started (setup output, copied config) are never part of a snapshot.
6. **Land both**: `python3 $ES/scripts/worktree.py land --repo . --plan-id <PLAN_ID> --id <A> --id <B>`.
   It refuses (and changes nothing) when HEAD moved since the worktrees were cut (exit 2), the file sets overlap (exit 2;
   compared case-insensitively), the gate evidence is stale or the worktree was edited after its snapshot (exit 4), or a patch does
   not apply (exit 5). Patches are applied byte-exact (CRLF, binary and non-UTF-8 files survive) and are reverted as a whole if
   anything fails half-way. On success the main tree holds A+B
   uncommitted, the same state a sequential pair ends in. **Never hand-merge a refusal**: fall back to the sequential pair
   (below).
7. **Combined gate**, by the orchestrator, in the foreground or detached: `$W/check.sh <BASE> > $W/runs/<B>/integration-gate.log 2>&1`
   (BASE = the commit before A). Neither implementer saw the combined tree, so this gate is the first run of A+B together.
   If it fails, treat it as a fix round (below).
8. **Review** the pair as usual with the `PARALLEL PAIR` block of `review-full-template.md` filled in. The freshness anchor is
   `integration-gate.log`; file ownership comes from `files.txt`; the reviewer judges cross-batch interactions.
9. **Owner report, commit, bookkeeping** exactly as in the session loop. Then **clean up**:
   `python3 $ES/scripts/worktree.py remove --repo . --plan-id <PLAN_ID> --all` (it refuses un-landed worktrees, and worktrees edited after their snapshot, without `--force`; re-adding an id archives the
   old attempt's run files into `runs/<id>/previous-<time>/`).

## Fix rounds

The reviewer's fix brief applies to the combined tree, so a fix round runs in the **main tree**, like a sequential
pair's: resume the implementer's session with `--cd <main tree>` if its CLI allows changing the directory, otherwise start a
new session with the fix brief (it states the context), then a NEW reviewer. Worktrees are not reused after landing.
An integration-gate failure that is clearly one batch's fault goes to that batch's lane the same way.

## Fall back to sequential

Use it whenever `land` refuses, a worktree is broken, or the owner says so: land what is clean
(`land --id A` alone works when A is fine), then run B as a normal batch in the main tree on top of the uncommitted A
(re-check B's brief first; BASE stays the commit before A), discard B's worktree with `remove --force --id B`, and note the
fallback in the ledger. Nothing is lost: B's WIP branch can be inspected until it is removed.

## Cost and safety notes

- Two sessions use quota at the same time, and two fix rounds cannot overlap. A parallel pair saves wall-clock time, not tokens.
- `WORKTREE_COPY_FILES` copies local untracked files (for example `.env`, `google-services.json`) into a directory next to the
  repo. That touches real config, which is an owner-reserved category: get an O-row for the exact file list at setup. Never
  copy secrets that the build does not need.
- Worktrees live outside the repo by default (`<repo>.worktrees/<PLAN_ID>/<id>`), so analyzers, IDEs and `git status` in the main
  checkout never see them. Delete leftovers with `worktree.py remove --all --force`; `doctor.py` and `status.py` list them.
- The WIP branches `es/<plan-lowercase>/<id-lowercase>` are local scratch. They are never pushed and never merged; only the landed diff is committed.
- Do not stash, checkout or reset in the main tree while worktrees exist. The existing git-safety rules apply unchanged.
- This is not the long-lived "worktree track" of `git-and-gates.md` (a branch worked on for days with merge gates): a parallel pair lives
  for one batch and lands as an uncommitted diff.
