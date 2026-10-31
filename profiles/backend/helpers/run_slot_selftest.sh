#!/usr/bin/env bash
# =============================================================================
# run_slot_selftest.sh — Self-test of run_slot.sh in the same folder (no Docker)
#
# Usage:
#   bash <plan dir>/helpers/run_slot_selftest.sh
#
# Every case uses a PRIVATE slot directory inside a temp folder, never the real run slots. Each holder is its own bash
# process (its pid is unique), so the cases behave like real concurrent runs.
#
# Cases:
#   1  three holders with a cap of two: no more than two hold a slot at once, and the slots are gone afterwards
#   2  a slot whose holder pid is dead is taken over, and two waiters on that one slot never overlap (cap 1)
#   3  a slot whose pid is alive but belongs to another process (start time differs: pid reuse) is taken over
#   4  a slot with NO owner file is kept inside the grace; once it is older than the grace it is taken over
#   5  a child of a live holder (ES_RUN_SLOT_OWNER_PID) is a no-op: it takes no slot and releases nothing
#   6  an acquire by a process that holds the stack lock is refused with exit 2, and takes no slot
#   7  `status` lists the live slots and prints nothing once every slot is free
#   8  an acquire by a child of a live stack-lock holder (it nests in the lock) is refused with exit 2, and takes no slot
#
# Exit status: 0 when every case passes, 1 when any case fails.
# =============================================================================

set -uo pipefail

SELFTEST_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SELFTEST_HELPER="$SELFTEST_SCRIPT_DIR/run_slot.sh"

# Test tuning: a short poll and short timeouts keep the self-test fast; the hold time is long enough for an overlap to show.
SELFTEST_POLL_SEC=1
SELFTEST_HOLD_SEC=2
SELFTEST_DEFAULT_CAP=2
SELFTEST_DEFAULT_TIMEOUT_SEC=60
SELFTEST_SHORT_TIMEOUT_SEC=2
# Owner start time that no live process can have (case 3: a live pid that belongs to another process).
SELFTEST_FOREIGN_START="Thu Jan  1 00:00:00 1970"
# Modification time far older than the owner-less grace (case 4), in `touch -t` format.
SELFTEST_OLD_MTIME="202001010000"
SELFTEST_PASS=0
SELFTEST_FAIL=0
# Private scratch folder, the slot directory the cases use, the holder script, and the pids of the background holders.
SELFTEST_TMP="$(mktemp -d)"
SELFTEST_SLOTS="$SELFTEST_TMP/slots"
SELFTEST_HOLDER="$SELFTEST_TMP/holder.sh"
SELFTEST_CHILD_PIDS=""

export ES_RUN_SLOT_DIR="$SELFTEST_SLOTS"
export ES_RUN_SLOT_POLL_SECONDS="$SELFTEST_POLL_SEC"
# The self-test must not inherit a holder from an outer run, which would look like nesting or the stack lock.
unset ES_RUN_SLOT_OWNER_PID ES_STACK_LOCK_OWNER_PID

# -----------------------------------------------------------------------------
# selftest_cleanup
# Purpose: EXIT trap: stops the background holders still running and removes the private scratch folder.
# Args: None
# -----------------------------------------------------------------------------
selftest_cleanup() {
  selftest_cleanup_children
  rm -rf "$SELFTEST_TMP"
}
trap selftest_cleanup EXIT

# -----------------------------------------------------------------------------
# selftest_set_cap <n>
# Purpose: Sets how many slots the cases see (ES_RUN_SLOTS) for the processes they start.
# Args: $1 - slot count
# -----------------------------------------------------------------------------
selftest_set_cap() {
  export ES_RUN_SLOTS="$1"
}

