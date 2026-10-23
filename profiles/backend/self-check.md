## Backend (profile)
B1. 401 only for an unusable token. Account states → 403, validation → 400, conflicts → 409, server faults → 500. List every 401
    your diff can produce and say why each one is a token problem.
B2. Lists are keyset/cursor; no OFFSET/Skip; page size bounded.
B3. Idempotent endpoints: a replay returns the identical status + body; keys are scoped per (owner, operation).
B4. Ownership from the token subject only. EVERY owner-scoped query, update, delete and bulk statement filters by the owner FIRST,
    including lookups by any entity id.
B5. Reads are untracked/projection-only, with filtering, sorting and paging in SQL and an index that covers them (name it). No
    per-row save calls.
B6. Writes: one short transaction; set-based bulk changes; no external HTTP call while holding a transaction or lock.
B7. Async all the way with cancellation passed down; no blocking waits; no fire-and-forget.
B8. No raw SQL built by string interpolation; parameters only.
B9. Schema changes only through the framework's migration generator; never edit a generated migration or the database directly;
    the model-consistency test is green.
B10. Every new setting is in the settings class (validated at startup) AND in every example env file.
B11. A race or lock assertion that inspects database activity runs on its OWN connection, never inside the transaction that
     holds the lock.
B12. Every changed e2e suite actually ran: paste its own check count.
