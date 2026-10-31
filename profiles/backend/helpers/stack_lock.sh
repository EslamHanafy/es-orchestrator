#!/usr/bin/env bash
# =============================================================================
# stack_lock.sh — One shared container stack, serialised across git worktrees (es-orchestrator backend profile)
#
# Every git worktree of a repo usually drives the SAME container stack (fixed container names, one compose project). Two
# runs that recreate or restart those containers at the same time corrupt each other, so every entry point that changes
# the shared stack (an E2E run, a load test, a seed script, a short ensure-up) holds this lock while it does. Build,
# format and unit tests on their own test database take NO lock (references/shared-stack.md).
# Installed by scaffold.py into <plan dir>/helpers/ (the MAIN tree's copy, used by every worktree); set ES_STACK_LOCK_DIR
# to a per-project path when two projects on one machine have different stacks.
#
# Use it sourced (library) or directly (wrapper, holds the lock for one command; or prints the holder and the queue):
#   source <plan dir>/helpers/stack_lock.sh
#   stack_lock_acquire "<owner-label>"     # waits (bounded) until the lock is ours, first come first served
#   stack_lock_release                     # only the holder releases; a nested call is a no-op
#   bash <plan dir>/helpers/stack_lock.sh run <owner-label> <command> [args...]
#   bash <plan dir>/helpers/stack_lock.sh status   # prints the holder and the queue, oldest first; takes nothing
#
# Contract for scripts:
#   - Acquire BEFORE you install your own EXIT trap: acquiring installs EXIT/INT/TERM traps that release the lock.
#   - A script whose own EXIT trap replaces the lock's EXIT trap calls stack_lock_release as the LAST step of that trap.
#   - Or set STACK_LOCK_EXIT_PREFIX to that cleanup before acquiring: the lock's own EXIT trap runs it first, queued or held.
#   - A child started by the holder (check.sh -> the e2e runner) sees ES_STACK_LOCK_OWNER_PID and becomes a no-op, so
#     nested runs never deadlock.
#   - Bash 3.2 compatible (macOS /bin/bash): no BASHPID, no associative arrays. Holder identity is $$, so a holder is
#     always a separate process, never a ( ) subshell.
#
# The lock is the directory ${ES_STACK_LOCK_DIR:-/tmp/es-stack.lock} holding an `owner` file:
#   tree=<repo root>  label=<owner label>  pid=<holder pid>  started_utc=<UTC ISO-8601>
# A lock whose holder pid is dead on this machine is stale and is broken. A live holder is never broken.
#
# FIFO queue: a process that does not get the lock at once writes ONE ticket file into <lock dir>.queue/, named
#   <epoch seconds, zero-padded to 12>-<pid, zero-padded to 10>   (content: tree, label, pid, queued_utc, proc_start)
# Only the oldest live ticket may try to take the lock; dead tickets are pruned on every poll; a ticket is
# removed when its process takes the lock, when it times out, and when it exits by EXIT/INT/TERM while it waits. A fresh
# acquirer that finds the queue empty takes a free lock at once, with no ticket. The names have whole seconds, so two
# processes that queue in the same UTC second are ordered by pid. A ticket is dead when its pid is dead OR when that pid
# now belongs to another process (its start time differs from `proc_start`): a SIGKILLed waiter whose pid the system
# reused must not block the queue. From the moment it queues, a process carries the lock's EXIT/INT/TERM traps (they
# withdraw the ticket), so a caller's own EXIT trap set before stack_lock_acquire is replaced while it waits and after a
# timeout too: set (or re-chain) your traps after the acquire, as the contract above says.
# =============================================================================

