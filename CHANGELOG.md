# Changelog

## 1.2.2

Fixes from the second, third and fourth fresh reviews (of 1.2.1 and two 1.2.2 drafts). Regression tests cover the
sentinel pattern, the login check, signals during build / restore / tests, run_timeout.py, the ensure-up lock wait and the
slot release / mutex break; the `ln` password, the empty `SS_MAIN_ROOT` check, the sampler pid removal and the
background polls were checked by hand only. Verified end to end on real Docker (postgres + backend containers): unit
tests on the test DB, E2E swap and restore, Ctrl-C and TERM mid-E2E.

### Fixed
- DB sentinel matches the server's own message texts (any driver prefix: psql, JDBC, Npgsql, node-pg, pgx, lib/pq,
  psycopg, SQLAlchemy, asyncpg; incl. a crash `WARNING` and "not yet accepting connections"), so "Connection refused" in
  test output, `:53300:` or a number no longer fails a passing gate.
- The test-DB login check gives the drop-the-volume advice only on a real password mismatch (`28P01`); other errors are shown.
- Cleanup ignores further INT/TERM/HUP, and the restore + proxy restart run `shielded` (own session, hard timeout
  `SS_RESTORE_TIMEOUT_SEC`), so a second Ctrl-C cannot kill compose mid-restore (Go re-enables SIGINT); a Ctrl-C during the
  normal restore no longer runs it twice.
- Cleanup stops and waits (bounded) for every RUNNING job before the slot is freed; finished jobs are never signalled.
- The E2E stop and build and the test-DB up run through `timed` (background + wait, under `GATE_TIMEOUT`); a wrapped
  ensure-up runs background + wait, with only the ensure-up itself under `GATE_TIMEOUT` (the lock wait keeps the lock's
  timeout); lock/slot/job-lock polls sleep in the background. A signal is handled at once.
- `run_timeout.py`: signals are blocked around the start, so an early TERM never orphans the command; a signal with no
  timeout exits 143 at once (polling wait, EPERM on a zombie group handled); the command gets default INT/QUIT/TERM/HUP; new
  `--shield` mode (a shielded timeout still stops the command gracefully). `timed` commands read /dev/null.
- Sampler pid files are removed after the stop, so exit cleanup never signals a reused pid.
- Run slots: a slot is released even when the gate is stopped between its mkdir and its owner write; a leaked takeover
  mutex is broken by rename-then-recheck and never put back inside a re-created one.
- Test-DB password created with an atomic `ln`; an empty `SS_MAIN_ROOT` fails the settings check.
- Cleanup messages ("base app restored", "could not restore — run …") reach the user even when the exit trap fires
  during a step whose output goes to a temp file (found in a real-Docker smoke run).
- A group TERM/HUP during the normal restore no longer releases the lock mid-restore; a TERM during a slow ensure-up
  frees the stack lock with the gate; the sentinel also catches "remaining connection slots are reserved" and no longer
  flags the app's own idle-timeout disconnects.

## 1.2.1

Fixes from a fresh review of the 1.2.0 tooling; each proved defect has a regression test with a fake `docker`.

### Fixed
- `pre-shared-stack`: an interrupt or failure after the app stop always restores (the "started" mark now comes before the stop).
- `pre-shared-stack`: the base app is restored from the MAIN tree, rebuilt, with a pinned compose project; `SS_MAIN_ROOT` is exported.
- Gate cleanup is kept while queued for the stack lock (`STACK_LOCK_EXIT_PREFIX`), so an interrupt there frees the slot.
- Missing `shared-stack.env` settings fail up front, and cleanup runs with `set +u`, so the lock and slot are always released.
- `check.sh`: SIGTERM/INT/HUP stop the running test or e2e command before its slot is freed (`timed` waits in the background).
- DB sentinel: also fails on `57P02`/`57P03`/refused connections, covers the whole E2E swap, has a bounded sampler stop, and its
  sampler no longer keeps the gate's output open after the gate dies.
- Run slots and stack lock: an unwritable root fails at once; stale slot takeovers are serialised by a mutex.
- Slot released on a lock timeout; a failing job-lock check fails E2E; the test-DB password is created race-free and checked
  against the volume; `scaffold.py` rejects helper names that are not plain file names.

## 1.2.0

From a 4-lane wave on one shared Docker stack (a .NET backend, 2026-10-31). Every rule carries its reason.

### Added
- `references/shared-stack.md`: shared-stack safety (named services + `--no-deps`, fail fast on an unhealthy shared DB, health-waited
  restore before the lock changes hands, proxy re-resolve, swap running scripts with `mv`), lock narrowing, a test-only database,
  the DB sentinel, run slots, the FIFO stack lock, the job-scheduler lock pre-check, the "test phase: N s" timer and the
  measured-payoff rule, and tooling-as-code discipline.
