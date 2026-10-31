# Gate snippet (pre-): the SIMPLE shared-stack lock, for repos whose unit tests still use the shared stack's database.
# Build, lint and format run unlocked (they never touch the stack); the lock is taken just before the tests or the e2e
# phase and held to the end of the gate. When the tests can get their own database, use pre-shared-stack instead (test DB,
# run slots, a lock around E2E only, a DB sentinel; references/shared-stack.md). Use one of the two, not both.
# The lock dir lives in the main checkout's plan folder; check.sh's cleanup() (EXIT trap) releases $LOCK_DIR.
LOCK_DIR="$HERE/runs/.stack-lock"
take_stack_lock() {
  [[ "$(cat "$LOCK_DIR/pid" 2>/dev/null)" == "$$" ]] && return 0
  local holder=""
  for _ in $(seq 1 360); do
    if mkdir "$LOCK_DIR" 2>/dev/null; then echo $$ > "$LOCK_DIR/pid"; break; fi
    holder="$(cat "$LOCK_DIR/pid" 2>/dev/null)"
    # A lock whose holder is dead is stale; never kill a live holder.
    if [[ -n "$holder" ]] && ! kill -0 "$holder" 2>/dev/null; then rm -rf "$LOCK_DIR"; continue; fi
    sleep 5
  done
  [[ "$(cat "$LOCK_DIR/pid" 2>/dev/null)" == "$$" ]] || { echo "could not acquire the stack lock (held by $holder)"; exit 2; }
  pass "stack lock acquired"
}
gate_before_tests() { take_stack_lock; }
gate_before_e2e() { take_stack_lock; }
