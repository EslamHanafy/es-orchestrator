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
# The MAIN tree: the base app is restored from its compose files and code, never from the worktree being gated.
SS_MAIN_ROOT="$(git -C "$HERE" rev-parse --show-toplevel)"; export SS_MAIN_ROOT
# Postgres errors that mean the database dropped or refused connections (terminated, crash of another backend, recovering
# or starting up, too many clients), plus a refused TCP connect.
SS_DB_KILL_RE='57P01|57P02|57P03|53300|too many clients|terminating connection|recovery mode|is starting up|Connection refused'

# A missing setting must fail here, before anything is stopped, not as an "unbound variable" mid-swap.
SS_MISSING=""
for v in ES_RUN_SLOTS ES_STACK_LOCK_DIR SS_TESTDB_COMPOSE SS_TESTDB_CONTAINER SS_TESTDB_PORT SS_TESTDB_USER \
  SS_TESTDB_MAX_CONNECTIONS SS_TESTDB_ENV_NAME SS_TESTDB_CONN_FORMAT SS_TESTDB_RANDOM_PAGE_COST \
  SS_TESTDB_EFFECTIVE_CACHE_SIZE SS_STACK_DB_CONTAINER SS_E2E_STOP SS_E2E_UP SS_E2E_RESTORE SS_PROXY_RESTART \
  SS_JOB_LOCK_CMD SS_JOB_LOCK_WAIT_SEC; do
  [[ -n "${!v:-}" ]] || SS_MISSING="$SS_MISSING $v"
done
if [[ -n "$SS_MISSING" ]]; then
  fail "shared-stack.env is missing:$SS_MISSING (use none for an unused command) — tests and e2e not run"
  GATE_SKIP_TESTS=1; GATE_SKIP_E2E=1; return 0
fi

# ss_sql <container> <sql>: one value from the Postgres in <container>, whitespace stripped (empty on any failure).
ss_sql() { docker exec "$1" sh -c "psql -U \"\$POSTGRES_USER\" -d postgres -tAc \"$2\"" 2>/dev/null | tr -d '[:space:]'; }
# ss_db_identity <container>: "<container StartedAt>|<server start time>"; either half empty = unreadable.
ss_db_identity() { echo "$(docker inspect -f '{{.State.StartedAt}}' "$1" 2>/dev/null)|$(ss_sql "$1" 'select pg_postmaster_start_time()')"; }
ss_healthy() { [[ "$(docker inspect -f '{{.State.Health.Status}}' "$1" 2>/dev/null)" == healthy ]]; }

# ss_ensure_testdb: generate the password once (mode 600, never printed), start the test DB only when it is not healthy
# (--no-recreate: never replace it under another gate) and export the connection string for the harness.
ss_ensure_testdb() {
  # Written beside the target and moved in without overwriting, so two first-run gates agree on one password.
  if [[ ! -s "$SS_SECRET_FILE" ]]; then
    ( umask 077; openssl rand -hex 24 > "$SS_SECRET_FILE.$$" ) && mv -n "$SS_SECRET_FILE.$$" "$SS_SECRET_FILE"
    rm -f "$SS_SECRET_FILE.$$"
  fi
  [[ -s "$SS_SECRET_FILE" ]] || return 1
  SS_TESTDB_PASSWORD="$(cat "$SS_SECRET_FILE")"
  export SS_TESTDB_PASSWORD SS_TESTDB_USER SS_TESTDB_PORT SS_TESTDB_MAX_CONNECTIONS SS_TESTDB_RANDOM_PAGE_COST SS_TESTDB_EFFECTIVE_CACHE_SIZE
  # shellcheck disable=SC2059
  export "$SS_TESTDB_ENV_NAME=$(printf "$SS_TESTDB_CONN_FORMAT" "$SS_TESTDB_PORT" "$SS_TESTDB_USER" "$SS_TESTDB_PASSWORD")"
  if ! ss_healthy "$SS_TESTDB_CONTAINER"; then
    docker compose -f "$SS_TESTDB_COMPOSE" up -d --no-recreate --wait --wait-timeout 120 > "$OUT/testdb-up.txt" 2>&1 || return 1
  fi
  ss_testdb_auth_ok || { echo "the test DB rejects the password in $SS_SECRET_FILE (its volume was created with another one):" \
    "drop the TEST DB volume (docker compose -f $SS_TESTDB_COMPOSE down -v) and re-run" > "$OUT/testdb-up.txt"; return 1; }
}

# ss_testdb_auth_ok: log in with the generated password over TCP on the container's own address (loopback is trust in the
# official image, so it would accept any password). PGPASSWORD is passed by name from the environment, never on a command line.
ss_testdb_auth_ok() {
  PGPASSWORD="$SS_TESTDB_PASSWORD" docker exec -e PGPASSWORD -e U="$SS_TESTDB_USER" "$SS_TESTDB_CONTAINER" \
    sh -c 'psql -h "$(hostname -i | cut -d" " -f1)" -U "$U" -d postgres -tAc "select 1"' 2>/dev/null | grep -q 1
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
    done ) < /dev/null > /dev/null 2>&1 &   # never holds the gate's output open (a dead, unreaped gate still passes kill -0)
  echo $! > "$OUT/$name.pid"
}

