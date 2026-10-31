#!/usr/bin/env bash
# =============================================================================
# stack_lock_selftest.sh — Self-test of stack_lock.sh in the same folder (no Docker)
#
# Usage:
#   bash <plan dir>/helpers/stack_lock_selftest.sh
#
# Every case uses a PRIVATE lock directory inside a temp folder, never the real stack lock. Each lock holder is its own
# bash process (the holder pid is $$, unique per process), so the cases behave like real concurrent runs.
#
# Cases:
#   1  two concurrent acquirers serialise (their hold intervals do not overlap) and the lock is gone afterwards
#   2  a lock whose holder pid is dead is broken and taken
#   3  a live foreign holder is reported on stderr, the wait times out, and the lock is NOT broken
#   4  re-entrancy: a child of the holder acquires and releases as a no-op, and the lock still belongs to the parent
#   5  release by a process that is not the holder is refused, and the lock stays
#   6  the EXIT trap releases the lock when the holder exits without an explicit release
#   7  a holder interrupted by SIGTERM or SIGINT releases the lock (the lock's INT/TERM trap exits, EXIT releases)
#   8  three waiters queued behind a holder take the lock in arrival order (their hold intervals follow each other)
#   9  a queued waiter that is killed (SIGKILL) is skipped: its ticket is pruned and the next waiter gets the lock
#  10  a waiter that times out leaves no ticket in the queue
#  11  `status` lists the holder and the queue in order; a waiter stopped by SIGTERM withdraws its ticket
#  12  a ticket whose pid now belongs to another live process (start time differs: pid reuse) is pruned, while a ticket
#      of a live waiter with its true start time is kept
#
# Exit status: 0 when every case passes, 1 when any case fails.
# =============================================================================

set -uo pipefail

SELFTEST_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=stack_lock.sh
source "$SELFTEST_SCRIPT_DIR/stack_lock.sh"

# Test tuning: a short poll and timeouts keep the self-test fast; the hold time is long enough for an overlap to show.
SELFTEST_POLL_SEC=1
SELFTEST_HOLD_SEC=2
SELFTEST_TIMEOUT_SEC=60
SELFTEST_SHORT_TIMEOUT_SEC=2
# Seconds a foreign holder sleeps (it is killed at the end of its case).
SELFTEST_FOREIGN_SLEEP_SEC=60
# FIFO cases: the first holder keeps the lock this long, so every waiter queues before it lets go.
SELFTEST_FIFO_HOLD_SEC=8
# FIFO cases: seconds between two arrivals. Ticket names have whole seconds, so arrivals must be more than one second apart
# for their order to show in the names.
SELFTEST_ARRIVAL_GAP_SEC=2
# Polling for a condition another process must reach: this many tries, this many seconds apart (about 5 s in all).
SELFTEST_WAIT_TRIES=50
SELFTEST_WAIT_STEP_SEC=0.1
# Case 12: epoch part of a planted ticket name (older than any real ticket) and a start time no live process can have.
SELFTEST_OLD_TICKET_EPOCH=1
SELFTEST_FOREIGN_START="Thu Jan  1 00:00:00 1970"
SELFTEST_PASS=0
SELFTEST_FAIL=0
# Private scratch folder, its lock directory, the queue directory beside it, the helper the child processes source, the
# foreign holder's pid, and the pids of the waiters a case started (stopped by selftest_stop_waiters).
SELFTEST_TMP="$(mktemp -d)"
SELFTEST_LOCK_DIR="$SELFTEST_TMP/lock"
SELFTEST_QUEUE_DIR="$SELFTEST_LOCK_DIR$STACK_LOCK_QUEUE_SUFFIX"
SELFTEST_HELPER="$SELFTEST_SCRIPT_DIR/stack_lock.sh"
SELFTEST_FOREIGN_PID=""
SELFTEST_WAITER_PIDS=""

export ES_STACK_LOCK_DIR="$SELFTEST_LOCK_DIR"
export ES_STACK_LOCK_POLL_SECONDS="$SELFTEST_POLL_SEC"
export ES_STACK_LOCK_TIMEOUT_SECONDS="$SELFTEST_TIMEOUT_SEC"
export SELFTEST_TMP SELFTEST_HELPER
# The self-test must not inherit a holder from an outer run, which would look like re-entrancy.
unset ES_STACK_LOCK_OWNER_PID

