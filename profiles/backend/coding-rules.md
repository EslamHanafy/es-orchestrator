## Backend rules
- **Clean Architecture direction**: Domain ← Application ← Infrastructure / API. Inner layers never reference outer
  ones.
- **Thin entry points**: controllers/endpoints only translate HTTP to a command or query (mediator/CQRS or a service)
  and never touch the database context directly. Handlers hold the use-case logic.
- **Results, not exceptions, for business outcomes**: handlers return the project's result type with a typed app
  error. Error codes come from one catalogue, and the error kind maps to the HTTP status in one place. 401 is only
  for an unusable token; business refusals are 400/403/409 with a code. Never `throw new Exception(...)`.
- **Ownership**: the caller's identity comes from the token, never from the request body. Every owner/tenant-scoped
  query, update, delete and bulk statement filters by the owner first.
- **Persistence**: database naming convention as configured; an index for every query you add; explicit FK delete
  behaviour; untracked/projection reads; set-based bulk changes; short transactions with no external I/O inside.
- **Lists** use keyset/cursor pagination with a bounded page size; never OFFSET.
- **Async all the way** with cancellation passed down; no blocking waits and no fire-and-forget tasks.
- **Settings**: one settings class per area, bound from `.env`, validated at startup. No silent defaults or optional
  dependencies.
- **One request/command/query/DTO per file**, in the project's feature folder convention (e.g.
  `Features/<Area>/{Commands|Queries}/<Name>/{Command,Validator,Handler}`).
- **Docker + curl**: after finishing, run the stack in containers and test every API you added or changed with curl.
  Paste the request and the response, and compare them with the contract.