# Lock directory used when ES_STACK_LOCK_DIR is not set.
STACK_LOCK_DEFAULT_DIR="/tmp/es-stack.lock"
# File inside the lock directory that names the holder.
STACK_LOCK_OWNER_FILE="owner"
# Suffix of the ticket queue directory, next to the lock directory: "<lock dir>.queue".
STACK_LOCK_QUEUE_SUFFIX=".queue"
# Widths of the zero-padded epoch and pid parts of a ticket name (fixed widths make the names sort by arrival).
STACK_LOCK_TICKET_EPOCH_WIDTH=12
STACK_LOCK_TICKET_PID_WIDTH=10
# Separator between the epoch part and the pid part of a ticket name.
STACK_LOCK_TICKET_SEP="-"
# Seconds between attempts while the lock is busy (ES_STACK_LOCK_POLL_SECONDS overrides; whole seconds).
STACK_LOCK_DEFAULT_POLL_SEC=5
# Longest wait in seconds before giving up (ES_STACK_LOCK_TIMEOUT_SECONDS overrides): two hours.
STACK_LOCK_DEFAULT_TIMEOUT_SEC=7200
# An owner-less lock younger than this is an acquirer between mkdir and the owner write, not a crash.
STACK_LOCK_INIT_GRACE_SEC=30
# Exit status after an interrupt (128 + SIGINT): INT/TERM end the script, so the EXIT trap releases the lock.
STACK_LOCK_SIGNAL_EXIT=130
# Repository root of the tree this run works on (CHECK_ROOT of a worktree gate, else the current checkout), written into
# the owner file.
STACK_LOCK_TREE_ROOT="${CHECK_ROOT:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
# How this process relates to the lock: "held" (we took it), "nested" (a live holder is an ancestor),
# "waiting" (we hold a ticket and poll for the lock), or empty.
STACK_LOCK_STATE=""
# Name of this process's ticket while it waits (empty when it holds no ticket).
STACK_LOCK_TICKET=""

# -----------------------------------------------------------------------------
# _stack_lock_dir
# Purpose: Prints the lock directory. Read at call time so a caller (or the self-test) can redirect it.
# Args: None
# Outputs: Lock directory path on stdout.
# -----------------------------------------------------------------------------
_stack_lock_dir() {
  echo "${ES_STACK_LOCK_DIR:-$STACK_LOCK_DEFAULT_DIR}"
}

# -----------------------------------------------------------------------------
# _stack_lock_queue_dir
# Purpose: Prints the ticket queue directory: the lock directory name with the queue suffix.
# Args: None
# Outputs: Queue directory path on stdout.
# -----------------------------------------------------------------------------
_stack_lock_queue_dir() {
  echo "$(_stack_lock_dir)$STACK_LOCK_QUEUE_SUFFIX"
}

# -----------------------------------------------------------------------------
# _stack_lock_now_utc
# Purpose: Prints the current time in UTC, ISO-8601 (written into the owner file and the waiting message).
# Args: None
# Outputs: Timestamp on stdout.
# -----------------------------------------------------------------------------
_stack_lock_now_utc() {
  date -u +"%Y-%m-%dT%H:%M:%SZ"
}

# -----------------------------------------------------------------------------
# _stack_lock_read_key <file> <key>
# Purpose: Prints the value of `key=` from a key=value file (an owner file or a ticket file); nothing when there is no file.
# Args: $1 - file path, $2 - key name
# Outputs: Value on stdout.
# -----------------------------------------------------------------------------
_stack_lock_read_key() {
  [ -f "$1" ] || return 0
  # 2>/dev/null: the file may vanish between the test above and this read (a release, a pruned ticket): an empty result.
  sed -n "s/^$2=//p" "$1" 2>/dev/null | head -n 1
}

# -----------------------------------------------------------------------------
# _stack_lock_read_field <lock_dir> <key>
# Purpose: Prints the value of `key=` from the owner file of a lock directory (nothing when there is no owner file).
# Args: $1 - lock directory, $2 - field name (tree, label, pid or started_utc)
# Outputs: Field value on stdout.
# -----------------------------------------------------------------------------
_stack_lock_read_field() {
  _stack_lock_read_key "$1/$STACK_LOCK_OWNER_FILE" "$2"
}

