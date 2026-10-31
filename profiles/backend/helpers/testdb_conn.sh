#!/usr/bin/env bash
# testdb_conn.sh — prints the test DB connection string for a FOCUSED test run, e.g.
#   APP_TEST_DB="$(bash <plan dir>/helpers/testdb_conn.sh)" dotnet test --filter <name>
# Prints the string on stdout only (it holds the generated password: never paste it into a report or log).
# Exit 1 when the gate has not generated the password yet (run check.sh once with tests).
set -uo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=/dev/null
source "$HERE/helpers/shared-stack.env"
secret="$HERE/.testdb-password"
[[ -s "$secret" ]] || { echo "no $secret yet: run the gate once with tests" >&2; exit 1; }
# shellcheck disable=SC2059
printf "$SS_TESTDB_CONN_FORMAT\n" "$SS_TESTDB_PORT" "$SS_TESTDB_USER" "$(cat "$secret")"
