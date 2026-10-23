# Generic gate hooks

Use this profile when the stack is neither a backend service nor a mobile app (a CLI, library, data pipeline or web
frontend), or as the base under the others. Fill the check.sh settings block with the project's own commands. The
backend and mobile `gate-hooks.md` tables list common commands per language.

Minimum viable gate: build + lint + tests vs known failures + function length + forbidden patterns. Add locale parity when
there is more than one language, and an e2e/live block when there is a running surface (HTTP, UI, CLI golden files).

For a web frontend, also consider: bundle-size budget (`size-limit`), accessibility lint (`eslint-plugin-jsx-a11y`),
visual/golden snapshot diffs, and a Playwright smoke suite as E2E_CMD.