# -----------------------------------------------------------------------------
# selftest_cleanup
# Purpose: EXIT trap: stops the foreign holder and the waiters, if any are running, and removes the private scratch folder.
# Args: None
# -----------------------------------------------------------------------------
selftest_cleanup() {
  selftest_stop_foreign
  selftest_stop_waiters
  rm -rf "$SELFTEST_TMP"
}
trap selftest_cleanup EXIT

# -----------------------------------------------------------------------------
# selftest_now
# Purpose: Prints the current time with sub-second precision (python3 is already a dependency of the test tooling).
# Args: None
# Outputs: Epoch seconds with fraction on stdout.
# -----------------------------------------------------------------------------
selftest_now() {
  python3 -c 'import time; print(time.time())'
}

# -----------------------------------------------------------------------------
# selftest_record <case name> <status>
# Purpose: Prints one PASS or FAIL line for a case and counts it.
# Args: $1 - case name, $2 - the case's exit status (0 = pass)
# -----------------------------------------------------------------------------
selftest_record() {
  if [ "$2" -eq 0 ]; then
    SELFTEST_PASS=$((SELFTEST_PASS + 1))
    echo "PASS  $1"
  else
    SELFTEST_FAIL=$((SELFTEST_FAIL + 1))
    echo "FAIL  $1"
  fi
}

# -----------------------------------------------------------------------------
# selftest_reset
# Purpose: Clears the private lock directory, its queue, the waiters and any foreign holder before a case, so cases never
#          see each other's state (a leftover ticket of a live process would block the queue of the next case).
# Args: None
# -----------------------------------------------------------------------------
selftest_reset() {
  selftest_stop_foreign
  selftest_stop_waiters
  rm -rf "$SELFTEST_LOCK_DIR" "$SELFTEST_QUEUE_DIR"
}

# -----------------------------------------------------------------------------
# selftest_stop_foreign
# Purpose: Kills the foreign holder process started by a case (no-op when none is running).
# Args: None
# -----------------------------------------------------------------------------
selftest_stop_foreign() {
  if [ -n "$SELFTEST_FOREIGN_PID" ]; then
    kill "$SELFTEST_FOREIGN_PID" 2>/dev/null || true
    wait "$SELFTEST_FOREIGN_PID" 2>/dev/null || true
    SELFTEST_FOREIGN_PID=""
  fi
}

# -----------------------------------------------------------------------------
# selftest_stop_waiters
# Purpose: Kills the waiter processes a case started and still tracks (no-op for the ones already reaped).
# Args: None
# -----------------------------------------------------------------------------
selftest_stop_waiters() {
  local pid
  for pid in $SELFTEST_WAITER_PIDS; do
    kill -KILL "$pid" 2>/dev/null || true
    wait "$pid" 2>/dev/null || true
  done
  SELFTEST_WAITER_PIDS=""
}

# -----------------------------------------------------------------------------
# selftest_plant_owner <label> <pid>
# Purpose: Writes an owner file into the private lock directory, creating the directory first. Used to simulate a
#          holder without running a real acquirer.
# Args: $1 - owner label, $2 - holder pid
# -----------------------------------------------------------------------------
selftest_plant_owner() {
  mkdir -p "$SELFTEST_LOCK_DIR"
  printf 'tree=selftest\nlabel=%s\npid=%s\nstarted_utc=selftest\n' "$1" "$2" > "$SELFTEST_LOCK_DIR/owner"
}

