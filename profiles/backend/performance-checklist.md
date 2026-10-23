# PERFORMANCE CHECKLIST — every group, every review (backend profile: large data, many concurrent users)

- **A. Data needed at all**: every DB/network/storage read justified; projections fetch only the needed columns; no loading an
  aggregate or list to read one field; no work for data the response does not return.
- **B. Query cost**: keyset paging only; WHERE + ORDER covered by an index (state it; EXPLAIN when in doubt); owner column first
  in composite indexes; no N+1 (batch-load per kind) and no client-side evaluation; read-only queries untracked; compiled or
  prepared queries on hot paths; no COUNT(*) or full scans on hot paths.
- **C. Writes and transactions**: transactions short; set-based bulk updates/deletes; batched inserts; locks taken late, held
  briefly, in a consistent order; no external I/O (object storage, AI/LLM, push, payment, mail) inside a transaction or lock;
  optimistic concurrency where needed.
- **D. Concurrency and async**: async all the way with cancellation tokens; no sync-over-async (`.Result`, `.Wait()`, blocking
  joins); thread-safe singletons; no shared mutable state; idempotent retries; races covered (two devices, replays, concurrent
  jobs, multiple instances).
- **E. Memory and allocation**: no unbounded lists; large outputs streamed, paged or spooled; pooled buffers for big payloads;
  bodies never buffered whole without need; caches have a size limit.
- **F. Serialization and payload**: source-generated or precompiled serializers on hot paths; payload caps (body size, page
  bytes); compression level chosen for CPU; no double serialization.
- **G. Caching**: what is cached and why; keys without secrets; TTL; invalidation on every write path; multi-instance staleness
  stated and acceptable.
- **H. Background work**: scheduled jobs idempotent, batched and bounded per run (heavy ones off-peak); bounded channels with an
  explicit back-pressure policy; no fire-and-forget.
- **I. External calls**: pooled HTTP clients with timeouts; retries with backoff + jitter for idempotent calls only; provider
  quotas respected; independent calls parallelized outside transactions.
- **J. Rate limiting and abuse**: a per-feature policy with the right partition key; rejected requests cost little; 429 body +
  `Retry-After`.
- **K. Database health**: table growth and retention planned; autovacuum/storage parameters on hot tables; index count and bloat
  reasonable; connection pool sizing; migrations safe on large tables.
- **L. Startup and configuration**: no heavy work at startup; options validated at start; migrations-at-boot noted as dev-only.
- **M. Observability cost**: no per-row logging inside loops; structured, redacted logs; low-cardinality metrics; audit writes
  batched.
- **N. Measurement**: where the plan asks for numbers (p95, memory, EXPLAIN plans, load tests), report NOT RUN unless actually
  measured.