# -----------------------------------------------------------------------------
# _stack_lock_pid_alive <pid>
# Purpose: True when <pid> is a live process on this machine. `ps -p` also sees other users' processes; `kill -0`
#          would report them as dead (EPERM).
# Args: $1 - process id (may be empty, which counts as not alive)
# Returns: 0 when alive, 1 otherwise.
# -----------------------------------------------------------------------------
_stack_lock_pid_alive() {
  [ -n "$1" ] && ps -p "$1" -o pid= >/dev/null 2>&1
}

# -----------------------------------------------------------------------------
# _stack_lock_age_sec <lock_dir>
# Purpose: Prints how many seconds ago the lock directory was last modified. GNU stat (-c) and BSD stat (-f) differ, so
#          GNU is tried first: on BSD `stat -c` fails and the BSD form runs.
# Args: $1 - lock directory
# Outputs: Age in seconds on stdout. Returns 1 when the directory cannot be inspected (it vanished meanwhile).
# -----------------------------------------------------------------------------
_stack_lock_age_sec() {
  local mtime
  mtime=$(stat -c %Y "$1" 2>/dev/null || stat -f %m "$1" 2>/dev/null) || return 1
  echo $(( $(date +%s) - mtime ))
}

# -----------------------------------------------------------------------------
# _stack_lock_is_stale <lock_dir>
# Purpose: Decides whether a lock may be broken. A lock with an owner file is stale when its holder pid is dead. A lock
#          with no owner file is stale only after STACK_LOCK_INIT_GRACE_SEC: a live acquirer writes the owner file within
#          milliseconds of its mkdir, so a lock that stays ownerless that long belongs to a crashed acquirer.
# Args: $1 - lock directory
# Returns: 0 when stale, 1 when live or when it cannot be judged.
# -----------------------------------------------------------------------------
_stack_lock_is_stale() {
  local lock_dir="$1" holder_pid age
  holder_pid=$(_stack_lock_read_field "$lock_dir" pid)
  if [ -n "$holder_pid" ]; then
    ! _stack_lock_pid_alive "$holder_pid"
    return
  fi
  age=$(_stack_lock_age_sec "$lock_dir") || return 1
  [ "$age" -gt "$STACK_LOCK_INIT_GRACE_SEC" ]
}

# -----------------------------------------------------------------------------
# _stack_lock_break_stale
# Purpose: Breaks the lock when it is stale, race-safely. The directory is first RENAMED to a private name, so two waiters
#          that both judged it stale cannot both delete it. The renamed copy is judged again: when a live holder re-created
#          the lock in between, the copy is moved back instead of being deleted.
# Args: None (reads the lock directory from the environment)
# Outputs: A NOTICE on stderr when a stale lock was broken.
# -----------------------------------------------------------------------------
_stack_lock_break_stale() {
  local lock_dir graveyard
  lock_dir="$(_stack_lock_dir)"
  [ -d "$lock_dir" ] && _stack_lock_is_stale "$lock_dir" || return 0
  graveyard="$lock_dir.broken.$$"
  mv "$lock_dir" "$graveyard" 2>/dev/null || return 0
  if _stack_lock_is_stale "$graveyard"; then
    rm -rf "$graveyard"
    echo "NOTICE: broke a stale stack lock left by a dead process." >&2
    return 0
  fi
  # A live holder took the lock between our check and the rename: put it back (never over a newer lock).
  if [ ! -e "$lock_dir" ] && mv "$graveyard" "$lock_dir" 2>/dev/null; then
    return 0
  fi
  echo "WARN: a live stack lock was moved aside; inspect $graveyard." >&2
}

# -----------------------------------------------------------------------------
# _stack_lock_try_take <label>
# Purpose: One atomic attempt to take the lock. mkdir either creates the lock directory or fails, so exactly one process
#          wins. The winner writes its owner file at once.
# Args: $1 - owner label, shown to the processes that wait
# Returns: 0 when the lock is ours, 1 when another holder has it.
# -----------------------------------------------------------------------------
_stack_lock_try_take() {
  local label="$1" lock_dir
  lock_dir="$(_stack_lock_dir)"
  mkdir "$lock_dir" 2>/dev/null || return 1
  printf 'tree=%s\nlabel=%s\npid=%s\nstarted_utc=%s\n' \
    "$STACK_LOCK_TREE_ROOT" "$label" "$$" "$(_stack_lock_now_utc)" > "$lock_dir/$STACK_LOCK_OWNER_FILE"
}