# -----------------------------------------------------------------------------
# selftest_plant_ticket <pid> <process start time>
# Purpose: Writes a queue ticket for <pid> with the oldest possible name, as a waiter would, but with the given start
#          time: the true one simulates a live waiter, another one simulates a waiter whose pid was reused.
# Args: $1 - pid, $2 - process start time written into the ticket
# -----------------------------------------------------------------------------
selftest_plant_ticket() {
  local name
  name=$(printf "%0${STACK_LOCK_TICKET_EPOCH_WIDTH}d%s%0${STACK_LOCK_TICKET_PID_WIDTH}d" \
    "$SELFTEST_OLD_TICKET_EPOCH" "$STACK_LOCK_TICKET_SEP" "$1")
  mkdir -p "$SELFTEST_QUEUE_DIR"
  printf 'tree=selftest\nlabel=planted\npid=%s\nqueued_utc=selftest\nproc_start=%s\n' "$1" "$2" \
    > "$SELFTEST_QUEUE_DIR/$name"
}

# -----------------------------------------------------------------------------
# selftest_start_foreign <label>
# Purpose: Starts a live process (a sleep) and plants a lock owned by it: a live foreign holder.
# Args: $1 - owner label of the foreign holder
# Outputs: Sets SELFTEST_FOREIGN_PID.
# -----------------------------------------------------------------------------
selftest_start_foreign() {
  sleep "$SELFTEST_FOREIGN_SLEEP_SEC" &
  SELFTEST_FOREIGN_PID=$!
  selftest_plant_owner "$1" "$SELFTEST_FOREIGN_PID"
}

# -----------------------------------------------------------------------------
# selftest_holder_is <label>
# Purpose: True when the private lock is held by the owner with this label (used as a poll condition).
# Args: $1 - owner label
# Returns: 0 when it is, 1 otherwise.
# -----------------------------------------------------------------------------
selftest_holder_is() {
  [ "$(_stack_lock_read_field "$SELFTEST_LOCK_DIR" label)" = "$1" ]
}

# -----------------------------------------------------------------------------
# selftest_has_ticket_for <pid>
# Purpose: True when the private queue holds a ticket of this pid (the ticket name ends with the padded pid).
# Args: $1 - waiter pid
# Returns: 0 when there is such a ticket, 1 otherwise.
# -----------------------------------------------------------------------------
selftest_has_ticket_for() {
  local suffix
  suffix=$(printf "%s%0${STACK_LOCK_TICKET_PID_WIDTH}d" "$STACK_LOCK_TICKET_SEP" "$1")
  ls -1 "$SELFTEST_QUEUE_DIR" 2>/dev/null | grep -q -e "$suffix\$"
}

# -----------------------------------------------------------------------------
# selftest_queue_empty
# Purpose: True when the private queue directory has no ticket (or does not exist).
# Args: None
# Returns: 0 when empty, 1 otherwise.
# -----------------------------------------------------------------------------
selftest_queue_empty() {
  [ -z "$(ls -A "$SELFTEST_QUEUE_DIR" 2>/dev/null)" ]
}

# -----------------------------------------------------------------------------
# selftest_poll <command> [args...]
# Purpose: Re-runs a condition until it holds, at most SELFTEST_WAIT_TRIES times, SELFTEST_WAIT_STEP_SEC apart.
# Args: the command line of the condition
# Returns: 0 when the condition held, 1 when it never did.
# -----------------------------------------------------------------------------
selftest_poll() {
  local tries=0
  until "$@"; do
    [ "$tries" -lt "$SELFTEST_WAIT_TRIES" ] || return 1
    sleep "$SELFTEST_WAIT_STEP_SEC"
    tries=$((tries + 1))
  done
}

# -----------------------------------------------------------------------------
# selftest_check_fifo <record file>...
# Purpose: Checks the hold intervals of holder.sh records in the given order: each hold must start after the one before
#          it ended, so the lock went to the processes in exactly the order they were named.
# Args: one record file per holder, in arrival order
# Returns: 0 when the holds follow each other, 1 otherwise (also when a record is missing).
# -----------------------------------------------------------------------------
selftest_check_fifo() {
  python3 - "$@" <<'PY'
import sys

def span(path):
    # One line: "start end" in epoch seconds, written by holder.sh.
    with open(path, encoding="utf-8") as handle:
        return tuple(float(value) for value in handle.read().split())

spans = [span(path) for path in sys.argv[1:]]
# Arrival order: every hold starts only after the one before it ended, so the lock went to the waiters in this order.
in_order = all(following[0] >= previous[1] for previous, following in zip(spans, spans[1:]))
sys.exit(0 if in_order else 1)
PY
}

