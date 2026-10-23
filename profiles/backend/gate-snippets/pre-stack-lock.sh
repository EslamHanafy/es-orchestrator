# Gate snippet (pre-): hold one lock for the whole gate run when several worktrees share ONE container stack.
# Only needed when tests or e2e use the shared stack. The lock dir lives in the main checkout's plan folder.
LOCK_DIR="$HERE/runs/.stack-lock"
if [[ $RUN_TESTS == 1 || -n "$E2E" ]]; then
  for _ in $(seq 1 360); do
    if mkdir "$LOCK_DIR" 2>/dev/null; then echo $$ > "$LOCK_DIR/pid"; break; fi
    holder="$(cat "$LOCK_DIR/pid" 2>/dev/null)"
    # A lock whose holder is dead is stale; never kill a live holder.
    if [[ -n "$holder" ]] && ! kill -0 "$holder" 2>/dev/null; then rm -rf "$LOCK_DIR"; continue; fi
    sleep 5
  done
  [[ "$(cat "$LOCK_DIR/pid" 2>/dev/null)" == "$$" ]] || { echo "could not acquire the stack lock (held by $holder)"; exit 2; }
  trap 'rm -rf "$LOCK_DIR"' EXIT
  pass "stack lock acquired"
fi
