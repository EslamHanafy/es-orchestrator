#!/usr/bin/env bash
# =============================================================================
# run_slot.sh — Run slots: at most N heavy test runs at once across every git worktree (es-orchestrator backend profile)
#
# A run slot caps how many heavy phases (a unit-test phase, an E2E phase) run at once on this machine, whatever the tree.
# The slots are shared by check.sh and any script that sources this file, so they all draw from one machine-wide cap.
# Installed by scaffold.py into <plan dir>/helpers/ (the MAIN tree's copy, used by every worktree).
#
# Use it sourced (library) or directly (`status` prints the busy slots; it takes nothing):
#   source <plan dir>/helpers/run_slot.sh
#   run_slot_acquire "<label>"        # waits (bounded) for a free slot; returns 1 on timeout, exits 2 when refused
#   run_slot_release                  # only the holder releases; safe to call more than once; a nested call is a no-op
#   bash <plan dir>/helpers/run_slot.sh status
#
# Contract for scripts:
#   - ORDER RULE: slot first, then the stack lock. A process that already holds the stack lock, or runs under a live holder
#     of it (a child that nests in the lock), is refused a slot (exit 2), so a lock holder never waits for a slot and no two
#     runs can deadlock on (slot, lock).
#   - This library installs NO traps: the stack lock owns EXIT/INT/TERM while it is held. The caller chains
#     run_slot_release into its own EXIT trap AFTER its stack lock release. A process that dies without releasing leaves a
#     slot whose pid is dead, and the next acquirer takes that slot over.
#   - A child started by the holder sees ES_RUN_SLOT_OWNER_PID and becomes a no-op, so nested runs never deadlock.
#   - Bash 3.2 compatible (macOS /bin/bash): no BASHPID, no associative arrays.
#
# Slots are the directories ${ES_RUN_SLOT_DIR:-/tmp/es-run-slots}/slot.<n> for n = 1..ES_RUN_SLOTS (default 2).
# A slot holds an `owner` file:
#   pid=<holder pid>  tree=<repo root>  label=<owner label>  started_utc=<UTC ISO-8601>  proc_start=<holder start time>
# A slot is free when its directory does not exist. A slot is STALE when its holder pid is dead, or when that pid now belongs
# to another process (proc_start differs: a reused pid). A slot with NO owner file is stale only after
# RUN_SLOT_INIT_GRACE_SEC. Only a stale slot is taken over, and only through a rename to a private name that is judged again
# (_run_slot_break_stale), so two waiters can never both take one slot.
# =============================================================================

# Directory holding the slots when ES_RUN_SLOT_DIR is not set.
RUN_SLOT_DEFAULT_DIR="/tmp/es-run-slots"
# Number of slots when ES_RUN_SLOTS is not set.
RUN_SLOT_DEFAULT_COUNT=2
# Name prefix of a slot directory: slot.<n>.
RUN_SLOT_DIR_PREFIX="slot."
# File inside a slot directory that names the holder.
RUN_SLOT_OWNER_FILE="owner"
# Seconds between attempts while every slot is busy (ES_RUN_SLOT_POLL_SECONDS overrides; whole seconds).
RUN_SLOT_DEFAULT_POLL_SEC=5
# Longest wait for a slot in seconds before giving up (ES_RUN_SLOT_TIMEOUT_SECONDS overrides): two hours.
RUN_SLOT_DEFAULT_TIMEOUT_SEC=7200
# An owner-less slot younger than this is an acquirer between mkdir and the owner write, not a crash.
RUN_SLOT_INIT_GRACE_SEC=30
# Exit status of a refused acquire (this process holds the stack lock): a usage error, as in check.sh.
RUN_SLOT_REFUSED_EXIT=2
# Repository root of the tree this run works on (CHECK_ROOT of a worktree gate, else the current checkout), written into
# the owner file.
RUN_SLOT_TREE_ROOT="${CHECK_ROOT:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
# The slot directory this process holds (empty when it holds none).
RUN_SLOT_HELD=""

# -----------------------------------------------------------------------------
# _run_slot_root
# Purpose: Prints the directory that holds the slots. Read at call time so a caller (or the self-test) can redirect it.
# Args: None
# Outputs: Slot root path on stdout.
# -----------------------------------------------------------------------------
_run_slot_root() {
  echo "${ES_RUN_SLOT_DIR:-$RUN_SLOT_DEFAULT_DIR}"
}