# -----------------------------------------------------------------------------
# selftest_set_timeout <seconds>
# Purpose: Sets how long a waiter may wait for a slot before it gives up (ES_RUN_SLOT_TIMEOUT_SECONDS).
# Args: $1 - timeout in seconds
# -----------------------------------------------------------------------------
selftest_set_timeout() {
  export ES_RUN_SLOT_TIMEOUT_SECONDS="$1"
}

# -----------------------------------------------------------------------------
# selftest_reset
# Purpose: Clears the slot directory, the background holders and the settings of the previous case, so cases never see each
#          other's slots (a leftover live owner would block the next case).
# Args: None
# -----------------------------------------------------------------------------
selftest_reset() {
  selftest_cleanup_children
  rm -rf "$SELFTEST_SLOTS"
  selftest_set_cap "$SELFTEST_DEFAULT_CAP"
  selftest_set_timeout "$SELFTEST_DEFAULT_TIMEOUT_SEC"
}

# -----------------------------------------------------------------------------
# selftest_cleanup_children
# Purpose: Kills and reaps the background holders a case started (no-op when none is running).
# Args: None
# -----------------------------------------------------------------------------
selftest_cleanup_children() {
  local pid
  for pid in $SELFTEST_CHILD_PIDS; do
    kill "$pid" 2>/dev/null || true
    wait "$pid" 2>/dev/null || true
  done
  SELFTEST_CHILD_PIDS=""
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
# selftest_write_holder
# Purpose: Writes the holder script every background holder runs: it takes a slot, holds it for the given time, records its
#          interval (start and end, epoch seconds) and releases the slot.
# Args: None (writes $SELFTEST_HOLDER)
# -----------------------------------------------------------------------------
selftest_write_holder() {
  cat > "$SELFTEST_HOLDER" <<'HOLDER'
#!/usr/bin/env bash
# Arguments: $1 run_slot.sh path, $2 label, $3 record file, $4 hold seconds.
source "$1" || exit 1
run_slot_acquire "$2" || exit 1
start="$(python3 -c 'import time; print(time.time())')"
sleep "$4"
end="$(python3 -c 'import time; print(time.time())')"
run_slot_release
printf '%s %s\n' "$start" "$end" > "$3"
HOLDER
}

# -----------------------------------------------------------------------------
# selftest_start_holder <label> <record file> <hold seconds>
# Purpose: Starts one holder process in the background and remembers its pid for selftest_join_holders.
# Args: $1 - label, $2 - record file, $3 - hold seconds
# -----------------------------------------------------------------------------
selftest_start_holder() {
  bash "$SELFTEST_HOLDER" "$SELFTEST_HELPER" "$1" "$2" "$3" > "$2.out" 2>&1 &
  SELFTEST_CHILD_PIDS="$SELFTEST_CHILD_PIDS $!"
}

# -----------------------------------------------------------------------------
# selftest_join_holders
# Purpose: Waits for every background holder a case started, then forgets their pids.
# Args: None
# -----------------------------------------------------------------------------
selftest_join_holders() {
  local pid
  for pid in $SELFTEST_CHILD_PIDS; do
    wait "$pid" 2>/dev/null || true
  done
  SELFTEST_CHILD_PIDS=""
}

# -----------------------------------------------------------------------------
# selftest_dead_pid
# Purpose: Prints the pid of a process that has already exited (a pid that is dead on this machine).
# Args: None
# Outputs: Pid on stdout.
# -----------------------------------------------------------------------------
selftest_dead_pid() {
  local pid
  sleep 0 &
  pid=$!
  wait "$pid" 2>/dev/null || true
  echo "$pid"
}

# -----------------------------------------------------------------------------
# selftest_plant_owner <slot number> <pid> <label> <proc_start or empty>
# Purpose: Creates a slot directory with an owner file that names a holder, as a crashed or foreign run would have left it.
# Args: $1 - slot number, $2 - holder pid, $3 - label, $4 - recorded start time (empty: no proc_start line)
# -----------------------------------------------------------------------------
selftest_plant_owner() {
  local dir="$SELFTEST_SLOTS/slot.$1"
  mkdir -p "$dir"
  printf 'pid=%s\ntree=%s\nlabel=%s\nstarted_utc=%s\n' "$2" "$SELFTEST_TMP" "$3" "2020-01-01T00:00:00Z" > "$dir/owner"
  [ -z "$4" ] || printf 'proc_start=%s\n' "$4" >> "$dir/owner"
}

# -----------------------------------------------------------------------------
# selftest_max_overlap <record file...>
# Purpose: Prints the most holds that were open at the same instant, from the "start end" record files.
# Args: one or more record files
# Outputs: The maximum overlap on stdout.
# -----------------------------------------------------------------------------
selftest_max_overlap() {
  python3 - "$@" <<'PY'
import sys

spans = []
for path in sys.argv[1:]:
    # One line per holder: "start end" in epoch seconds, written by the holder script.
    with open(path, encoding="utf-8") as handle:
        start, end = (float(value) for value in handle.read().split())
    spans.append((start, end))
# At each hold's start instant, count the holds that are open then; the largest count is the overlap.
print(max((sum(1 for s, e in spans if s <= t < e) for t, _ in spans), default=0))
PY
}

# -----------------------------------------------------------------------------
# case_cap_respected
# Purpose: Case 1. Three holders share a cap of two: never more than two hold at once, all three run, and the slot directory
#          is empty afterwards (every holder released).
# Returns: 0 on pass, 1 on fail.
# -----------------------------------------------------------------------------
case_cap_respected() {
  selftest_set_cap 2
  selftest_start_holder A "$SELFTEST_TMP/cap-a.times" "$SELFTEST_HOLD_SEC"
  selftest_start_holder B "$SELFTEST_TMP/cap-b.times" "$SELFTEST_HOLD_SEC"
  selftest_start_holder C "$SELFTEST_TMP/cap-c.times" "$SELFTEST_HOLD_SEC"
  selftest_join_holders
  [ -f "$SELFTEST_TMP/cap-a.times" ] && [ -f "$SELFTEST_TMP/cap-b.times" ] && [ -f "$SELFTEST_TMP/cap-c.times" ] || return 1
  [ "$(selftest_max_overlap "$SELFTEST_TMP/cap-a.times" "$SELFTEST_TMP/cap-b.times" "$SELFTEST_TMP/cap-c.times")" -le 2 ] || return 1
  [ -z "$(ls -A "$SELFTEST_SLOTS" 2>/dev/null)" ]
}

# -----------------------------------------------------------------------------
# case_dead_holder_slot_taken
# Purpose: Case 2. The only slot names a dead pid. Two waiters (cap 1) both get it in turn, never at once: a stale slot is
#          taken over exactly once.
# Returns: 0 on pass, 1 on fail.
# -----------------------------------------------------------------------------
case_dead_holder_slot_taken() {
  selftest_set_cap 1
  selftest_plant_owner 1 "$(selftest_dead_pid)" "ghost" ""
  selftest_start_holder A "$SELFTEST_TMP/dead-a.times" "$SELFTEST_HOLD_SEC"
  selftest_start_holder B "$SELFTEST_TMP/dead-b.times" "$SELFTEST_HOLD_SEC"
  selftest_join_holders
  [ -f "$SELFTEST_TMP/dead-a.times" ] && [ -f "$SELFTEST_TMP/dead-b.times" ] || return 1
  [ "$(selftest_max_overlap "$SELFTEST_TMP/dead-a.times" "$SELFTEST_TMP/dead-b.times")" -eq 1 ]
}

# -----------------------------------------------------------------------------
# case_reused_pid_slot_taken
# Purpose: Case 3. The slot names a LIVE pid (this self-test's own), but the recorded start time is another process's: the
#          pid was reused, so the slot is stale and a waiter takes it at once (the short timeout would fail it otherwise).
# Returns: 0 on pass, 1 on fail.
# -----------------------------------------------------------------------------
case_reused_pid_slot_taken() {
  selftest_set_cap 1
  selftest_set_timeout "$SELFTEST_SHORT_TIMEOUT_SEC"
  selftest_plant_owner 1 "$$" "reused" "$SELFTEST_FOREIGN_START"
  bash "$SELFTEST_HOLDER" "$SELFTEST_HELPER" "reuser" "$SELFTEST_TMP/reuse.times" 0 > "$SELFTEST_TMP/reuse.out" 2>&1
  [ -f "$SELFTEST_TMP/reuse.times" ]
}

# -----------------------------------------------------------------------------
# case_ownerless_slot_grace
# Purpose: Case 4. A slot with no owner file is an acquirer between mkdir and the owner write while it is young: a waiter
#          must not take it (its short timeout expires). Once it is older than the grace, the waiter takes it.
# Returns: 0 on pass, 1 on fail.
# -----------------------------------------------------------------------------
case_ownerless_slot_grace() {
  selftest_set_cap 1
  selftest_set_timeout "$SELFTEST_SHORT_TIMEOUT_SEC"
  mkdir -p "$SELFTEST_SLOTS/slot.1"
  bash "$SELFTEST_HOLDER" "$SELFTEST_HELPER" "young" "$SELFTEST_TMP/young.times" 0 > "$SELFTEST_TMP/young.out" 2>&1 && return 1
  [ ! -f "$SELFTEST_TMP/young.times" ] || return 1
  touch -t "$SELFTEST_OLD_MTIME" "$SELFTEST_SLOTS/slot.1"
  bash "$SELFTEST_HOLDER" "$SELFTEST_HELPER" "old" "$SELFTEST_TMP/old.times" 0 > "$SELFTEST_TMP/old.out" 2>&1
  [ -f "$SELFTEST_TMP/old.times" ]
}

# -----------------------------------------------------------------------------
# case_nested_child_is_noop
# Purpose: Case 5. A live holder (a sleeping process) owns slot 1. A child that names it in ES_RUN_SLOT_OWNER_PID takes
#          no slot (still one slot directory) and its release leaves the holder's slot in place.
# Returns: 0 on pass, 1 on fail.
# -----------------------------------------------------------------------------
case_nested_child_is_noop() {
  local holder_pid child_status slot_count
  selftest_set_cap 2
  sleep 60 &
  holder_pid=$!
  SELFTEST_CHILD_PIDS="$SELFTEST_CHILD_PIDS $holder_pid"
  selftest_plant_owner 1 "$holder_pid" "parent" ""
  ES_RUN_SLOT_OWNER_PID="$holder_pid" bash -c 'source "$1"; run_slot_acquire nested-child; status=$?; run_slot_release; exit $status' _ "$SELFTEST_HELPER" \
    > "$SELFTEST_TMP/nested.out" 2>&1
  child_status=$?
  slot_count="$(ls -A "$SELFTEST_SLOTS" | wc -l | tr -d ' ')"
  [ "$child_status" -eq 0 ] && [ "$slot_count" -eq 1 ] && [ -f "$SELFTEST_SLOTS/slot.1/owner" ]
}

# -----------------------------------------------------------------------------
# case_lock_held_refused
# Purpose: Case 6. A process that holds the stack lock (ES_STACK_LOCK_OWNER_PID is its own pid) is refused a slot: exit 2,
#          a message, and no slot taken.
# Returns: 0 on pass, 1 on fail.
# -----------------------------------------------------------------------------
case_lock_held_refused() {
  local out status
  out="$(bash -c 'source "$1"; ES_STACK_LOCK_OWNER_PID=$$; run_slot_acquire lock-holder; echo SHOULD-NOT-REACH' _ "$SELFTEST_HELPER" 2>&1)"
  status=$?
  [ "$status" -eq 2 ] || return 1
  [[ "$out" == *refused* ]] || return 1
  [[ "$out" != *SHOULD-NOT-REACH* ]] || return 1
  [ -z "$(ls -A "$SELFTEST_SLOTS" 2>/dev/null)" ]
}

# -----------------------------------------------------------------------------
# case_lock_held_by_parent_refused
# Purpose: Case 8. A child whose ES_STACK_LOCK_OWNER_PID names a LIVE holder (a sleeping process) nests in the stack lock,
#          so it is refused a slot like the holder itself: exit 2, a message, and no slot taken.
# Returns: 0 on pass, 1 on fail.
# -----------------------------------------------------------------------------
case_lock_held_by_parent_refused() {
  local holder_pid out status
  sleep 60 &
  holder_pid=$!
  SELFTEST_CHILD_PIDS="$SELFTEST_CHILD_PIDS $holder_pid"
  out="$(ES_STACK_LOCK_OWNER_PID="$holder_pid" bash -c 'source "$1"; run_slot_acquire lock-child; echo SHOULD-NOT-REACH' _ "$SELFTEST_HELPER" 2>&1)"
  status=$?
  [ "$status" -eq 2 ] || return 1
  [[ "$out" == *refused* ]] || return 1
  [[ "$out" != *SHOULD-NOT-REACH* ]] || return 1
  [ -z "$(ls -A "$SELFTEST_SLOTS" 2>/dev/null)" ]
}

# -----------------------------------------------------------------------------
# case_status_lists_live_slots
# Purpose: Case 7. `status` prints the live slot and not the stale one; once the live slot is gone it prints nothing.
# Returns: 0 on pass, 1 on fail.
# -----------------------------------------------------------------------------
case_status_lists_live_slots() {
  local out
  selftest_plant_owner 1 "$$" "status-live" ""
  selftest_plant_owner 2 "$(selftest_dead_pid)" "status-dead" ""
  out="$(bash "$SELFTEST_HELPER" status 2>&1)"
  [[ "$out" == *"slot.1: label=status-live "* ]] || return 1
  [[ "$out" != *status-dead* ]] || return 1
  rm -rf "$SELFTEST_SLOTS/slot.1"
  out="$(bash "$SELFTEST_HELPER" status 2>&1)"
  [ -z "$out" ]
}

# -----------------------------------------------------------------------------
# selftest_run_case <case name> <function>
# Purpose: Resets the private state, runs one case and records its result.
# Args: $1 - the case's name for the report, $2 - the case function
# -----------------------------------------------------------------------------
selftest_run_case() {
  selftest_reset
  "$2"
  selftest_record "$1" $?
}

# -----------------------------------------------------------------------------
# selftest_main
# Purpose: Runs every case in order, prints the summary and sets the exit status (0 only when every case passed).
# Args: None
# Returns: 0 when all cases pass, 1 otherwise.
# -----------------------------------------------------------------------------
selftest_main() {
  selftest_write_holder
  selftest_run_case "1 cap respected: three holders, cap 2" case_cap_respected
  selftest_run_case "2 dead holder's slot taken over, waiters never overlap" case_dead_holder_slot_taken
  selftest_run_case "3 reused pid (start time differs) is stale" case_reused_pid_slot_taken
  selftest_run_case "4 owner-less slot: kept in grace, taken after it" case_ownerless_slot_grace
  selftest_run_case "5 nested child is a no-op" case_nested_child_is_noop
  selftest_run_case "6 lock-held acquire refused (exit 2)" case_lock_held_refused
  selftest_run_case "7 status lists live slots only" case_status_lists_live_slots
  selftest_run_case "8 acquire under a live stack-lock holder refused (exit 2)" case_lock_held_by_parent_refused
  echo "run slot selftest: $SELFTEST_PASS passed, $SELFTEST_FAIL failed"
  [ "$SELFTEST_FAIL" -eq 0 ]
}

selftest_main
