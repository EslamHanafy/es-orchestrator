# PERFORMANCE CHECKLIST — every group, every review (generic profile)

- **A. Data needed at all**: every read (DB, network, file) is justified; only the needed fields are fetched; nothing is loaded
  just to read one value.
- **B. Algorithmic cost**: no quadratic loops over unbounded input; no N+1 calls; work is batched.
- **C. I/O and transactions**: short transactions; no external I/O inside a transaction or lock; bulk operations are set-based.
- **D. Concurrency and async**: async all the way with cancellation; no blocking waits; races covered (two clients, replays,
  concurrent jobs).
- **E. Memory**: no unbounded lists; large outputs streamed or paged; caches bounded.
- **F. Caching**: what is cached and why; keys without secrets; TTL; invalidation on every write path.
- **G. External calls**: timeouts; retries with backoff + jitter for idempotent calls only; provider quotas respected.
- **H. Startup**: no heavy work at startup; configuration validated early.
- **I. Observability cost**: no logging per item inside loops; structured, redacted logs.
- **J. Measurement**: where the plan asks for numbers (p95, memory, frame times), report NOT RUN unless actually measured.
