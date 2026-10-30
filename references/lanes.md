# Implementer lanes

A lane is one implementer model reached through one delegate skill, plus a fallback chain. The orchestrator picks
a lane per batch, and it never writes feature code itself.

## Available delegate skills (use what is installed)

| Skill | CLI | Resume flag (from result.json) | Notes |
| --- | --- | --- | --- |
| /claude-delegate | `claude` | `--session <id>` | Separate config dirs (`CLAUDE_CONFIG_DIR`) give separate quotas |
| /opencode-delegate | `opencode` | `--session <id>` | Any provider (`anthropic/…`, `opencode-go/…`); `--variant high` |
| /cursor-delegate | `cursor-agent` | `--session <id>` | `--sandbox disabled` when it must run docker |
| /agy-delegate | `agy` | `--conversation <id>` | Gemini; its evidence is often wrong, so treat it as untrusted |
| /codex-delegate, /grok-delegate, /kimi-delegate, /zcode-delegate | … | see each skill | Same relay shape |
| Agent tool (model haiku/sonnet) | built-in | SendMessage | Last-resort fallback; also used for read-only fact maps |

Load the delegate skill once per session before the first dispatch. Each skill documents its own relay flags.

## Rules

- **One batch, one new implementer session.** Pair B is a new session too. Fix rounds resume the same session as
  the batch they fix.
- **Background, never poll.** Run the relay with `run_in_background` and wait for the completion notification. A
  wait loop that exits when a known pid ends is fine. Periodic `ps`/`tail` checks are not.
- **Parallel pairs.** Both lanes run at the same time with `--cd <worktree>`; each worktree is its own tree, so there is no
  file ownership by mtime. Check quota for two simultaneous sessions first. A fix round runs in the main tree (new session if
  the CLI cannot change its directory on resume).
- **Run marker.** `touch runs/<id>/START` right before dispatch. The pair reviewer assigns file ownership by mtime
  against it.
- **Out-dir per run.** `runs/<id>/` holds `result.json`, `REPORT.md` (the final message saved verbatim),
  `gate.log` and `live-checks.log`.
- **Quota/limit error → fallback at once**, same brief, with one line to the owner. Record the switch in the ledger.
- **Resume, never restart** an interrupted run: same command plus the resume flag and a short delta brief ("you
  stopped at …, finish X, re-run the gate, write the report").
- **Untrusted-evidence lanes** (flag `untrusted_evidence`): the orchestrator pre-checks the report's claims (do the
  logs exist? do the counts match?), and the reviewer re-runs every gate and live check instead of only verifying.
- **No sub-workers.** Implementers must not spawn subagents, servers or background helpers, except the e2e stack
  the gate needs.
- **Effort.** Default high for cheap models. Where a fallback has a medium variant, use medium unless the batch is
  JUDGEMENT-heavy.
- **Fact maps / surveys** run on a read-only lane (helper model, one output file) and never edit.

## Choosing a lane per batch

MECHANICAL batches (renames, proven deletions, package bumps without API change, repeated substitutions) → the
cheapest lane, LIGHT review. JUDGEMENT batches → the primary lane, FULL review. The lane never decides the review
type; the batch order does.
