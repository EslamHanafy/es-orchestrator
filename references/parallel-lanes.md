# Parallel lanes (a wave of batches across up to 4 worktrees)

A **parallel pair** (`parallel-pairs.md`) runs two batches at once and lands them uncommitted. A **wave of parallel lanes**
goes further: up to 4 worktree tracks, each running its own sequence of pairs (with the usual review and commit per pair on
its track branch), merged back with a merge gate. Use it for a large, mostly independent set of work; it cut one 18-batch
wave from ≈ 9 h serial to ≈ 6 h with 4 lanes. Worktree tracks are the owner's call (`git-and-gates.md`), so ask first.

## 1. Plan the wave

1. **Fact map first** (read-only helper, the orchestrator re-checks every fact that drives a ruling): every item with its
   files (file:line), what it reads and writes, and its dependencies. *Lanes cut from guesses collide on shared files.*
2. Cut **≈ 30-minute batches** (`pairing-and-review.md`) and group them into **parallel groups with disjoint file sets**
   (no shared generated file, lockfile, route table, DI module, locale or barrel file), plus a **sequential tail** for the
   batches that touch shared files or need another lane's result.
3. **Real scope growth is an owner question.** When the fact map turns "1 batch" into 11, show the new list and the time,
   with a recommendation, before cutting lanes. *Silent growth spends the owner's budget without their say.*
4. **Up to 4 worktrees** (more costs more machine and quota than it saves; with a shared stack, see `shared-stack.md`). Write
   the **per-lane ownership** into the plan: lane → its pairs in order → the files it owns. A file belongs to one lane only.
5. **Commit the plan amendment before any brief** (batch list, lanes, ownership, plan size). *Worktrees are cut from HEAD:
   an uncommitted plan is invisible to them, and briefs would cite a plan nobody else can read.*
6. **Create every run folder before dispatch** (`mkdir -p $W/runs/<id>` + `START`). *A lane that finishes before its folder
   exists writes its evidence somewhere else, and file-ownership markers are missing.*

## 2. E2E frequency (a setup question; record the answer as an O-row)

Ask at setup or before the first wave, recommendation first:
- **Touched suites per pair (Recommended)**: the reviewer runs only the E2E suites the pair touches, live.
- **Full suite at merges and at the final gate**: every wave merge and the final gate run all suites.
*Full E2E on every pair serialised all lanes behind one stack; touched suites per pair plus full runs at merges kept the
coverage and removed the queue.*

## 3. Run the wave

- Each lane works its pairs in order on its own track branch, with the normal loop (brief re-check, fresh reviewer, owner
  report, commit). Lanes never edit another lane's files; a needed change there is a DECISION for the orchestrator.
- Heavy phases draw from the shared run slots and the stack lock (`shared-stack.md`), so 4 lanes never run 4 E2E at once.
- **Merge** each track into the work branch when its pairs are committed: merge gate on the merged tree (unit + the touched
  suites), and the **full E2E at the wave merge** (§2). A conflict is resolved by the orchestrator with its own gate run.
- After the last merge: clean up (owner-approved list: `git branch -d` only, worktrees removed, throw-away databases and
  images dropped, real-config copies archived first), then the **final whole-task review** (`pairing-and-review.md`) and the
  final gate.
