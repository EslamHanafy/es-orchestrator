# PERFORMANCE CHECKLIST — every group, every review (mobile profile)

- **A. Data needed at all**: every repository/DB/network/file read justified for this screen; not already hydrated, joined or in
  state; no loading whole tables or lists to pick one item; lazy (on open of the section that needs it), not eager.
- **B. Data access cost**: LIMIT/keyset paging; no N+1 or per-row queries/inserts (batch); WHERE/ORDER covered by an index
  (EXPLAIN when in doubt); owner filter indexed; reads inside a transaction use its executor; transactions short; no
  full-history scans; sync/import in bounded batches.
- **C. Concurrency/async**: independent awaits run concurrently; stale-result generation guards; debounce search/typing; cancel or
  ignore superseded work; no await chains blocking first paint; timeouts on platform/network calls.
- **D. UI thread**: no heavy synchronous work on the UI thread (large JSON decode, image compress/hash, sorting/grouping large
  lists, crypto, sync file I/O) → background isolate/worker or the data layer; no work in build/render (formatter creation,
  regex, sorting, filtering, large allocations) → precompute in state/model or cache.
- **E. Rebuild scope**: state listeners narrowed to the fields used (selectors, `buildWhen`, memo); high-frequency emissions
  (scroll, map pan, text input, progress) never rebuild the whole screen; size/padding queries instead of full media queries;
  local state scoped to the smallest component; const/pure components; stable keys for list items; no futures/streams created
  inside build.
- **F. Lists/layout**: lazy builders for anything unbounded; no eager children lists for large collections; no shrink-wrapped
  long or nested scrollables; fixed item extents when rows are fixed-height; no intrinsic sizing or layout builders inside rows;
  no deep expensive nesting in repeated rows.
- **G. Painting/compositing**: avoid opacity layers, shader masks, backdrop blur and clip paths in rows and animations (use
  transitions or colours with alpha); repaint boundaries around frequently repainting parts; precise `shouldRepaint`; shadows
  and blur limited in scrolling content.
- **H. Animations**: controllers disposed; animated builders keep their static subtree as a child; no per-row controllers in
  large lists; implicit animations do not restart on every rebuild; nothing animates off-screen.
- **I. Images/media**: decode at display size for thumbnails; no full-resolution decode in grids/lists; placeholders and error
  builders; precache only what is about to show; bounded caches; compress before upload, off the UI thread.
- **J. Memory/leaks**: every controller (text/scroll/animation/map/paging), subscription, timer, focus node and listener is
  disposed or cancelled; no closures capturing a context after dispose; caches bounded; large lists not copied on every emit.
- **K. Startup/navigation**: no heavy work at app start or in init (defer; lazy singletons; startup tasks after the first
  frame); route transitions not blocked by synchronous loads; the first frame shows a skeleton, not a blank wait.
- **L. Network**: pagination, request de-duplication, cancellation on dispose, retry with backoff, caching where the data allows,
  no over-fetching.
- **M. Platform channels/plugins**: no chatty per-item channel calls in loops (batch); permission/location/file plugin calls not
  repeated on every build.
- **N. Measurement**: where the plan asks for profile evidence (frame times, query p50/p95, memory), report NOT RUN unless
  measured on a device or profile build.