# -----------------------------------------------------------------------------
# selftest_write_scripts
# Purpose: Writes the child scripts the cases run as separate processes. Each one sources the helper and acts as a lock
#          holder, a nested child or a parent; their exit status and records are what the cases check.
# Args: None
# Outputs: holder.sh, child.sh, parent.sh and looper.sh in the private scratch folder.
# -----------------------------------------------------------------------------
selftest_write_scripts() {
  cat > "$SELFTEST_TMP/holder.sh" <<'HOLDER'
#!/usr/bin/env bash
# Args: <helper> <label> <record-file> <hold-seconds>. Takes the lock, holds it, records "start end", releases.
source "$1"
stack_lock_acquire "$2" || exit 1
start=$(python3 -c 'import time; print(time.time())')
sleep "$4"
end=$(python3 -c 'import time; print(time.time())')
printf '%s %s\n' "$start" "$end" > "$3"
stack_lock_release
HOLDER
  cat > "$SELFTEST_TMP/child.sh" <<'CHILD'
#!/usr/bin/env bash
# Args: <helper>. Acquires and releases the lock that the parent holds: both must be no-ops (exit 0).
source "$1"
stack_lock_acquire "child" || exit 1
stack_lock_release || exit 1
exit 0
CHILD
  cat > "$SELFTEST_TMP/parent.sh" <<'PARENT'
#!/usr/bin/env bash
# Args: <helper> <result-file>. Holds the lock, runs child.sh under it, records "child-status owner-label", releases.
source "$1"
stack_lock_acquire "parent" || exit 1
bash "$SELFTEST_TMP/child.sh" "$1"
child_status=$?
owner=$(sed -n 's/^label=//p' "$ES_STACK_LOCK_DIR/owner")
printf '%s %s\n' "$child_status" "$owner" > "$2"
stack_lock_release
PARENT
  cat > "$SELFTEST_TMP/looper.sh" <<'LOOPER'
#!/usr/bin/env bash
# Args: <helper> <ready-file>. Takes the lock, signals readiness, then waits in short sleeps until it is signalled (bash
# runs a trap only between commands, so short sleeps keep the reaction fast).
source "$1"
stack_lock_acquire "looper" || exit 1
: > "$2"
while :; do sleep 0.2; done
LOOPER
}

# -----------------------------------------------------------------------------
# case_two_acquirers_serialise
# Purpose: Case 1. Two holder processes take the same lock at once; their [start, end] intervals must not overlap, and the
#          lock must be gone once both have finished (the release really happened).
# Returns: 0 on pass, 1 on fail.
# -----------------------------------------------------------------------------
case_two_acquirers_serialise() {
  local a_record="$SELFTEST_TMP/a.times" b_record="$SELFTEST_TMP/b.times"
  bash "$SELFTEST_TMP/holder.sh" "$SELFTEST_HELPER" A "$a_record" "$SELFTEST_HOLD_SEC" &
  bash "$SELFTEST_TMP/holder.sh" "$SELFTEST_HELPER" B "$b_record" "$SELFTEST_HOLD_SEC" &
  wait
  [ ! -d "$SELFTEST_LOCK_DIR" ] || return 1
  python3 - "$a_record" "$b_record" <<'PY'
import sys

def span(path):
    # One line: "start end" in epoch seconds, written by holder.sh.
    with open(path, encoding="utf-8") as handle:
        start, end = (float(value) for value in handle.read().split())
    return start, end

a_start, a_end = span(sys.argv[1])
b_start, b_end = span(sys.argv[2])
# Serialised means one hold ends before the other one starts.
sys.exit(0 if (b_start >= a_end or a_start >= b_end) else 1)
PY
}

# -----------------------------------------------------------------------------
# case_dead_pid_lock_is_broken
# Purpose: Case 2. The lock names a pid that has already exited. A new holder must break it and take the lock, and then
#          release it.
# Returns: 0 on pass, 1 on fail.
# -----------------------------------------------------------------------------
case_dead_pid_lock_is_broken() {
  local dead_pid result="$SELFTEST_TMP/stale.result" status
  sleep 0 &
  dead_pid=$!
  wait "$dead_pid"
  selftest_plant_owner "ghost" "$dead_pid"
  bash "$SELFTEST_TMP/holder.sh" "$SELFTEST_HELPER" after-stale "$result" 0
  status=$?
  [ "$status" -eq 0 ] && [ -f "$result" ] && [ ! -d "$SELFTEST_LOCK_DIR" ]
}

