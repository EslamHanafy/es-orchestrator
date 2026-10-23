# PERFORMANCE CHECKLIST — every group, every review (web profile)

- **A. Data needed at all**: each request justified for this view; no over-fetching; no duplicate requests for the
  same data (share or cache them).
- **B. Bundle size**: lazy-loaded routes; no heavy dependency for a trivial job; tree-shakable imports; the
  bundle budget respected (state the delta).
- **C. Rendering**: OnPush/Signals (or memoized components); `trackBy`/keys on lists; no function calls or heavy
  pipes in templates; virtual scrolling for long lists.
- **D. Main thread**: no long synchronous work; heavy computation in web workers; debounced input handlers.
- **E. Network**: pagination; request cancellation on navigation; retry with backoff for idempotent calls; HTTP
  caching headers respected.
- **F. Images and fonts**: responsive sizes (`srcset`), modern formats, lazy loading below the fold, font-display
  swap, preloading only for critical assets.
- **G. Core Web Vitals**: LCP element known and fast; no layout shift (reserved sizes); INP-friendly handlers.
- **H. Memory**: subscriptions, listeners and timers cleaned up; no unbounded in-memory caches.
- **I. Startup**: minimal work before the first render; no blocking initializers; skeletons instead of blank waits.
- **J. Measurement**: where the plan asks for numbers (Lighthouse, CWV, bundle size), report NOT RUN unless measured.
