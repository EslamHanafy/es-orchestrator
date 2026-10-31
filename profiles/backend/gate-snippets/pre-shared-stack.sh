# requires-helpers: stack_lock.sh run_slot.sh shared-stack.env docker-compose.testdb.yml testdb_conn.sh stack_lock_selftest.sh run_slot_selftest.sh
# Gate snippet (pre-): several worktrees share ONE container stack (references/shared-stack.md, which gives the reason for
# every rule below). Unit tests run on a test-only database; build/format/lint and unit tests take NO stack lock; a run
# slot caps heavy phases machine-wide (slot BEFORE lock); only E2E holds the FIFO stack lock; a DB sentinel line names a
# restart or a connection kill instead of letting it look like a code fault. Settings: helpers/shared-stack.env.
# Postgres commands are in ss_sql / ss_db_identity; swap those two for another engine. Replaces pre-stack-lock (use one).
# shellcheck source=/dev/null
source "$HERE/helpers/shared-stack.env"
# shellcheck source=/dev/null
source "$HERE/helpers/run_slot.sh"
SS_SECRET_FILE="$HERE/.testdb-password"
SS_E2E_STARTED=0

# ss_sql <container> <sql>: one value from the Postgres in <container>, whitespace stripped (empty on any failure).
ss_sql() { docker exec "$1" sh -c "psql -U \"\$POSTGRES_USER\" -d postgres -tAc \"$2\"" 2>/dev/null | tr -d '[:space:]'; }
# ss_db_identity <container>: "<container StartedAt>|<server start time>"; either half empty = unreadable.
ss_db_identity() { echo "$(docker inspect -f '{{.State.StartedAt}}' "$1" 2>/dev/null)|$(ss_sql "$1" 'select pg_postmaster_start_time()')"; }
ss_healthy() { [[ "$(docker inspect -f '{{.State.Health.Status}}' "$1" 2>/dev/null)" == healthy ]]; }

# ss_ensure_testdb: generate the password once (mode 600, never printed), start the test DB only when it is not healthy
# (--no-recreate: never replace it under another gate) and export the connection string for the harness.
ss_ensure_testdb() {
  [[ -s "$SS_SECRET_FILE" ]] || ( umask 077; openssl rand -hex 24 > "$SS_SECRET_FILE" ) || return 1
  SS_TESTDB_PASSWORD="$(cat "$SS_SECRET_FILE")"
  export SS_TESTDB_PASSWORD SS_TESTDB_USER SS_TESTDB_PORT SS_TESTDB_MAX_CONNECTIONS SS_TESTDB_RANDOM_PAGE_COST SS_TESTDB_EFFECTIVE_CACHE_SIZE
  # shellcheck disable=SC2059
  export "$SS_TESTDB_ENV_NAME=$(printf "$SS_TESTDB_CONN_FORMAT" "$SS_TESTDB_PORT" "$SS_TESTDB_USER" "$SS_TESTDB_PASSWORD")"
  ss_healthy "$SS_TESTDB_CONTAINER" && return 0
  docker compose -f "$SS_TESTDB_COMPOSE" up -d --no-recreate --wait --wait-timeout 120 > "$OUT/testdb-up.txt" 2>&1
}

# ss_shared_ensure: each "<health>|<ensure-up>" pair whose health check fails runs its ensure-up under a SHORT wrapped lock.
ss_shared_ensure() {
  local pair
  for pair in ${SS_SHARED_ENSURE[@]+"${SS_SHARED_ENSURE[@]}"}; do
    bash -c "${pair%%|*}" > /dev/null 2>&1 && continue
    echo "shared ensure-up: taking the stack lock briefly (waits while another tree runs E2E)"
    bash "$HERE/helpers/stack_lock.sh" run "check.sh ensure-up" bash -c "${pair#*|}" >> "$OUT/ensure-up.txt" 2>&1 \
      || { echo "⚠  ensure-up failed: ${pair#*|}"; tail -5 "$OUT/ensure-up.txt"; }
  done
}

# ss_sentinel_start <container> <name>: remember the DB identity and sample its connection count every second.
ss_sentinel_start() {
  local container="$1" name="$2" parent="$$"
  rm -f "$OUT/$name.stop"; : > "$OUT/$name.conn"
  ss_db_identity "$container" > "$OUT/$name.before"
  ( while [[ ! -f "$OUT/$name.stop" ]] && kill -0 "$parent" 2>/dev/null; do
      echo "$(ss_sql "$container" 'select count(*) from pg_stat_activity')" >> "$OUT/$name.conn"; sleep 1
    done ) &
  echo $! > "$OUT/$name.pid"
}