# -----------------------------------------------------------------------------
# _run_slot_count
# Purpose: Prints how many slots may be held at once (the cap).
# Args: None
# Outputs: Slot count on stdout.
# -----------------------------------------------------------------------------
_run_slot_count() {
  echo "${ES_RUN_SLOTS:-$RUN_SLOT_DEFAULT_COUNT}"
}

# -----------------------------------------------------------------------------
# _run_slot_path <n>
# Purpose: Prints the directory of slot number <n>.
# Args: $1 - slot number (1-based)
# Outputs: Slot directory path on stdout.
# -----------------------------------------------------------------------------
_run_slot_path() {
  echo "$(_run_slot_root)/$RUN_SLOT_DIR_PREFIX$1"
}

# -----------------------------------------------------------------------------
# _run_slot_now_utc
# Purpose: Prints the current time in UTC, ISO-8601 (written into the owner file and the messages).
# Args: None
# Outputs: Timestamp on stdout.
# -----------------------------------------------------------------------------
_run_slot_now_utc() {
  date -u +"%Y-%m-%dT%H:%M:%SZ"
}

# -----------------------------------------------------------------------------
# _run_slot_read_key <file> <key>
# Purpose: Prints the value of `key=` from a key=value file (nothing when there is no file or no such key).
# Args: $1 - file path, $2 - key name
# Outputs: Value on stdout.
# -----------------------------------------------------------------------------
_run_slot_read_key() {
  [ -f "$1" ] || return 0
  # 2>/dev/null: the file may vanish between the test above and this read (a release): an empty result.
  sed -n "s/^$2=//p" "$1" 2>/dev/null | head -n 1
}

# -----------------------------------------------------------------------------
# _run_slot_pid_alive <pid>
# Purpose: True when <pid> is a live process on this machine. `ps -p` also sees other users' processes.
# Args: $1 - process id (may be empty, which counts as not alive)
# Returns: 0 when alive, 1 otherwise.
# -----------------------------------------------------------------------------
_run_slot_pid_alive() {
  [ -n "$1" ] && ps -p "$1" -o pid= >/dev/null 2>&1
}

# -----------------------------------------------------------------------------
# _run_slot_pid_start <pid>
# Purpose: Prints the start time of a process as `ps` reports it (LC_ALL=C, so every caller formats it the same way),
#          without the padding spaces. A reused pid has a different start time.
# Args: $1 - process id
# Outputs: Start time on stdout (nothing when the process does not exist).
# -----------------------------------------------------------------------------
_run_slot_pid_start() {
  LC_ALL=C ps -p "$1" -o lstart= 2>/dev/null | sed -e 's/^ *//' -e 's/ *$//'
}

# -----------------------------------------------------------------------------
# _run_slot_owner_live <slot dir>
# Purpose: True when the slot's holder is still the process that wrote the owner file: its pid is alive AND its start time
#          is the recorded one (a pid reused by another process is not the holder). An owner file without proc_start is
#          judged by the pid alone.
# Args: $1 - slot directory
# Returns: 0 when live, 1 otherwise.
# -----------------------------------------------------------------------------
_run_slot_owner_live() {
  local owner_file="$1/$RUN_SLOT_OWNER_FILE" pid recorded
  pid="$(_run_slot_read_key "$owner_file" pid)"
  _run_slot_pid_alive "$pid" || return 1
  recorded="$(_run_slot_read_key "$owner_file" proc_start)"
  [ -z "$recorded" ] || [ "$recorded" = "$(_run_slot_pid_start "$pid")" ]
}

# -----------------------------------------------------------------------------
# _run_slot_age_sec <slot dir>
# Purpose: Prints how many seconds ago the slot directory was last modified. GNU stat (-c) and BSD stat (-f) differ, so GNU
#          is tried first: on BSD `stat -c` fails and the BSD form runs.
# Args: $1 - slot directory
# Outputs: Age in seconds on stdout. Returns 1 when the directory cannot be inspected (it vanished meanwhile).
# -----------------------------------------------------------------------------
_run_slot_age_sec() {
  local mtime
  mtime=$(stat -c %Y "$1" 2>/dev/null || stat -f %m "$1" 2>/dev/null) || return 1
  echo $(( $(date +%s) - mtime ))
}