# -----------------------------------------------------------------------------
# case_live_foreign_holder_is_reported
# Purpose: Case 3. A live foreign holder keeps the lock. The waiter must time out (non-zero), print the holder's label on
#          stderr, and leave the lock in place with the foreign owner.
# Returns: 0 on pass, 1 on fail.
# -----------------------------------------------------------------------------
case_live_foreign_holder_is_reported() {
  local out status
  selftest_start_foreign "foreign-run"
  out=$( export ES_STACK_LOCK_TIMEOUT_SECONDS="$SELFTEST_SHORT_TIMEOUT_SEC"; stack_lock_acquire "waiter" 2>&1 )
  status=$?
  [ "$status" -ne 0 ] || return 1
  [[ "$out" == *"label=foreign-run"* ]] || return 1
  [ -d "$SELFTEST_LOCK_DIR" ] || return 1
  [ "$(sed -n 's/^pid=//p' "$SELFTEST_LOCK_DIR/owner")" = "$SELFTEST_FOREIGN_PID" ]
}

# -----------------------------------------------------------------------------
# case_nested_child_is_noop
# Purpose: Case 4. A parent holds the lock and runs a child process under it. The child's acquire and release must both
#          succeed without waiting, and the owner must still be the parent when the child is done.
# Returns: 0 on pass, 1 on fail.
# -----------------------------------------------------------------------------
case_nested_child_is_noop() {
  local result="$SELFTEST_TMP/parent.result"
  ES_STACK_LOCK_TIMEOUT_SECONDS="$SELFTEST_SHORT_TIMEOUT_SEC" bash "$SELFTEST_TMP/parent.sh" "$SELFTEST_HELPER" "$result"
  # A waiting child would have hit the short timeout and reported status 1, so "0 parent" proves a true no-op.
  [ "$(cat "$result" 2>/dev/null)" = "0 parent" ] && [ ! -d "$SELFTEST_LOCK_DIR" ]
}

# -----------------------------------------------------------------------------
# case_release_by_non_holder_is_refused
# Purpose: Case 5. A process that does not hold the lock calls release while a live foreign holder owns it. The call must
#          be refused (non-zero) and the lock must stay with the foreign owner.
# Returns: 0 on pass, 1 on fail.
# -----------------------------------------------------------------------------
case_release_by_non_holder_is_refused() {
  selftest_start_foreign "foreign-run"
  if stack_lock_release 2>/dev/null; then
    return 1
  fi
  [ -d "$SELFTEST_LOCK_DIR" ] && [ "$(sed -n 's/^pid=//p' "$SELFTEST_LOCK_DIR/owner")" = "$SELFTEST_FOREIGN_PID" ]
}

# -----------------------------------------------------------------------------
# case_exit_trap_releases
# Purpose: Case 6. A holder process takes the lock and exits WITHOUT an explicit release. The lock must be held while the
#          process runs (proven by reading its owner) and gone after it exits (the EXIT trap released it).
# Returns: 0 on pass, 1 on fail.
# -----------------------------------------------------------------------------
case_exit_trap_releases() {
  local held
  held=$(bash -c 'source "$1"; stack_lock_acquire "exiter" || exit 1; sed -n "s/^label=//p" "$ES_STACK_LOCK_DIR/owner"' _ "$SELFTEST_HELPER") || return 1
  [ "$held" = "exiter" ] && [ ! -d "$SELFTEST_LOCK_DIR" ]
}

