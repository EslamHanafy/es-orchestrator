# Owner decisions and escalation

## Two ledgers

- **Owner decisions** `O-<n>`: the table in the handoff. They are binding until the owner reverses them. Each
  row: id · date · the decision in bold, then the detail · `[reason / who]`. Superseded rows stay, marked
  `superseded by O-m`.
- **Orchestrator rulings** `<PHASE>-R<n>`: in the phase survey/rulings file (`runs/<phase>-survey.md`, appended
  section). Each one has a reason, and the next owner summary lists them.

## What goes to the owner (ask first, recommendation first)

Default reserved categories (setup can add more):
1. User-visible behaviour, copy, or UX flow changes.
2. Contract/API deviations, or anything another team (mobile, web, partner) must agree to.
3. Data-loss, privacy or security trade-offs; retention; deleting user data.
4. Real scope, cost, quota or schedule changes; new paid services; buying anything.
5. Anything an existing O-row reserves.
6. Touching real config, secrets, production or shared infrastructure.

Everything else you rule on yourself: test harness, refactors, naming, file splits, evidence format, batch order
and lane choice. Asking the owner about those wastes their time and stalls the pipeline.

## How to ask

- AskUserQuestion, max 4 questions, each with 2–4 options. Put your recommendation first, marked
  "(Recommended)", and include one line on the consequence of each option.
- Park only the dependent work. Keep dispatching independent batches.
- If the owner is away and the work must move: decide, mark it **OWNER-REVIEW** in END STATE, and ask at the
  start of the next session (confirm or reverse). Never do this for categories 3, 4 or 6.

## Recording

1. Add the O-row with the date and reason.
2. Check every existing ruling and brief that the decision touches, and update them (ledger line).
3. If it creates a standing rule (e.g. "every user-visible key in all locale files"), add it to the RULE
   CHECKLIST, the self-check and the reviewer checklist in the same turn.
4. Mention it in the next owner summary.
