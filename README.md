# es-orchestrator

A [Claude Code](https://claude.com/claude-code) skill that runs a long implementation plan with Claude as
**orchestrator only**.

- Claude writes the **surveys, briefs and rulings**.
- Cheaper **implementer models** write the code in paired ≈30-minute batches.
- A fresh **reviewer agent** checks every pair line by line against stack checklists.
- **You** get the full review report before every commit.
- A handoff file, a progress ledger and a next-session prompt carry the state across sessions and context
  compactions.

It works on any project and stack. The stack is detected from the repo (backend, mobile or web, monorepos
included). The coding rules ship as defaults that you keep, edit or replace during setup.

## Contents

- [Install](#install)
- [Quick start](#quick-start)
- [Run modes: one step or the whole cycle](#run-modes-one-step-or-the-whole-cycle)
- [How a cycle works](#how-a-cycle-works)
- [Prompt cheat sheet](#prompt-cheat-sheet)
- [What gets generated](#what-gets-generated)
- [Implementer lanes](#implementer-lanes)
- [Troubleshooting](#troubleshooting)
- [Customize](#customize)
- [Layout of this skill](#layout-of-this-skill)

## Install

Requirements: `git`, `bash` and `python3` (standard library only) on your machine, and Node.js for `npx`.

### With `npx skills` (recommended)

```bash
npx skills add EslamHanafy/es-orchestrator
```

The CLI asks which agents to install for. Useful variations:

```bash
# Available in every project on this machine (instead of only the current project)
npx skills add EslamHanafy/es-orchestrator -g

# Claude Code only, no prompts
npx skills add EslamHanafy/es-orchestrator -a claude-code -y

# See what the repo offers without installing
npx skills add EslamHanafy/es-orchestrator --list

# Independent copy instead of a symlink (for systems without symlink support)
npx skills add EslamHanafy/es-orchestrator --copy
```

| Scope | Flag | Installed under |
| --- | --- | --- |
| This project (default; commit it to share with your team) | none | `./.claude/skills/es-orchestrator` |
| All projects on this machine | `-g` | `~/.claude/skills/es-orchestrator` |

Other agents get their own folder (for example `.agents/skills/`). The skill finds its own scripts wherever it was
installed, so the location does not matter.

Manage it later with:

```bash
npx skills list            # what is installed
npx skills check           # is an update available?
npx skills update es-orchestrator
npx skills remove es-orchestrator
```

### Manual install

```bash
git clone https://github.com/EslamHanafy/es-orchestrator.git ~/.claude/skills/es-orchestrator
```

Update with `git -C ~/.claude/skills/es-orchestrator pull`.

### Optional: delegate skills for the implementer lanes

The implementers run through a delegate skill such as `claude-delegate`, `opencode-delegate`, `cursor-delegate`,
`agy-delegate` or `codex-delegate`. Install the ones you want to use. Without any of them, the plain Agent tool is
the fallback lane, so nothing is required.

## Quick start

1. Open Claude Code in your repo. Have a plan file ready (phases and tasks). If you do not have one, ask Claude
   to write it first.
2. **Set up** (once per plan):
   ```
   Use es-orchestrator to set up the orchestrator workflow for this repo: plan = docs/plans/my-plan.md
   ```
   Claude detects the stack, shows what it found, and asks only for what it could not work out: coding rules
   (defaults / edit / replace / repo file only), gate commands, implementer lanes, reviewer model, batch size,
   languages and staging paths. It then generates `.superpowers/sdd/<PLAN_ID>/`, runs a baseline gate and shows
   you the prompt for the next session.
3. **Work**: ask for the whole cycle, or for one step (next section).
   ```
   Use es-orchestrator to continue <PLAN_ID> as ORCHESTRATOR.
   ```
4. **Stop**: ask Claude to end the session. It writes the END STATE and a resume prompt for next time.
   ```
   Use es-orchestrator to end the session: write the END STATE, the next-session prompt, and trim the archives.
   ```
5. **Resume** in any new session by pasting the generated `NEXT_SESSION_PROMPT.md`, or by repeating step 3.

`.superpowers/` holds your plan's working files. Add it to `.gitignore` (setup offers to do it).

## Run modes: one step or the whole cycle

You do not have to run the full loop. Pick the step you want, and Claude runs only that step.

| Mode | What it does | Stops when | Does **not** |
| --- | --- | --- | --- |
| `plan` | Surveys the next phase, rules open decisions, writes and re-checks the briefs, orders the batches into pairs | Briefs are ready and you have seen the batch order | Dispatch code, review, commit |
| `orchestrate` | Dispatches pair A and pair B to the implementer lanes and collects their reports | Both reports are saved and complete | Review, commit |
| `review` | A fresh reviewer reads every changed line against the checklists, fixes the minor findings, writes the report and sends it to you | You have the report file and a plain-language summary | Dispatch, commit |
| `commit` | Confirms the gate is fresh, commits with explicit paths, updates the ledger and handoff | The commit exists and the books are updated | Review, dispatch |
| `full` (default) | All four, over and over | You say stop | — |

Other modes: **setup** (once per plan), **status** (done/left %, what is running) and **end of session**.

How to ask:

```
Use es-orchestrator in plan mode for <PLAN_ID>
Use es-orchestrator: orchestrate only, batches B14+B15
/es-orchestrator review B14+B15
Use es-orchestrator to review the uncommitted changes (review only)
Use es-orchestrator: full cycle
```

Rules that hold in every mode:

- A mode does only its own step. If the step before it is not finished (no brief, no report, open findings), Claude
  stops and tells you which mode to run first.
- Every mode starts by checking the handoff against the real repo (`git log`, `git status`, running processes).
  If they differ, the repo wins.
- Every mode ends by recording where the work stands and naming the next mode to run, for example
  "Both batches implemented, not reviewed. Next: `review B14+B15`." That is what lets a different session
  pick up the work.
- Nothing is committed without you having the full review report, whatever the mode.
- With no plan folder yet, Claude offers **setup** first and does not start it silently.

Typical ways to use the modes:

| You want to… | Run |
| --- | --- |
| Hand the whole plan to the workflow | `full` |
| Look over the briefs before any money is spent on implementers | `plan`, read the briefs, then `orchestrate` |
| Let implementers work overnight and review in the morning | `orchestrate`, later `review` |
| Get a strict second opinion on changes you or another tool wrote | `review` on the working tree or a commit range |
| Commit after you have read the report and agree | `commit` |

## How a cycle works

```
 plan ──▶ orchestrate ──▶ review ──▶ commit
  │            │             │          │
  │            │             │          └ gate fresh? explicit-path commit, ledger + handoff updated
  │            │             └ fresh reviewer, every changed line read; you get the full report
  │            └ pair A, then pair B on top of A; each in its own new implementer session
  └ survey, rulings, briefs (re-checked against the code before every dispatch)
```

Who does what:

| Role | Who | Does |
| --- | --- | --- |
| Owner | You | Decide product, scope, money, security and data-loss questions. Read the report before every commit. |
| Orchestrator | Claude (this skill) | Surveys, briefs, rulings, dispatch, verdicts, the commit and the books. Writes no feature code. |
| Implementers | Cheaper models in their own sessions | One batch each, about 30 minutes, run as pairs. |
| Reviewer | A fresh strong-model subagent per pair | Reads every changed line, fixes minor findings, hands the rest back as a fix brief. |

Why it is built this way:

- Summary-only reviews miss defects, so every changed line is read against a written checklist, with evidence.
- Cheap implementers fabricate gate output, so evidence is checked against log files, and the gate must be newer
  than every source file before a commit.
- Long sessions lose state, so an END STATE block, a ledger and a generated resume prompt make every session
  restartable.
- Big batches overwhelm reviews, so batches take ≈30 minutes, run as pairs, with one review per pair.

## Prompt cheat sheet

| Goal | Say |
| --- | --- |
| First-time setup | `Use es-orchestrator to set up the orchestrator workflow for this repo: plan = <path>` |
| See progress | `Use es-orchestrator: status for <PLAN_ID>` |
| Continue everything | `Use es-orchestrator to continue <PLAN_ID> as ORCHESTRATOR` |
| Planning only | `Use es-orchestrator in plan mode` |
| Planning for one phase | `Use es-orchestrator: plan only, phase 3` |
| Implement only | `Use es-orchestrator: orchestrate only` |
| Review only | `Use es-orchestrator: review only B14+B15` |
| Commit only | `Use es-orchestrator: commit only` |
| Stop for today | `Use es-orchestrator to end the session` |

## What gets generated

```
.superpowers/sdd/<PLAN_ID>/
  ORCHESTRATOR_HANDOFF.md      commit gate, roles, LIVE STATUS / END STATE, decisions, rule checklist, workflow
  progress.md                  roadmap + one ledger line per review/commit
  coding-rules.md              the rules implementers and reviewers follow (defaults / edited / your own)
  review-checklist.md          mandatory review checkpoints (generic + stack)
  performance-checklist.md     performance groups for the stack
  review-lessons-self-check.md implementer self-check; grows with every review finding
  brief / survey / review-full / review-light templates, reviewer-agent.md, NEXT_SESSION_PROMPT.md
  check.sh + fnlen.py + locale_parity.py + allow-lists + forbidden-patterns.txt + gates.d/
  runs/<batch>/                START marker, result.json, REPORT.md, gate.log, live-checks.log
```

Setup also installs a per-plan reviewer agent into `~/.claude/agents/` (it asks first, because that is user-level
configuration).

## Implementer lanes

A lane is one implementer model reached through one delegate skill, plus a fallback chain, for example:

1. Haiku via `claude-delegate`
2. then OpenCode with an Anthropic provider
3. then a plain Agent-tool Haiku

Setup asks for your lane order. When a lane hits a quota limit, Claude switches to its fallback with the same brief
and tells you in one line. Details: `references/lanes.md`.

## Troubleshooting

| Problem | Fix |
| --- | --- |
| `npx skills add` says no skills found | Run `npx skills add EslamHanafy/es-orchestrator --list` and make sure you have the latest CLI (`npx skills@latest`). The `SKILL.md` frontmatter must be valid YAML. |
| Claude does not pick the skill up | Name it: "Use es-orchestrator …". Restart the session after installing. |
| "No plan folder found" | Run setup first. No other mode can run without `.superpowers/sdd/<PLAN_ID>/`. |
| A mode refuses and names another mode | The step before it is not finished. Run the mode it names. |
| `TOOL NOT FOUND` in the gate log | The toolchain is missing from `PATH`. Fix `PATH` in `check.sh`, then re-run the gate. It is not a code finding. |
| A scaffold run refuses to overwrite | The plan folder exists. Use the session modes, or ask for a re-scaffold with `--force` (backups are written as `*.bak-<date>`). |
| Handoff and repo disagree | The repo wins. Claude writes a ledger line saying what it found. |

## Customize

- **Rules**: edit `profiles/<stack>/coding-rules.md`, or choose "edit" / "replace" during setup.
- **A new stack**: add `profiles/<name>/` with the same six files. `generic` is always the base.
- **More gates**: drop a snippet into `profiles/<stack>/gate-snippets/` (it is sourced by `check.sh`; `pre-*`
  snippets run before the build).

## Layout of this skill

| Path | What |
| --- | --- |
| `SKILL.md` | Mode router (setup / plan / orchestrate / review / commit / full / status / end) and the non-negotiables |
| `references/run-modes.md` | The single-step modes: entry checks, steps, stop conditions |
| `references/` | Setup flow, answers schema, session loop, end-of-session, lanes, pairing & review, git & gates, owner decisions |
| `templates/` | Files copied into the plan folder |
| `profiles/{generic,backend,mobile,web}/` | Coding rules, review checkpoints, performance checklist, self-check lines, defaults, gate hooks, gate snippets |
| `scripts/detect_stack.py` | Suggests profiles, gate commands, locale/rules/plan files from the repo |
| `scripts/scaffold.py` | Generates the plan folder from `answers.json` |
| `scripts/status.py` | Exact done/left % (by count and effort), phases, running runs |
| `scripts/archive.py` | End-of-session trimming of the handoff and the ledger |

## License

MIT. See [LICENSE](LICENSE).