# -----------------------------------------------------------------------------
# selftest_signal_releases <signal>
# Purpose: Starts looper.sh as a lock holder, waits until it holds the lock, sends it <signal> and checks that it exits
#          with the lock's interrupt status and that the lock is gone. Job control (set -m) is on in this subshell only:
#          without it, a background job of a non-interactive shell ignores SIGINT and could not be interrupted at all.
# Args: $1 - signal name (TERM or INT)
# Returns: 0 on pass, 1 on fail.
# -----------------------------------------------------------------------------
selftest_signal_releases() (
  set -m
  local ready="$SELFTEST_TMP/looper.$1.ready" pid status tries=0
  bash "$SELFTEST_TMP/looper.sh" "$SELFTEST_HELPER" "$ready" &
  pid=$!
  # Wait (bounded) until the holder has the lock.
  while [ ! -f "$ready" ] && [ "$tries" -lt 50 ]; do sleep 0.1; tries=$((tries + 1)); done
  [ -f "$ready" ] && [ -d "$SELFTEST_LOCK_DIR" ] || { kill -KILL "$pid" 2>/dev/null; return 1; }
  kill -"$1" "$pid"
  wait "$pid"
  status=$?
  [ "$status" -eq "$STACK_LOCK_SIGNAL_EXIT" ] && [ ! -d "$SELFTEST_LOCK_DIR" ]
)

# -----------------------------------------------------------------------------
# case_signal_releases
# Purpose: Case 7. A holder stopped by SIGTERM, and another stopped by SIGINT, must each release the lock on its way out.
# Returns: 0 on pass, 1 on fail.
# -----------------------------------------------------------------------------
case_signal_releases() {
  selftest_signal_releases TERM || return 1
  selftest_reset
  selftest_signal_releases INT
}

# -----------------------------------------------------------------------------
# case_queued_waiters_take_in_arrival_order
# Purpose: Case 8. A holder keeps the lock while three waiters queue, one every SELFTEST_ARRIVAL_GAP_SEC seconds. The lock
#          must go to them in arrival order: each hold starts only after the one before it ended, the holder being first.
#          The queue must be empty at the end (every ticket was taken).
# Returns: 0 on pass, 1 on fail.
# -----------------------------------------------------------------------------
case_queued_waiters_take_in_arrival_order() {
  local dir="$SELFTEST_TMP/fifo"
  mkdir -p "$dir"
  bash "$SELFTEST_TMP/holder.sh" "$SELFTEST_HELPER" holder "$dir/0.times" "$SELFTEST_FIFO_HOLD_SEC" &
  selftest_poll selftest_holder_is holder || return 1
  bash "$SELFTEST_TMP/holder.sh" "$SELFTEST_HELPER" waiter-1 "$dir/1.times" "$SELFTEST_HOLD_SEC" &
  sleep "$SELFTEST_ARRIVAL_GAP_SEC"
  bash "$SELFTEST_TMP/holder.sh" "$SELFTEST_HELPER" waiter-2 "$dir/2.times" "$SELFTEST_HOLD_SEC" &
  sleep "$SELFTEST_ARRIVAL_GAP_SEC"
  bash "$SELFTEST_TMP/holder.sh" "$SELFTEST_HELPER" waiter-3 "$dir/3.times" "$SELFTEST_HOLD_SEC" &
  wait
  [ ! -d "$SELFTEST_LOCK_DIR" ] || return 1
  selftest_queue_empty || return 1
  selftest_check_fifo "$dir/0.times" "$dir/1.times" "$dir/2.times" "$dir/3.times"
}