# ss_sentinel_finish <container> <name> <max connections> <phase log>: ONE gate line. Fails when the identity cannot be read
# (a blind check never passes), when the DB restarted, or when the log shows killed / refused connections.
ss_sentinel_finish() {
  local container="$1" name="$2" max="$3" log="$4" before after peak killed
  touch "$OUT/$name.stop"; wait "$(cat "$OUT/$name.pid")" 2>/dev/null
  before="$(cat "$OUT/$name.before")"; after="$(ss_db_identity "$container")"
  [[ "$after" == "|"* || "$after" == *"|" ]] && { sleep 2; after="$(ss_db_identity "$container")"; }
  peak="$(grep -E '^[0-9]+$' "$OUT/$name.conn" | sort -n | tail -1)"
  killed="$(grep -cwE '57P01|53300|too many clients|terminating connection due to administrator command' "$log" 2>/dev/null)"
  if [[ "$before" == "|"* || "$before" == *"|" || "$after" == "|"* || "$after" == *"|" ]]; then
    fail "db sentinel ($container): identity unreadable (before '$before', after '$after') — restart check blind during $name"
  elif [[ "$before" != "$after" ]]; then
    fail "db sentinel ($container): the database RESTARTED during $name ($before → $after) — failures above are not code faults"
  elif [[ "${killed:-0}" -gt 0 ]]; then
    fail "db sentinel ($container): $killed × terminated / too-many-connections in the $name log, peak ${peak:-?}/$max"
  else pass "db sentinel ($container): no restart during $name (started ${before%%|*}), peak ${peak:-?}/$max connections, 0 killed"; fi
}

# ss_job_lock_wait: before an E2E boot, wait (bounded, printed) while the job scheduler still holds FRESH lock rows.
ss_job_lock_wait() {
  set_or_none "$SS_JOB_LOCK_CMD" || return 0
  local waited=0 rows
  while rows="$(bash -c "$SS_JOB_LOCK_CMD" 2>/dev/null)" && [[ -n "$rows" ]]; do
    [[ $waited -ge $SS_JOB_LOCK_WAIT_SEC ]] && { echo "⚠  job-scheduler locks still fresh after ${waited}s:"; echo "$rows" | head -5; return 0; }
    [[ $waited == 0 ]] && { echo "waiting for fresh job-scheduler locks to expire:"; echo "$rows" | head -5; }
    sleep 10; waited=$((waited + 10))
  done
}

gate_before_tests() {
  ss_shared_ensure
  if ss_ensure_testdb; then echo "test DB: $SS_TESTDB_CONTAINER healthy on 127.0.0.1:$SS_TESTDB_PORT ($SS_TESTDB_ENV_NAME exported, value not printed)"
  else fail "test DB: $SS_TESTDB_CONTAINER did not become healthy:"; tail -10 "$OUT/testdb-up.txt" 2>/dev/null
    GATE_SKIP_TESTS=1; return; fi   # never let the harness fall back to the shared stack's database
  run_slot_acquire "unit tests" || { fail "run slot: none free in time for the unit tests"; GATE_SKIP_TESTS=1; return; }
  ss_sentinel_start "$SS_TESTDB_CONTAINER" unit
}

gate_after_tests() {
  ss_sentinel_finish "$SS_TESTDB_CONTAINER" unit "$SS_TESTDB_MAX_CONNECTIONS" "$OUT/tests.txt"
  run_slot_release
}

gate_before_e2e() {
  run_slot_acquire "e2e $E2E" || { fail "run slot: none free in time for e2e"; GATE_SKIP_E2E=1; return; }
  # shellcheck source=/dev/null
  source "$HERE/helpers/stack_lock.sh"
  stack_lock_acquire "check.sh e2e $E2E"; local rc=$?
  # The lock installs its own EXIT trap (already while queued): chain check.sh's cleanup (slot release) in front of it.
  trap 'cleanup; _stack_lock_on_exit' EXIT
  [[ $rc == 0 ]] || { fail "stack lock: not acquired in time (bash $HERE/helpers/stack_lock.sh status)"; GATE_SKIP_E2E=1; return; }
  echo "stack lock held from $(date -u +%H:%M:%SZ)"
  ss_healthy "$SS_STACK_DB_CONTAINER" \
    || { fail "e2e: shared $SS_STACK_DB_CONTAINER is not healthy — start the base stack from the MAIN tree first"; GATE_SKIP_E2E=1; return; }
  bash -c "$SS_E2E_STOP" > /dev/null 2>&1 || true
  ss_job_lock_wait
  SS_E2E_STARTED=1
  bash -c "$SS_E2E_UP" > "$OUT/e2e-up.txt" 2>&1 \
    || { fail "e2e: compose up failed:"; tail -20 "$OUT/e2e-up.txt"; GATE_SKIP_E2E=1; ss_e2e_restore; return; }
  set_or_none "$SS_PROXY_RESTART" && { bash -c "$SS_PROXY_RESTART" > /dev/null 2>&1 || true; }
  ss_sentinel_start "$SS_STACK_DB_CONTAINER" e2e
}

# ss_e2e_restore: put the base app back, health-waited, before the lock changes hands; nothing to do when nothing started.
ss_e2e_restore() {
  [[ $SS_E2E_STARTED == 1 ]] || return 0
  if bash -c "$SS_E2E_RESTORE" > /dev/null 2>&1; then
    set_or_none "$SS_PROXY_RESTART" && { bash -c "$SS_PROXY_RESTART" > /dev/null 2>&1 || true; }
    echo "base app restored at $(date -u +%H:%M:%SZ)"
  else echo "⚠  could not restore the base app — run: $SS_E2E_RESTORE"; fi
  SS_E2E_STARTED=0
}

gate_after_e2e() {
  ss_sentinel_finish "$SS_STACK_DB_CONTAINER" e2e "$(ss_sql "$SS_STACK_DB_CONTAINER" 'show max_connections')" "$OUT/e2e.txt"
  ss_e2e_restore
  run_slot_release
}

# On any exit (an interrupt mid-E2E too): restore the base app while the lock is still held, then free the slot.
gate_on_exit() { ss_e2e_restore; run_slot_release; }