# -----------------------------------------------------------------------------
# _stack_lock_ticket_name
# Purpose: Prints the ticket name this process uses now: the epoch seconds, then the pid, both zero-padded, so that the
#          names sort by arrival (the epoch is the major key).
# Args: None
# Outputs: Ticket name on stdout (the epoch padded to 12 digits, a dash, the pid padded to 10 digits).
# -----------------------------------------------------------------------------
_stack_lock_ticket_name() {
  printf "%0${STACK_LOCK_TICKET_EPOCH_WIDTH}d${STACK_LOCK_TICKET_SEP}%0${STACK_LOCK_TICKET_PID_WIDTH}d" \
    "$(date +%s)" "$$"
}

# -----------------------------------------------------------------------------
# _stack_lock_ticket_pid <ticket name>
# Purpose: Prints the pid part of a ticket name as a plain number (arithmetic drops the zero padding).
# Args: $1 - ticket name
# Outputs: Pid on stdout.
# -----------------------------------------------------------------------------
_stack_lock_ticket_pid() {
  local pid="${1##*$STACK_LOCK_TICKET_SEP}"
  echo $((10#$pid))
}

# -----------------------------------------------------------------------------
# _stack_lock_list_tickets
# Purpose: Prints the names of the queued tickets, oldest first. Byte order (LC_ALL=C) keeps the zero-padded names in
#          arrival order whatever the locale.
# Args: None
# Outputs: One ticket name per line on stdout (nothing when the queue is empty or missing).
# -----------------------------------------------------------------------------
_stack_lock_list_tickets() {
  ls -1 "$(_stack_lock_queue_dir)" 2>/dev/null | LC_ALL=C sort
}

# -----------------------------------------------------------------------------
# _stack_lock_queue_head
# Purpose: Prints the oldest ticket in the queue, the only one allowed to take the lock. Call it after the prune.
# Args: None
# Outputs: Ticket name on stdout, or nothing when the queue is empty.
# -----------------------------------------------------------------------------
_stack_lock_queue_head() {
  _stack_lock_list_tickets | head -n 1
}

# -----------------------------------------------------------------------------
# _stack_lock_pid_start <pid>
# Purpose: Prints the start time of a process as `ps` reports it (LC_ALL=C, so every caller formats it the same way),
#          without the padding spaces. Two processes that share a pid one after the other have different start times.
# Args: $1 - process id
# Outputs: Start time on stdout (nothing when the process does not exist).
# -----------------------------------------------------------------------------
_stack_lock_pid_start() {
  LC_ALL=C ps -p "$1" -o lstart= 2>/dev/null | sed -e 's/^ *//' -e 's/ *$//'
}

# -----------------------------------------------------------------------------
# _stack_lock_ticket_live <ticket name>
# Purpose: True when the ticket still belongs to a waiting process: its pid is alive AND that pid is still the process
#          that wrote the ticket (same start time). A ticket whose start time is not written yet (its writer is between
#          the create and the write) is judged by the pid alone.
# Args: $1 - ticket name
# Returns: 0 when live, 1 when dead (the pid exited, or the system reused it for another process).
# -----------------------------------------------------------------------------
_stack_lock_ticket_live() {
  local pid recorded
  pid="$(_stack_lock_ticket_pid "$1")"
  _stack_lock_pid_alive "$pid" || return 1
  recorded="$(_stack_lock_read_key "$(_stack_lock_queue_dir)/$1" proc_start)"
  [ -z "$recorded" ] || [ "$recorded" = "$(_stack_lock_pid_start "$pid")" ]
}

# -----------------------------------------------------------------------------
# _stack_lock_prune_queue
# Purpose: Removes the dead tickets. A waiter killed with SIGKILL cannot remove its own ticket, so every poll prunes them
#          (also when the system has reused the dead waiter's pid), and the queue head is always a live waiter.
# Args: None
# -----------------------------------------------------------------------------
_stack_lock_prune_queue() {
  local name
  _stack_lock_list_tickets | while IFS= read -r name; do
    _stack_lock_ticket_live "$name" || rm -f "$(_stack_lock_queue_dir)/$name"
  done
}

# -----------------------------------------------------------------------------
# _stack_lock_enqueue <owner label>
# Purpose: Writes this process's ticket into the queue, once (a second call is a no-op), and makes the process a waiter:
#          the traps that withdraw the ticket on exit or interrupt are installed now. The ticket records this process's
#          start time, so a reused pid is not mistaken for it.
# Args: $1 - owner label, stored in the ticket for `status`
# Outputs: Sets STACK_LOCK_TICKET and STACK_LOCK_STATE=waiting.
# -----------------------------------------------------------------------------
_stack_lock_enqueue() {
  local label="$1" queue_dir
  [ -z "$STACK_LOCK_TICKET" ] || return 0
  queue_dir="$(_stack_lock_queue_dir)"
  mkdir -p "$queue_dir"
  STACK_LOCK_TICKET="$(_stack_lock_ticket_name)"
  printf 'tree=%s\nlabel=%s\npid=%s\nqueued_utc=%s\nproc_start=%s\n' \
    "$STACK_LOCK_TREE_ROOT" "$label" "$$" "$(_stack_lock_now_utc)" "$(_stack_lock_pid_start "$$")" \
    > "$queue_dir/$STACK_LOCK_TICKET"
  STACK_LOCK_STATE="waiting"
  _stack_lock_install_traps
}

# -----------------------------------------------------------------------------
# _stack_lock_drop_ticket
# Purpose: Removes this process's ticket from the queue and forgets it. A no-op when the process has no ticket.
# Args: None
# Outputs: Clears STACK_LOCK_TICKET.
# -----------------------------------------------------------------------------
_stack_lock_drop_ticket() {
  if [ -n "$STACK_LOCK_TICKET" ]; then
    rm -f "$(_stack_lock_queue_dir)/$STACK_LOCK_TICKET"
  fi
  STACK_LOCK_TICKET=""
}

# -----------------------------------------------------------------------------
# _stack_lock_leave_queue
# Purpose: Gives up a wait (timeout): removes the ticket and clears the waiting state, so the EXIT trap has nothing to do.
# Args: None
# Outputs: Clears STACK_LOCK_STATE when it was "waiting".
# -----------------------------------------------------------------------------
_stack_lock_leave_queue() {
  _stack_lock_drop_ticket
  STACK_LOCK_STATE=""
}

# -----------------------------------------------------------------------------
# _stack_lock_attempt_take <label>
# Purpose: One FIFO attempt to take the lock. The queue is pruned first. The lock is tried only when the queue is empty
#          (a fresh acquirer with no waiters) or this process holds the oldest live ticket. A taken lock drops our ticket.
# Args: $1 - owner label
# Returns: 0 when the lock is ours (state held), 1 when it is busy or it is not our turn.
# -----------------------------------------------------------------------------
_stack_lock_attempt_take() {
  local label="$1" head
  _stack_lock_prune_queue
  head="$(_stack_lock_queue_head)"
  # An older live ticket is ahead of us: wait without touching the lock.
  if [ -n "$head" ] && [ "$head" != "$STACK_LOCK_TICKET" ]; then
    return 1
  fi
  _stack_lock_try_take "$label" || return 1
  _stack_lock_drop_ticket
  _stack_lock_mark_held
  return 0
}

# -----------------------------------------------------------------------------
# _stack_lock_describe <lock_dir>
# Purpose: Prints the holder of a lock on one line (label, pid, tree, start time) for the waiting message. Prints nothing
#          when the lock has no owner file.
# Args: $1 - lock directory
# Outputs: One line on stdout (or nothing).
# -----------------------------------------------------------------------------
_stack_lock_describe() {
  local lock_dir="$1" label
  label=$(_stack_lock_read_field "$lock_dir" label)
  # No label means no owner file, or the holder released it while we read: there is no holder to describe.
  [ -n "$label" ] || return 0
  printf 'label=%s pid=%s tree=%s since=%s\n' \
    "$label" \
    "$(_stack_lock_read_field "$lock_dir" pid)" \
    "$(_stack_lock_read_field "$lock_dir" tree)" \
    "$(_stack_lock_read_field "$lock_dir" started_utc)"
}

# -----------------------------------------------------------------------------
# _stack_lock_describe_ticket <ticket file>
# Purpose: Prints one queued ticket on one line (label, pid, tree, queue time) for `status`.
# Args: $1 - ticket file path
# Outputs: One line on stdout.
# -----------------------------------------------------------------------------
_stack_lock_describe_ticket() {
  printf 'label=%s pid=%s tree=%s queued_utc=%s\n' \
    "$(_stack_lock_read_key "$1" label)" \
    "$(_stack_lock_read_key "$1" pid)" \
    "$(_stack_lock_read_key "$1" tree)" \
    "$(_stack_lock_read_key "$1" queued_utc)"
}

# -----------------------------------------------------------------------------
# _stack_lock_is_nested
# Purpose: True when this process runs under a live holder of THIS lock: the holder exported its pid
#          (ES_STACK_LOCK_OWNER_PID) and the lock still names that pid as its owner.
# Args: None
# Returns: 0 when nested, 1 otherwise.
# -----------------------------------------------------------------------------
_stack_lock_is_nested() {
  [ -n "${ES_STACK_LOCK_OWNER_PID:-}" ] || return 1
  [ "$ES_STACK_LOCK_OWNER_PID" = "$(_stack_lock_read_field "$(_stack_lock_dir)" pid)" ] || return 1
  _stack_lock_pid_alive "$ES_STACK_LOCK_OWNER_PID"
}

# -----------------------------------------------------------------------------
# _stack_lock_install_traps
# Purpose: Installs the traps of a process that holds or waits for the lock: EXIT runs _stack_lock_on_exit, and INT/TERM
#          exit (so EXIT runs too).
# Args: None
# -----------------------------------------------------------------------------
_stack_lock_install_traps() {
  # STACK_LOCK_EXIT_PREFIX (optional): the caller's own cleanup, run first by the same EXIT trap, so it is kept while the
  # process waits in the queue too (e.g. 'set +u; cleanup'); the lock is released after it.
  trap "${STACK_LOCK_EXIT_PREFIX:+$STACK_LOCK_EXIT_PREFIX; }_stack_lock_on_exit" EXIT
  trap "exit $STACK_LOCK_SIGNAL_EXIT" INT TERM
}

# -----------------------------------------------------------------------------
# _stack_lock_mark_held
# Purpose: Records that this process holds the lock: exports the owner pid for child processes and installs the traps
#          that release the lock when the script exits or is interrupted.
# Args: None
# Outputs: Sets STACK_LOCK_STATE=held, exports ES_STACK_LOCK_OWNER_PID, installs the traps.
# -----------------------------------------------------------------------------
_stack_lock_mark_held() {
  STACK_LOCK_STATE="held"
  export ES_STACK_LOCK_OWNER_PID="$$"
  _stack_lock_install_traps
}

# -----------------------------------------------------------------------------
# _stack_lock_on_exit
# Purpose: EXIT trap of the lock. A holder releases the lock. A process that only waits withdraws its ticket. Nothing
#          else is touched: a process that has already released or timed out no longer owns the lock, so it must not
#          run stack_lock_release (that would warn about the lock of another process).
# Args: None
# -----------------------------------------------------------------------------
_stack_lock_on_exit() {
  if [ "$STACK_LOCK_STATE" = "held" ]; then
    stack_lock_release
  fi
  _stack_lock_drop_ticket
}

# -----------------------------------------------------------------------------
# _stack_lock_forget
# Purpose: Clears this process's lock state after a release (the owner pid is no longer ours to pass on).
# Args: None
# -----------------------------------------------------------------------------
_stack_lock_forget() {
  STACK_LOCK_STATE=""
  unset ES_STACK_LOCK_OWNER_PID
}

# -----------------------------------------------------------------------------
# _stack_lock_wait_and_take <label>
# Purpose: The waiting loop of stack_lock_acquire: try to take the lock in FIFO order, break a stale one, print the holder
#          whenever it changes, sleep, and repeat until the timeout expires.
# Args: $1 - owner label
# Outputs: Waiting lines and the timeout error on stderr.
# Returns: 0 when taken, 1 on timeout.
# -----------------------------------------------------------------------------
_stack_lock_wait_and_take() {
  local label="$1" waited=0 timeout poll last_seen="" now_seen
  timeout="${ES_STACK_LOCK_TIMEOUT_SECONDS:-$STACK_LOCK_DEFAULT_TIMEOUT_SEC}"
  poll="${ES_STACK_LOCK_POLL_SECONDS:-$STACK_LOCK_DEFAULT_POLL_SEC}"
  while true; do
    if _stack_lock_attempt_take "$label"; then
      return 0
    fi
    # Not at once: join the queue (once; later polls keep the same ticket) and keep polling.
    _stack_lock_enqueue "$label"
    _stack_lock_break_stale
    # Print the holder only when it changes, so a long wait does not flood the log.
    now_seen="$(_stack_lock_describe "$(_stack_lock_dir)")"
    if [ -n "$now_seen" ] && [ "$now_seen" != "$last_seen" ]; then
      echo "Docker stack busy — waiting for: $now_seen" >&2
      last_seen="$now_seen"
    fi
    if [ "$waited" -ge "$timeout" ]; then
      echo "ERROR: stack lock still held after ${timeout}s (waiting for '$label')." >&2
      _stack_lock_leave_queue
      return 1
    fi
    # Background + wait: an INT/TERM trap runs at once instead of after the sleep.
    sleep "$poll" & wait $!
    waited=$((waited + poll))
  done
}

# -----------------------------------------------------------------------------
# stack_lock_acquire <owner-label>
# Purpose: Takes the stack lock, waiting in FIFO order while another live holder has it. Re-entrant: a call from the
#          holder, or from a child of the holder, returns 0 at once and takes nothing, so a nested run never deadlocks.
# Args: $1 - owner label (e.g. e2e-runner), shown to the processes that wait
# Env:  ES_STACK_LOCK_DIR, ES_STACK_LOCK_POLL_SECONDS, ES_STACK_LOCK_TIMEOUT_SECONDS (see the constants)
# Returns: 0 when held or nested; 1 on timeout (the holder is printed on stderr).
# -----------------------------------------------------------------------------
stack_lock_acquire() {
  local label="${1:-unnamed}"
  if [ "$STACK_LOCK_STATE" = "held" ]; then
    return 0
  fi
  if _stack_lock_is_nested; then
    STACK_LOCK_STATE="nested"
    return 0
  fi
  # An unwritable lock root would look like "busy" for the whole timeout: say so and fail at once.
  local queue_dir
  queue_dir="$(_stack_lock_queue_dir)"
  if ! mkdir -p "$queue_dir" 2>/dev/null || [ ! -w "$queue_dir" ]; then
    echo "stack lock: cannot write $queue_dir (set ES_STACK_LOCK_DIR to a writable path)." >&2
    return 1
  fi
  _stack_lock_wait_and_take "$label"
}

# -----------------------------------------------------------------------------
# stack_lock_release
# Purpose: Releases the lock this process holds. Only the holder removes the lock directory (pid check). A nested process
#          has nothing to release and does nothing. Safe to call more than once.
# Args: None
# Outputs: A WARN on stderr when the lock belongs to another live process.
# Returns: 0 when released or nothing to release; 1 when the lock is another process's (refused).
# -----------------------------------------------------------------------------
stack_lock_release() {
  if [ "$STACK_LOCK_STATE" = "nested" ]; then
    return 0
  fi
  local lock_dir
  lock_dir="$(_stack_lock_dir)"
  if [ ! -d "$lock_dir" ]; then
    _stack_lock_forget
    return 0
  fi
  if [ "$(_stack_lock_read_field "$lock_dir" pid)" != "$$" ]; then
    echo "WARN: stack lock not released: this process ($$) is not its holder." >&2
    return 1
  fi
  rm -rf "$lock_dir"
  _stack_lock_forget
  return 0
}

# -----------------------------------------------------------------------------
# _stack_lock_print_queue
# Purpose: Prints the live tickets, oldest first, one line each, numbered from 1. Dead tickets are skipped (the next poll
#          of a waiter prunes them); nothing is removed here.
# Args: None
# Outputs: One "queue <n>: ..." line per live ticket on stdout (nothing when the queue is empty).
# -----------------------------------------------------------------------------
_stack_lock_print_queue() {
  local position=0 name
  _stack_lock_list_tickets | while IFS= read -r name; do
    _stack_lock_ticket_live "$name" || continue
    position=$((position + 1))
    echo "queue $position: $(_stack_lock_describe_ticket "$(_stack_lock_queue_dir)/$name")"
  done
  return 0
}

# -----------------------------------------------------------------------------
# stack_lock_status
# Purpose: Prints the lock holder, then the queue, oldest first, one line each. Read-only: it takes nothing and removes
#          nothing. Nothing secret is printed (labels, pids, tree paths and times only).
# Args: None
# Outputs: "holder: ..." (or "holder: none") and then one "queue <n>: ..." line per live ticket, on stdout.
# Returns: 0.
# -----------------------------------------------------------------------------
stack_lock_status() {
  local holder
  holder="$(_stack_lock_describe "$(_stack_lock_dir)")"
  echo "holder: ${holder:-none}"
  _stack_lock_print_queue
  return 0
}

# -----------------------------------------------------------------------------
# _stack_lock_run_wrapped <owner-label> <command> [args...]
# Purpose: Runs one command while holding the lock. The EXIT trap releases the lock after the command, also on failure
#          or interrupt, and the command's exit status becomes this script's exit status.
# Args: $1 - owner label; the rest is the command line
# Returns: the command's exit status (1 when the lock could not be taken).
# -----------------------------------------------------------------------------
_stack_lock_run_wrapped() {
  local label="$1"
  shift
  stack_lock_acquire "$label" || return 1
  "$@"
}

# -----------------------------------------------------------------------------
# _stack_lock_usage
# Purpose: Prints the usage line of the direct entry point (stderr).
# Args: None
# -----------------------------------------------------------------------------
_stack_lock_usage() {
  echo "usage: bash stack_lock.sh run <owner-label> <command> [args...] | status" >&2
}

# -----------------------------------------------------------------------------
# _stack_lock_cli <run|status> [args...]
# Purpose: Dispatches the direct (not sourced) entry point: `run` holds the lock for one command, `status` prints the
#          holder and the queue.
# Args: $1 - "run" or "status"; for run, the owner label and the command line
# Returns: the command's exit status for run, 0 for status, 2 for a usage error.
# -----------------------------------------------------------------------------
_stack_lock_cli() {
  case "${1:-}" in
    run)
      if [ "$#" -lt 3 ]; then
        _stack_lock_usage
        return 2
      fi
      shift
      _stack_lock_run_wrapped "$@"
      ;;
    status)
      stack_lock_status
      ;;
    *)
      _stack_lock_usage
      return 2
      ;;
  esac
}

# Run directly (not sourced): `run` holds the lock for one command; `status` prints the holder and the queue.
if [ "${BASH_SOURCE[0]}" = "$0" ]; then
  _stack_lock_cli "$@"
fi