# -----------------------------------------------------------------------------
# case_killed_waiter_is_skipped
# Purpose: Case 9. A holder keeps the lock. Waiter B queues and is killed with SIGKILL, so it cannot remove its ticket.
#          Waiter C queues after it. When the holder lets go, B's ticket must be pruned (its pid is dead), C must take the
#          lock, and B must never have held it. The queue must be empty at the end.
# Returns: 0 on pass, 1 on fail.
# -----------------------------------------------------------------------------
case_killed_waiter_is_skipped() {
  local a_record="$SELFTEST_TMP/dead-a.times" b_record="$SELFTEST_TMP/dead-b.times" c_record="$SELFTEST_TMP/dead-c.times"
  local a_pid b_pid c_pid
  bash "$SELFTEST_TMP/holder.sh" "$SELFTEST_HELPER" A "$a_record" "$SELFTEST_FIFO_HOLD_SEC" &
  a_pid=$!
  selftest_poll selftest_holder_is A || return 1
  bash "$SELFTEST_TMP/holder.sh" "$SELFTEST_HELPER" B "$b_record" "$SELFTEST_HOLD_SEC" &
  b_pid=$!
  selftest_poll selftest_has_ticket_for "$b_pid" || return 1
  kill -KILL "$b_pid"
  wait "$b_pid" 2>/dev/null
  # C arrives after B's ticket, so B's dead ticket is the oldest one in the queue when the lock is released.
  sleep "$SELFTEST_ARRIVAL_GAP_SEC"
  bash "$SELFTEST_TMP/holder.sh" "$SELFTEST_HELPER" C "$c_record" "$SELFTEST_HOLD_SEC" &
  c_pid=$!
  wait "$a_pid" || return 1
  wait "$c_pid" || return 1
  [ ! -f "$b_record" ] || return 1
  [ ! -d "$SELFTEST_LOCK_DIR" ] || return 1
  selftest_queue_empty || return 1
  selftest_check_fifo "$a_record" "$c_record"
}

# -----------------------------------------------------------------------------
# case_timed_out_waiter_leaves_no_ticket
# Purpose: Case 10. A foreign holder keeps the lock. A waiter with a short timeout must first queue (its ticket is seen
#          while it waits), then give up with status 1 and leave no ticket behind. The foreign owner stays.
# Returns: 0 on pass, 1 on fail.
# -----------------------------------------------------------------------------
case_timed_out_waiter_leaves_no_ticket() {
  local record="$SELFTEST_TMP/timeout.times" waiter_pid status
  selftest_start_foreign "foreign-run"
  ES_STACK_LOCK_TIMEOUT_SECONDS="$SELFTEST_SHORT_TIMEOUT_SEC" \
    bash "$SELFTEST_TMP/holder.sh" "$SELFTEST_HELPER" timed-out "$record" 0 &
  waiter_pid=$!
  selftest_poll selftest_has_ticket_for "$waiter_pid" || return 1
  wait "$waiter_pid"
  status=$?
  [ "$status" -eq 1 ] || return 1
  [ ! -f "$record" ] || return 1
  selftest_queue_empty && selftest_holder_is foreign-run
}

# -----------------------------------------------------------------------------
# case_status_lists_holder_and_queue
# Purpose: Case 11. With a foreign holder and two queued waiters, `status` must exit 0 and print the holder, then the two
#          waiters oldest first. A waiter stopped by SIGTERM while it waits must withdraw its ticket (the trap runs).
# Returns: 0 on pass, 1 on fail.
# -----------------------------------------------------------------------------
case_status_lists_holder_and_queue() {
  local first_record="$SELFTEST_TMP/status-1.times" second_record="$SELFTEST_TMP/status-2.times"
  local first_pid second_pid out status
  selftest_start_foreign "foreign-run"
  bash "$SELFTEST_TMP/holder.sh" "$SELFTEST_HELPER" queued-one "$first_record" 0 &
  first_pid=$!
  SELFTEST_WAITER_PIDS="$SELFTEST_WAITER_PIDS $first_pid"
  selftest_poll selftest_has_ticket_for "$first_pid" || return 1
  sleep "$SELFTEST_ARRIVAL_GAP_SEC"
  bash "$SELFTEST_TMP/holder.sh" "$SELFTEST_HELPER" queued-two "$second_record" 0 &
  second_pid=$!
  SELFTEST_WAITER_PIDS="$SELFTEST_WAITER_PIDS $second_pid"
  selftest_poll selftest_has_ticket_for "$second_pid" || return 1
  out=$(bash "$SELFTEST_HELPER" status)
  status=$?
  [ "$status" -eq 0 ] || return 1
  [[ "$out" == *"holder: label=foreign-run "* ]] || return 1
  # One pattern for both queue lines: queued-one must be printed on the line before queued-two (oldest first).
  [[ "$out" == *"queue 1: label=queued-one "*"queue 2: label=queued-two "* ]] || return 1
  kill -TERM "$first_pid"
  wait "$first_pid"
  status=$?
  [ "$status" -eq "$STACK_LOCK_SIGNAL_EXIT" ] || return 1
  ! selftest_has_ticket_for "$first_pid"
}

