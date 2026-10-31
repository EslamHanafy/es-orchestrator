# Shared stack: several trees, one machine (containers, databases, gates)

Read this when two or more trees (the main checkout, parallel-pair worktrees, lane worktrees) gate or run E2E against ONE
container stack on one machine. Each rule is the fix for a failure that really happened; the reason follows it in *italics*.
The backend profile ships it ready to wire: the `pre-shared-stack` gate snippet, its helpers (`stack_lock.sh`, `run_slot.sh`,
self-tests, `shared-stack.env`, a test-DB compose file, `testdb_conn.sh`) copied into `$W/helpers/` by `scaffold.py`.

## 1. Shared-stack safety

- **Compose calls from a worktree name their services and add `--no-deps`.** *A bare `up` recreates the shared database
  whenever that tree's compose config hash differs from the running container's, which kills every other tree's tests.*
- **Fail fast when the shared database is unhealthy**, and start the base stack only from the MAIN tree. *A worktree that
  starts it bakes its own env file and bind mounts into a container every tree uses.*
- **Restore with `--wait`, and hand the lock over only after the restored service is healthy.** *Releasing while the app
  still migrates or registers jobs let the next holder recreate it mid-boot (stale scheduler locks, crash loops).*
- **Restore from the MAIN tree, rebuilt (`--build`), with a pinned compose project (`-p`).** *The E2E `up --build` left the
  worktree's image on the shared tag; a restore run from the worktree brought every tree back on that worktree's code and env.*
- **Every exit path after the stop restores**, an interrupt or a failed check included (mark "started" before the stop).
  *A gate killed while it waited for scheduler locks left the base app stopped and released the lock.*
- **A proxy re-resolves after a swap** (nginx: `upstream { zone <name> 64k; server <svc>:<port> resolve; }` + one
  `resolver`), **or is restarted after it.** *A static upstream keeps the old container's IP: 502 until someone restarts it.*
- **Never edit or `cp` over a bash script that may be running; write the new version beside it and `mv` it into place.**
  *bash reads a script while it runs; an in-place change makes a running gate execute half-old, half-new lines.*

## 2. Lock narrowing

- Build, format, lint and style run **unlocked**. *They never touch the stack; locking them was pure queue time.*
- Unit tests take **no stack lock** once they have their own test database (§3).
- Only **shared ensure-ups** (a short lock wrapped around one command, skipped when the service is already healthy) and
  **E2E** hold the stack lock. *A unit gate that always took the lock for an ensure-up queued behind every E2E run again.*

## 3. Test-only database

- Its **own compose project, container name and loopback port**. *The main project's `up` can then never touch it.*
- **Durability off** (`fsync`, `synchronous_commit`, `full_page_writes`). *The data is disposable; create + migrate is much faster.*
- **Planner settings IDENTICAL to the main database** (e.g. `random_page_cost`, `effective_cache_size`). *EXPLAIN-based tests
  failed without them: the planner chose sequential scans the real database never picks.*
- **`max_connections` sized to the slot cap** (slots × measured peak per gate + headroom). *Two gates plus an E2E backend
  passed the shared database's limit and failed with "too many clients", which looked like a code fault.*
- The compose file is **the MAIN tree's copy, started with `--no-recreate`**. *Every tree starts the same container, and no
  gate replaces it under another gate's run.*
- A **generated, gitignored password** (`openssl rand`, mode 600) **exported through the environment**, never printed.
- A **helper prints the connection string** for focused runs (`testdb_conn.sh`). *Otherwise people point focused runs at
  the shared database and bring back the contention.*
- When the test DB cannot start, **fail and skip the test phase**. *The harness silently fell back to the shared database.*

## 4. DB sentinel (one gate line per heavy phase)

Record the container start time and the database server's start time before the phase (for E2E: before the stop, compared
after the restore, since the swap is where a shared DB gets recreated), sample the connection count every second, then compare
and grep the phase logs for terminated / recovering / refused / too-many-connections errors (`57P01`, `57P02`, `57P03`,
`53300`, "Connection refused"). One line:
restart → FAIL naming the cause; killed connections → FAIL with the count and the peak; identity unreadable → **FAIL
("blind")**, never a pass. *Without it a restart mid-run shows up as red tests that look like code faults; a sentinel that
passes when it read nothing verifies nothing.*

## 5. Run slots (machine-wide cap of heavy phases)

- One **shared library** (`run_slot.sh`) used by the gate and every script; **cap 2** by default (`ES_RUN_SLOTS`). *Two gates
  plus E2E on one laptop exhausted memory and connections; a fixed, proven cap beats load-based guesses.*