# -----------------------------------------------------------------------------
# _run_slot_is_stale <slot dir>
# Purpose: Decides whether a slot may be taken over. With an owner file: stale when the holder is not live (dead pid or a
#          reused pid). Without one: stale only after RUN_SLOT_INIT_GRACE_SEC, because a live acquirer writes the owner file
#          within milliseconds of its mkdir.
# Args: $1 - slot directory
# Returns: 0 when stale, 1 when live or when it cannot be judged.
# -----------------------------------------------------------------------------
_run_slot_is_stale() {
  local slot="$1" age
  if [ -n "$(_run_slot_read_key "$slot/$RUN_SLOT_OWNER_FILE" pid)" ]; then
    if _run_slot_owner_live "$slot"; then
      return 1
    fi
    return 0
  fi
  age=$(_run_slot_age_sec "$slot") || return 1
  [ "$age" -gt "$RUN_SLOT_INIT_GRACE_SEC" ]
}

# -----------------------------------------------------------------------------
# _run_slot_break_stale <slot dir>
# Purpose: Takes a stale slot out of the way, race-safely. The directory is first RENAMED to a private name, so two waiters
#          that both judged it stale cannot both delete it. The renamed copy is judged again: when a live holder re-created
#          the slot in between, the copy is moved back instead of being deleted.
# Args: $1 - slot directory
# Outputs: A NOTICE on stderr when a stale slot was removed; a WARN when a live slot had to be moved aside.
# Returns: 0 (a live slot is simply left alone; the caller's mkdir decides).
# -----------------------------------------------------------------------------
_run_slot_break_stale() {
  local slot="$1" graveyard
  if [ ! -d "$slot" ] || ! _run_slot_is_stale "$slot"; then
    return 0
  fi
  graveyard="$slot.broken.$$"
  mv "$slot" "$graveyard" 2>/dev/null || return 0
  if _run_slot_is_stale "$graveyard"; then
    rm -rf "$graveyard"
    echo "NOTICE: broke a stale run slot left by a dead process ($(basename "$slot"))." >&2
    return 0
  fi
  # A live holder took the slot between our check and the rename: put it back (never over a newer slot).
  if [ ! -e "$slot" ] && mv "$graveyard" "$slot" 2>/dev/null; then
    return 0
  fi
  echo "WARN: a live run slot was moved aside; inspect $graveyard." >&2
  return 0
}

# -----------------------------------------------------------------------------
# _run_slot_write_owner <slot dir> <label>
# Purpose: Writes the owner file of a slot this process has just created: pid, tree, label, start times.
# Args: $1 - slot directory, $2 - owner label shown to the processes that wait
# -----------------------------------------------------------------------------
_run_slot_write_owner() {
  printf 'pid=%s\ntree=%s\nlabel=%s\nstarted_utc=%s\nproc_start=%s\n' \
    "$$" "$RUN_SLOT_TREE_ROOT" "$2" "$(_run_slot_now_utc)" "$(_run_slot_pid_start "$$")" > "$1/$RUN_SLOT_OWNER_FILE"
}

# -----------------------------------------------------------------------------
# _run_slot_try_take <slot dir> <label>
# Purpose: One atomic attempt to take one slot. mkdir either creates the slot directory or fails, so exactly one process
#          wins. A stale slot is taken over first (renamed away, then created again).
# Args: $1 - slot directory, $2 - owner label
# Returns: 0 when the slot is ours (it is recorded in RUN_SLOT_HELD and the owner pid is exported), 1 when it is busy.
# -----------------------------------------------------------------------------
_run_slot_try_take() {
  local slot="$1" label="$2"
  if ! mkdir "$slot" 2>/dev/null; then
    _run_slot_break_stale "$slot"
    mkdir "$slot" 2>/dev/null || return 1
  fi
  # A slot whose owner file could not be written would look owner-less and be taken over after the grace: give it back.
  if ! _run_slot_write_owner "$slot" "$label"; then
    rm -rf "$slot"
    return 1
  fi
  RUN_SLOT_HELD="$slot"
  export ES_RUN_SLOT_OWNER_PID="$$"
  return 0
}