# ss_sentinel_finish <container> <name> <max connections> <phase log>: ONE gate line. Fails when the identity cannot be read
# (a blind check never passes), when the DB restarted, or when the log shows killed / refused connections.
ss_sentinel_finish() {
  local container="$1" name="$2" max="$3" log="$4" before after peak killed
  local pid; pid="$(cat "$OUT/$name.pid" 2>/dev/null)"
  touch "$OUT/$name.stop"
  # Bounded: a hung docker exec in the sampler must not hang the gate.
  for _ in 1 2 3 4 5 6 7 8 9 10; do [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null || break; sleep 1; done
  [[ -n "$pid" ]] && { kill "$pid" 2>/dev/null; wait "$pid" 2>/dev/null; }
  before="$(cat "$OUT/$name.before")"; after="$(ss_db_identity "$container")"
  [[ "$after" == "|"* || "$after" == *"|" ]] && { sleep 2; after="$(ss_db_identity "$container")"; }
  peak="$(grep -E '^[0-9]+$' "$OUT/$name.conn" | sort -n | tail -1)"
  killed="$(grep -cE "$SS_DB_KILL_RE" "$log" 2>/dev/null)"
  if [[ "$before" == "|"* || "$before" == *"|" || "$after" == "|"* || "$after" == *"|" ]]; then
    fail "db sentinel ($container): identity unreadable (before '$before', after '$after') — restart check blind during $name"
  elif [[ "$before" != "$after" ]]; then
    fail "db sentinel ($container): the database RESTARTED during $name ($before → $after) — failures above are not code faults"
  elif [[ "${killed:-0}" -gt 0 ]]; then
    fail "db sentinel ($container): $killed × terminated / refused / too-many-connections lines in the $name log, peak ${peak:-?}/$max"
  else pass "db sentinel ($container): no restart during $name (started ${before%%|*}), peak ${peak:-?}/$max connections, 0 killed"; fi
}

# ss_job_lock_wait: before an E2E boot, wait (bounded, printed) while the job scheduler still holds FRESH lock rows.
# Returns 1 when the check itself fails: an unreadable lock table is not "no locks".
ss_job_lock_wait() {
  set_or_none "$SS_JOB_LOCK_CMD" || return 0
  local waited=0 rows
  while true; do
    rows="$(bash -c "$SS_JOB_LOCK_CMD" 2>"$OUT/job-lock.err")" || { echo "job-lock check failed:"; tail -3 "$OUT/job-lock.err"; return 1; }
    [[ -n "$rows" ]] || return 0
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
  # The lock's EXIT trap (installed already while queued) runs check.sh's cleanup first: restore + slot release, then the lock.
  STACK_LOCK_EXIT_PREFIX='set +u; cleanup'
  if ! stack_lock_acquire "check.sh e2e $E2E"; then
    fail "stack lock: not acquired in time (bash $HERE/helpers/stack_lock.sh status)"; run_slot_release; GATE_SKIP_E2E=1; return
  fi
  echo "stack lock held from $(date -u +%H:%M:%SZ)"
  ss_healthy "$SS_STACK_DB_CONTAINER" \
    || { fail "e2e: shared $SS_STACK_DB_CONTAINER is not healthy — start the base stack from the MAIN tree first"; GATE_SKIP_E2E=1; return; }
  # Watched from before the stop to after the restore: the swap itself is where a shared DB gets recreated.
  ss_sentinel_start "$SS_STACK_DB_CONTAINER" e2e
  SS_E2E_STARTED=1   # from the stop on, every exit path restores the base app
  bash -c "$SS_E2E_STOP" > /dev/null 2>&1 || true
  ss_job_lock_wait || { fail "e2e: job-scheduler lock check failed"; GATE_SKIP_E2E=1; ss_e2e_finish; return; }
  bash -c "$SS_E2E_UP" > "$OUT/e2e-up.txt" 2>&1 \
    || { fail "e2e: compose up failed:"; tail -20 "$OUT/e2e-up.txt"; GATE_SKIP_E2E=1; ss_e2e_finish; return; }
  set_or_none "$SS_PROXY_RESTART" && { bash -c "$SS_PROXY_RESTART" > /dev/null 2>&1 || true; }
}

# ss_e2e_restore: put the base app back, health-waited, before the lock changes hands; nothing to do when nothing started.
# Runs in the MAIN tree, so the base app comes back with the main tree's compose files, env and code.
ss_e2e_restore() {
  [[ $SS_E2E_STARTED == 1 ]] || return 0
  if (cd "$SS_MAIN_ROOT" && bash -c "$SS_E2E_RESTORE") > "$OUT/e2e-restore.txt" 2>&1; then
    set_or_none "$SS_PROXY_RESTART" && { (cd "$SS_MAIN_ROOT" && bash -c "$SS_PROXY_RESTART") > /dev/null 2>&1 || true; }
    echo "base app restored at $(date -u +%H:%M:%SZ)"
  else fail "e2e: could not restore the base app — run in $SS_MAIN_ROOT: $SS_E2E_RESTORE"; tail -10 "$OUT/e2e-restore.txt"; fi
  SS_E2E_STARTED=0
}

# ss_e2e_finish: restore (health-waited, lock still held), then the sentinel line over the whole swap.
ss_e2e_finish() {
  ss_e2e_restore
  cat "$OUT/e2e-up.txt" "$OUT/e2e.txt" "$OUT/e2e-restore.txt" > "$OUT/e2e-all.txt" 2>/dev/null
  ss_sentinel_finish "$SS_STACK_DB_CONTAINER" e2e "$(ss_sql "$SS_STACK_DB_CONTAINER" 'show max_connections')" "$OUT/e2e-all.txt"
}

gate_after_e2e() {
  ss_e2e_finish
  run_slot_release
}

# ss_sentinel_kill: stop every sampler still running (an exit before its phase finished).
ss_sentinel_kill() { local f; for f in "$OUT"/*.pid; do [[ -f "$f" ]] && kill "$(cat "$f")" 2>/dev/null; done; return 0; }

# On any exit (an interrupt mid-E2E too): restore the base app while the lock is still held, then free the slot.
gate_on_exit() { ss_sentinel_kill; ss_e2e_restore; run_slot_release; }