- **Slot BEFORE lock**, never the reverse; a process that holds (or nests in) the stack lock is **refused** a slot instead of
  waiting. *Holder-waits-for-slot plus slot-holder-waits-for-lock is a deadlock.*
- **Stale takeover is race-safe**: rename the slot to a private name, judge it again, put it back if its holder is alive.
  *Two waiters that both `rm` + `mkdir` a stale slot ran three heavy phases at once.*
- **Process-start-time check**, not only `kill -0`. *A reused pid made a dead holder look alive forever.*
- **Ownerless grace** (a slot dir without an owner file is stale only after ~30 s). *That is an acquirer between `mkdir` and
  its owner write, not a crash.*
- **Release on lock failure** (and in the EXIT trap chain). *A timed-out lock wait otherwise kept the slot until the pid died.*
- **One stale-breaker at a time** (a takeover mutex dir). *With three waiters, one moved aside a slot another had just re-taken.*
- **An unwritable slot or lock root fails at once.** *It looked like "busy" and the gate waited silently for two hours.*
- Acceptance proofs before relying on a new cap: peak connections ≤ 70 % of `max_connections` during 2 parallel gates; a swap
  (restore) watched in both logs; three gates at once → the third waits; a SIGKILLed holder's slot is taken over.

## 6. FIFO stack lock

Tickets (`<epoch>-<pid>` files in `<lock>.queue/`) served oldest first, each with the holder's process start time; dead or
pid-reused tickets are pruned; `bash stack_lock.sh status` prints the holder and the queue. *Polling with a random winner
starved lanes for hours, and nobody could see who was waiting.* The lock installs its EXIT trap while queued: set
`STACK_LOCK_EXIT_PREFIX` to your cleanup BEFORE acquiring, so that trap runs it first (the snippet sets `'set +u; cleanup'`).
*Re-chaining only after the acquire lost the gate's cleanup for an interrupt while queued.*

## 7. Job-scheduler lock pre-check before an E2E boot

Stop the running app **gracefully** (the scheduler releases its locks on shutdown), then wait — bounded and printed — only
while a lock row is **younger than the scheduler's lock timeout**. A check that cannot read the table fails the E2E phase. Never delete lock rows by hand (that is a direct DB change).
*A recreated app crashed on another instance's fresh lock rows; "wait for an empty table" waited for rows that never expire.*

## 8. Measure the payoff

The gate prints `test phase: N s` (and `e2e phase: N s`). A tooling extra is kept only when this number (or a proof log)
shows a payoff. *A template database for test leases was built, reviewed and measured: no gain, a real concurrency risk —
removed.* Record "dropped, no measured gain" as a ruling so nobody rebuilds it.

## 9. Tooling changes follow code discipline

Gate scripts, helpers, compose files and proxies are code: change them **one step at a time, each with its proof log**
(`runs/<task>/<step>.log`), then a **fresh strong-model review of the tooling diff and the proofs** before any gate relies on
it. Gate scripts survive signals and missing settings: long steps run background + wait so a signal is handled at once, a TERM
stops the running command before its slot is freed, cleanup ignores further signals and runs with `set +u`, the restore
runs shielded (own session, hard timeout) because compose re-enables SIGINT, and required
settings are checked before anything is stopped. *A second Ctrl-C killed a restore mid-build and the lock was released anyway.*
A sentinel matches database-shaped errors only. *A bare "Connection refused" pattern failed passing gates on curl output.* Repo files (compose, proxy config, Dockerfile, test support) go through lane batches with a FULL review; the orchestrator
edits only its own gitignored gate files. *The first tooling review found a sentinel that passed blind, a restore on the skip
path and a trap chain broken by the new lock — all invisible in green gate runs.* Gate probes follow env-name renames: grep the
gate for every renamed key. *A readiness probe still read a renamed key, and E2E silently never ran through the gate.*

## Wiring (backend profile)

1. `EXTRA_GATES: ["pre-shared-stack"]` (instead of `pre-stack-lock`) → scaffold copies the snippet and `$W/helpers/`.
2. Edit `$W/helpers/shared-stack.env` (names, ports, the E2E up/restore commands, planner settings copied from the main DB)
   and `$W/helpers/docker-compose.testdb.yml` (engine + version identical to the stack's). Point the test harness at the env
   var named in `SS_TESTDB_ENV_NAME`.
3. Run `bash $W/helpers/stack_lock_selftest.sh` and `bash $W/helpers/run_slot_selftest.sh`, then the proofs of §5 with logs, then
   the tooling review of §9. Record the result as a decision row.
4. Repo scripts that touch the stack (`run_e2e.sh`, load tests) source the same helpers: slot first, then the lock.
