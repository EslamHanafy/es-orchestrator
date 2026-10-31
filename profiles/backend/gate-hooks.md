# Backend gate hooks (fill check.sh settings)

| Stack | BUILD_CMD | LINT_CMD | FORMAT_CHECK (files) | TEST_CMD | TEST_FAILURES_EXTRACT |
| --- | --- | --- | --- | --- | --- |
| .NET | `dotnet build <sln> --no-incremental -warnaserror` (changed-file warnings) | `dotnet format style <sln> --verify-no-changes --severity warn` | `dotnet format whitespace <sln> --verify-no-changes --include` | `dotnet test <sln> --logger "console;verbosity=normal"` | `grep -E '^\s+Failed ' \| awk '{print $2}'` |
| Node/TS | `npm run build` | `npx eslint .` | `npx prettier --check` | `npx vitest run` / `npx jest` | `grep -E '^ FAIL ' \| awk '{print $2}'` |
| Java/Kotlin | `./gradlew assemble` | `./gradlew detekt` / `checkstyleMain` | `./gradlew spotlessCheck` (whole tree) | `./gradlew test` | parse `build/test-results/**/*.xml` |
| Go | `go build ./...` | `golangci-lint run` | `gofmt -l` | `go test ./...` | `grep -E '^--- FAIL' \| awk '{print $3}'` |
| Python | `python -m compileall -q src` | `ruff check .` | `ruff format --check` | `pytest -q` | `grep -E '^FAILED ' \| awk '{print $2}'` |

Extra gates worth adding (as numbered blocks before the e2e block):
- **Layering**: grep the imports/usings of changed files in inner layers for references to outer layers (domain must not
  import infrastructure or the web layer).
- **One type per file / enums separate**: for C#/Java/Kotlin, count top-level `class|interface|record|enum|struct`
  declarations per changed file.
- **Doc comments on added declarations**: for languages whose rules require them (e.g. `///` in C#, KDoc, JSDoc).
- **Database required tests**: an env flag that makes DB-gated tests fail instead of soft-skipping, so concurrency and locking
  claims really run.
- **Shared stack** (several worktrees, one container stack): `pre-shared-stack` — unit tests on a test-only database, run slots
  (cap 2, slot before lock), a FIFO stack lock around E2E only, a DB sentinel line, a job-scheduler lock pre-check, a
  health-waited restore. Settings in `helpers/shared-stack.env`; rules in `references/shared-stack.md`. Without a test
  database: `pre-stack-lock` (locks from the tests on, build/format unlocked).
- **Suite parse check**: `bash -n` on every e2e suite, so a syntax error cannot make a suite skip silently.

E2E_CMD pattern: `./tests/run_tests.sh $E2E`; each suite prints `NN: <k> checks`. With `pre-shared-stack` the snippet starts
and restores the app (`SS_E2E_UP` / `SS_E2E_RESTORE`: NAMED services + `--no-deps` + `--wait`), so E2E_CMD only runs suites.
Without it: `docker compose up -d --build --no-deps --wait <svc> && ./tests/run_tests.sh $E2E` — never a bare `up`.
Better AST scanners than fnlen.py: Roslyn analyzers / a small Roslyn script (.NET), `eslint max-lines-per-function` (TS),
detekt `LongMethod` (Kotlin), `gocyclo`/`funlen` (Go), ruff `PLR0915` (Python).
