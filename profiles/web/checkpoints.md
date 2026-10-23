## Web checkpoints (in addition to 1–22)
- **W1. File separation and components**: no inline templates or styles; smart/presentational split respected; the
  shared component index and style partials reused; no near-duplicate component.
- **W2. Reactivity**: Signals/computed over manual change detection; no leaked subscriptions; no nested subscribes;
  effects only for side effects.
- **W3. API layer**: typed models (one per file, no `any`); errors mapped to the app's error type; loading, empty and
  error states rendered for every request.
- **W4. Routing and guards**: lazy routes; guards/resolvers for auth and data; deep links work after a reload.
- **W5. Accessibility**: semantic markup, labels, keyboard navigation, focus traps in dialogs, contrast; run an
  automated a11y check on changed pages.
- **W6. Localization and RTL**: every key in all locale files; logical CSS properties; numbers/dates formatted by
  locale; layout checked in RTL.
- **W7. Design fidelity**: the page against the approved design, value by value; responsive breakpoints checked.
- **W8. Live evidence**: the changed pages exercised in a browser (or a Playwright smoke suite), with screenshots or
  test output in the run folder; NOT RUN reported explicitly when impossible.