# -----------------------------------------------------------------------------
# case_reused_pid_ticket_is_pruned
# Purpose: Case 12. An unrelated live process (a sleep) has the pid of a planted ticket. First the ticket carries that
#          process's TRUE start time: it is a live waiter, so a newcomer with a short timeout must wait behind it and time
#          out (status 1), and the ticket stays. Then the ticket carries ANOTHER start time (the pid was reused after the
#          real waiter was SIGKILLed): the newcomer must prune it and take the free lock at once. The sleep is untouched.
# Returns: 0 on pass, 1 on fail.
# -----------------------------------------------------------------------------
case_reused_pid_ticket_is_pruned() {
  local blocked="$SELFTEST_TMP/reuse-blocked.times" taken="$SELFTEST_TMP/reuse-taken.times" other_pid status
  sleep "$SELFTEST_FOREIGN_SLEEP_SEC" &
  other_pid=$!
  SELFTEST_WAITER_PIDS="$SELFTEST_WAITER_PIDS $other_pid"
  selftest_plant_ticket "$other_pid" "$(_stack_lock_pid_start "$other_pid")"
  ES_STACK_LOCK_TIMEOUT_SECONDS="$SELFTEST_SHORT_TIMEOUT_SEC" \
    bash "$SELFTEST_TMP/holder.sh" "$SELFTEST_HELPER" behind-live "$blocked" 0 2>/dev/null
  status=$?
  [ "$status" -eq 1 ] && [ ! -f "$blocked" ] || return 1
  selftest_has_ticket_for "$other_pid" || return 1
  selftest_plant_ticket "$other_pid" "$SELFTEST_FOREIGN_START"
  ES_STACK_LOCK_TIMEOUT_SECONDS="$SELFTEST_SHORT_TIMEOUT_SEC" \
    bash "$SELFTEST_TMP/holder.sh" "$SELFTEST_HELPER" after-reuse "$taken" 0 || return 1
  [ -f "$taken" ] && selftest_queue_empty && _stack_lock_pid_alive "$other_pid"
}

# -----------------------------------------------------------------------------
# selftest_run_case <case name> <case function>
# Purpose: Resets the private state, runs one case and records its outcome.
# Args: $1 - case name shown in the output, $2 - case function
# -----------------------------------------------------------------------------
selftest_run_case() {
  selftest_reset
  "$2"
  selftest_record "$1" $?
}

# -----------------------------------------------------------------------------
# main
# Purpose: Writes the child scripts, runs the twelve cases in order and prints the summary.
# Returns: 0 when every case passes, 1 otherwise.
# -----------------------------------------------------------------------------
main() {
  selftest_write_scripts
  selftest_run_case "1 two concurrent acquirers serialise" case_two_acquirers_serialise
  selftest_run_case "2 dead-pid stale lock is broken" case_dead_pid_lock_is_broken
  selftest_run_case "3 live foreign holder is reported, not broken" case_live_foreign_holder_is_reported
  selftest_run_case "4 nested child is a no-op (re-entrant)" case_nested_child_is_noop
  selftest_run_case "5 release by non-holder is refused" case_release_by_non_holder_is_refused
  selftest_run_case "6 EXIT trap releases the lock" case_exit_trap_releases
  selftest_run_case "7 SIGTERM / SIGINT release the lock" case_signal_releases
  selftest_run_case "8 queued waiters take the lock in arrival order" case_queued_waiters_take_in_arrival_order
  selftest_run_case "9 killed queued waiter is skipped" case_killed_waiter_is_skipped
  selftest_run_case "10 timed-out waiter leaves no ticket" case_timed_out_waiter_leaves_no_ticket
  selftest_run_case "11 status lists holder and queue" case_status_lists_holder_and_queue
  selftest_run_case "12 ticket of a reused pid is pruned" case_reused_pid_ticket_is_pruned
  echo ""
  echo "stack_lock_selftest: $SELFTEST_PASS passed, $SELFTEST_FAIL failed"
  [ "$SELFTEST_FAIL" -eq 0 ]
}

main