# -----------------------------------------------------------------------------
# _run_slot_take_free <label>
# Purpose: Tries every slot in order once and keeps the first one that is free (or stale).
# Args: $1 - owner label
# Outputs: "run slot <n> held for <label> from <time>" on stdout when a slot was taken.
# Returns: 0 when a slot was taken, 1 when all of them are busy.
# -----------------------------------------------------------------------------
_run_slot_take_free() {
  local label="$1" n
  for n in $(seq 1 "$(_run_slot_count)"); do
    if _run_slot_try_take "$(_run_slot_path "$n")" "$label"; then
      echo "run slot $n held for $label from $(_run_slot_now_utc)"
      return 0
    fi
  done
  return 1
}

# -----------------------------------------------------------------------------
# _run_slot_describe <slot dir>
# Purpose: Prints one busy slot on one line (slot name, label, pid, tree, start time) for the waiting message and `status`.
# Args: $1 - slot directory
# Outputs: One line on stdout; nothing when the slot has no owner label (an acquirer is between mkdir and the owner write).
# -----------------------------------------------------------------------------
_run_slot_describe() {
  local owner_file="$1/$RUN_SLOT_OWNER_FILE" label
  label="$(_run_slot_read_key "$owner_file" label)"
  [ -n "$label" ] || return 0
  printf '%s: label=%s pid=%s tree=%s since=%s\n' \
    "$(basename "$1")" "$label" \
    "$(_run_slot_read_key "$owner_file" pid)" \
    "$(_run_slot_read_key "$owner_file" tree)" \
    "$(_run_slot_read_key "$owner_file" started_utc)"
}

# -----------------------------------------------------------------------------
# _run_slot_busy_lines
# Purpose: Prints one line per slot that is held by a live process (stale slots are left out; nothing is removed here).
# Args: None
# Outputs: Zero or more lines on stdout (see _run_slot_describe).
# -----------------------------------------------------------------------------
_run_slot_busy_lines() {
  local slot
  for slot in "$(_run_slot_root)/$RUN_SLOT_DIR_PREFIX"*; do
    [ -d "$slot" ] || continue
    _run_slot_is_stale "$slot" && continue
    _run_slot_describe "$slot"
  done
  return 0
}

# -----------------------------------------------------------------------------
# _run_slot_nested
# Purpose: True when this process runs under a live holder of a slot: the holder exported its pid (ES_RUN_SLOT_OWNER_PID),
#          a slot still names that pid as its owner, and the pid is alive. A stale export (the holder is gone) is not nesting.
# Args: None
# Returns: 0 when nested, 1 otherwise.
# -----------------------------------------------------------------------------
_run_slot_nested() {
  local owner="${ES_RUN_SLOT_OWNER_PID:-}" slot
  [ -n "$owner" ] || return 1
  for slot in "$(_run_slot_root)/$RUN_SLOT_DIR_PREFIX"*; do
    if [ "$(_run_slot_read_key "$slot/$RUN_SLOT_OWNER_FILE" pid)" = "$owner" ]; then
      _run_slot_pid_alive "$owner"
      return
    fi
  done
  return 1
}

# -----------------------------------------------------------------------------
# _run_slot_under_stack_lock
# Purpose: True when this process holds the Docker stack lock, or runs under a live holder of it: stack_lock.sh exports
#          ES_STACK_LOCK_OWNER_PID to its children, and such a child nests in the lock (e.g. `stack_lock.sh run <id> <cmd>`).
#          Either way, waiting for a slot here would hold the lock while waiting.
# Args: None
# Returns: 0 when the stack lock is held by this process or an ancestor, 1 otherwise.
# -----------------------------------------------------------------------------
_run_slot_under_stack_lock() {
  local holder="${ES_STACK_LOCK_OWNER_PID:-}"
  [ -n "$holder" ] || return 1
  [ "$holder" = "$$" ] || _run_slot_pid_alive "$holder"
}

