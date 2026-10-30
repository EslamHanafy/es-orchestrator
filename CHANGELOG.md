# Changelog

## 1.1.0

### Added
- **Run modes**: `plan`, `orchestrate`, `review`, `commit` and `full` (`references/run-modes.md`). Each runs only its stage and
  records the stage reached (`status.py --set-stage`); `NEXT_SESSION_PROMPT.md` and the END STATE carry the mode.
- **Parallel pairs** in git worktrees (`scripts/worktree.py`, `references/parallel-pairs.md`): add, snapshot, land, remove, list.
  New answer keys `PARALLEL_PAIRS`, `WORKTREE_DIR`, `WORKTREE_SETUP_CMD`, `WORKTREE_COPY_FILES`.
- `scripts/doctor.py` (health check), `detect_stack.py --draft-answers` (quick setup), `scaffold.py --upgrade-static`.
- Gate: per-command timeout (`GATE_TIMEOUT_SECONDS`), temp-dir cleanup and fallback, secret scan of added lines,
  code-only forbidden-pattern rules (`~name`), placeholder parity and `.properties`/`.strings` support in `locale_parity.py`.
- Owner-report marker (`<A>+<B>-OWNER_REPORT_SENT`) checked by `commit`; stale-run detection in `status.py`.
- Reviewer agent installs per project (`.claude/agents/`) by default (`REVIEWER_AGENT_SCOPE`).
- Install with `npx skills add EslamHanafy/es-orchestrator`; tests and CI; host fallbacks documented.

### Fixed
- `SKILL.md` frontmatter is valid YAML (the `skills` CLI skipped the skill before).
- Scripts no longer hard-code `~/.claude/skills/es-orchestrator` (`$ES` = the install directory).
- `status.py`: tasks were double-counted (task headings plus their checkbox steps); a run id matched other ids by prefix
  (`B1` vs `B10`); clear errors instead of tracebacks.
- `scaffold.py`: `PLAN_ID` is validated (no path traversal), unknown answer keys are reported, `--only` rejects unknown files.
- `archive.py`: clear error when the handoff has no LIVE STATUS heading.
- `detect_stack.py`: Xcode projects are detected, plain Dart packages are not treated as Flutter apps, plans are found by directory.
- Mobile `generated-up-to-date` snippet is opt-in (no project-specific default); the `null-assert` rule no longer fires on strings.

- Hardening from an independent review: `land` is byte-exact (CRLF, non-UTF-8, binary), refuses edits made after the snapshot,
  compares file names case-insensitively and reverts a half-applied patch; re-adding a batch id archives the old attempt;
  `remove --all` skips already-removed worktrees; git output is pinned (`core.quotepath=off`, `a/ b/` prefixes) so non-ASCII file
  names and `diff.noprefix` no longer hide files from the gate; untracked files without a trailing newline cannot swallow the next
  file's header; a gates.d snippet that does not parse fails the gate (and the mobile `core-imports-features` snippet now parses
  under macOS bash 3.2); `check.sh` refuses to gate a different checkout than it was started in; `run_timeout.py` forwards
  SIGTERM/SIGINT/SIGHUP and always kills the whole group; the secret scan is case-insensitive and catches unquoted `.env` lines;
  `status.py` treats only a leading done-word/✅ as done, counts signal-less tasks as open, ignores fenced code, matches legacy
  hyphenated report names exactly and says so when it recognises no tasks.

### Removed
- Two empty placeholder files in `profiles/generic/` (missing profile files are skipped).

## 1.0.0
- Initial release.