- `references/parallel-lanes.md`: a wave of up to 4 lanes on worktree tracks (fact map, ≈30-min batches in disjoint-file groups +
  a sequential tail, scope growth is an owner question, per-lane ownership, commit the plan amendment before any brief, run
  folders before dispatch) and the E2E-frequency setup question.
- Final whole-task review after all waves and the clean-up (`pairing-and-review.md`), and red tests through the production path
  for money rules.
- Backend `pre-shared-stack` gate snippet + `profiles/backend/helpers/` (`stack_lock.sh` FIFO lock with `status`, `run_slot.sh`,
  both self-tests, `shared-stack.env`, `docker-compose.testdb.yml`, `testdb_conn.sh`); `scaffold.py` copies the files a snippet
  names on its `# requires-helpers:` line into the plan's `helpers/`.
- `check.sh` hooks `gate_before_tests` / `gate_after_tests` / `gate_before_e2e` / `gate_after_e2e` / `gate_on_exit`
  (`GATE_SKIP_TESTS` / `GATE_SKIP_E2E` stop a phase), and `test phase: N s` / `e2e phase: N s` lines.
- Self-check lessons: renamed settings in gate probes, timing windows without slow steps, tooling discipline (generic);
  cross-section settings validation, production-path money tests, complete test seeds (backend).

### Changed
- `pre-stack-lock` no longer locks build/format/lint: it takes the lock just before the tests or E2E.

## 1.1.0

### Added
- **Run modes**: `plan`, `orchestrate`, `review`, `commit` and `full` (`references/run-modes.md`). Each runs only its stage and
  records the stage reached (`status.py --set-stage`); `NEXT_SESSION_PROMPT.md` and the END STATE carry the mode.
- **Parallel pairs** in git worktrees (`scripts/worktree.py`, `references/parallel-pairs.md`): add, snapshot, land, remove, list.
  New answer keys `PARALLEL_PAIRS`, `WORKTREE_DIR`, `WORKTREE_SETUP_CMD`, `WORKTREE_COPY_FILES`.
- `scripts/doctor.py` (health check), `detect_stack.py --draft-answers` (quick setup), `scaffold.py --upgrade-static`.
- Gate: per-command timeout (`GATE_TIMEOUT_SECONDS`), temp-dir cleanup and fallback, secret scan of added lines,
  code-only forbidden-pattern rules (`~name`), placeholder parity and `.properties`/`.strings` support in `locale_parity.py`.
- Owner-report marker (`<A>+<B>-OWNER_REPORT_SENT`) checked by `commit`; stale-run detection in `status.py`.
- Reviewer agent installs per project (`.claude/agents/`) by default (`REVIEWER_AGENT_SCOPE`).
- Install with `npx skills add EslamHanafy/es-orchestrator`; tests and CI; host fallbacks documented.

### Fixed
- `SKILL.md` frontmatter is valid YAML (the `skills` CLI skipped the skill before).
- Scripts no longer hard-code `~/.claude/skills/es-orchestrator` (`$ES` = the install directory).
- `status.py`: tasks were double-counted (task headings plus their checkbox steps); a run id matched other ids by prefix
  (`B1` vs `B10`); clear errors instead of tracebacks.
- `scaffold.py`: `PLAN_ID` is validated (no path traversal), unknown answer keys are reported, `--only` rejects unknown files.
- `archive.py`: clear error when the handoff has no LIVE STATUS heading.
- `detect_stack.py`: Xcode projects are detected, plain Dart packages are not treated as Flutter apps, plans are found by directory.
- Mobile `generated-up-to-date` snippet is opt-in (no project-specific default); the `null-assert` rule no longer fires on strings.

- Hardening from an independent review: `land` is byte-exact (CRLF, non-UTF-8, binary), refuses edits made after the snapshot,
  compares file names case-insensitively and reverts a half-applied patch; re-adding a batch id archives the old attempt;
  `remove --all` skips already-removed worktrees; git output is pinned (`core.quotepath=off`, `a/ b/` prefixes) so non-ASCII file
  names and `diff.noprefix` no longer hide files from the gate; untracked files without a trailing newline cannot swallow the next
  file's header; a gates.d snippet that does not parse fails the gate (and the mobile `core-imports-features` snippet now parses
  under macOS bash 3.2); `check.sh` refuses to gate a different checkout than it was started in; `run_timeout.py` forwards
  SIGTERM/SIGINT/SIGHUP and always kills the whole group; the secret scan is case-insensitive and catches unquoted `.env` lines;
  `status.py` treats only a leading done-word/✅ as done, counts signal-less tasks as open, ignores fenced code, matches legacy
  hyphenated report names exactly and says so when it recognises no tasks.

### Removed
- Two empty placeholder files in `profiles/generic/` (missing profile files are skipped).

## 1.0.0
- Initial release.