# -----------------------------------------------------------------------------
# _run_slot_wait_and_take <label>
# Purpose: The waiting loop of run_slot_acquire: try every slot, print the busy slots whenever they change, sleep, and
#          repeat until the timeout expires.
# Args: $1 - owner label
# Outputs: Waiting lines and the timeout error on stderr; the success line on stdout.
# Returns: 0 when a slot was taken, 1 on timeout.
# -----------------------------------------------------------------------------
_run_slot_wait_and_take() {
  local label="$1" waited=0 timeout poll last_seen="" now_seen
  timeout="${ES_RUN_SLOT_TIMEOUT_SECONDS:-$RUN_SLOT_DEFAULT_TIMEOUT_SEC}"
  poll="${ES_RUN_SLOT_POLL_SECONDS:-$RUN_SLOT_DEFAULT_POLL_SEC}"
  while true; do
    if _run_slot_take_free "$label"; then
      return 0
    fi
    # Print the busy slots only when they change, so a long wait does not flood the log.
    now_seen="$(_run_slot_busy_lines)"
    if [ "$now_seen" != "$last_seen" ]; then
      echo "run slots busy ($(_run_slot_count)): $(echo "$now_seen" | tr '\n' ' ')— waiting" >&2
      last_seen="$now_seen"
    fi
    if [ "$waited" -ge "$timeout" ]; then
      echo "run slot: still busy after ${waited}s (waiting for '$label')." >&2
      return 1
    fi
    sleep "$poll"
    waited=$((waited + poll))
  done
}

# -----------------------------------------------------------------------------
# run_slot_acquire <label>
# Purpose: Takes one run slot, waiting while every slot is held by a live process. Re-entrant: a call from the holder, or
#          from a live holder's child, returns 0 at once and takes nothing. Refused (exit 2) when this process already holds
#          the stack lock or runs under a live holder of it (ORDER RULE: slot first, then lock).
# Args: $1 - owner label (e.g. e2e-runner), shown to the processes that wait
# Env:  ES_RUN_SLOT_DIR, ES_RUN_SLOTS, ES_RUN_SLOT_POLL_SECONDS, ES_RUN_SLOT_TIMEOUT_SECONDS (see the constants)
# Returns: 0 when held or nested; 1 on timeout (the busy slots are printed on stderr).
# -----------------------------------------------------------------------------
run_slot_acquire() {
  local label="${1:-unnamed}"
  if [ -n "$RUN_SLOT_HELD" ] || _run_slot_nested; then
    return 0
  fi
  if _run_slot_under_stack_lock; then
    echo "run slot refused for '$label': the stack lock is already held by this process or its parent (take the slot before the lock)." >&2
    exit "$RUN_SLOT_REFUSED_EXIT"
  fi
  mkdir -p "$(_run_slot_root)"
  _run_slot_wait_and_take "$label"
}

# -----------------------------------------------------------------------------
# run_slot_release
# Purpose: Releases the slot this process holds. Only the holder removes the slot directory (pid check). A nested process
#          holds nothing and does nothing. Safe to call more than once.
# Args: None
# Returns: 0 always (a slot that was already taken over is left alone).
# -----------------------------------------------------------------------------
run_slot_release() {
  [ -n "$RUN_SLOT_HELD" ] || return 0
  if [ "$(_run_slot_read_key "$RUN_SLOT_HELD/$RUN_SLOT_OWNER_FILE" pid)" = "$$" ]; then
    rm -rf "$RUN_SLOT_HELD"
  fi
  RUN_SLOT_HELD=""
  unset ES_RUN_SLOT_OWNER_PID
  return 0
}

# -----------------------------------------------------------------------------
# run_slot_status
# Purpose: Prints the slots held by live processes, one line each. Read-only: it takes nothing and removes nothing. Prints
#          nothing when every slot is free. Nothing secret is printed (labels, pids, tree paths and times only).
# Args: None
# Outputs: One line per busy slot on stdout (nothing when none is busy).
# Returns: 0.
# -----------------------------------------------------------------------------
run_slot_status() {
  _run_slot_busy_lines
}

# -----------------------------------------------------------------------------
# _run_slot_usage
# Purpose: Prints the usage line of the direct entry point (stderr).
# Args: None
# -----------------------------------------------------------------------------
_run_slot_usage() {
  echo "usage: bash run_slot.sh status" >&2
}

# -----------------------------------------------------------------------------
# _run_slot_cli <status>
# Purpose: Dispatches the direct (not sourced) entry point: `status` prints the busy slots.
# Args: $1 - "status"
# Returns: 0 for status, 2 for a usage error.
# -----------------------------------------------------------------------------
_run_slot_cli() {
  case "${1:-}" in
    status)
      run_slot_status
      ;;
    *)
      _run_slot_usage
      return 2
      ;;
  esac
}

# Run directly (not sourced): `status` prints the busy slots.
if [ "${BASH_SOURCE[0]}" = "$0" ]; then
  _run_slot_cli "$@"
fi
