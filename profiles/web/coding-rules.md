## Web frontend rules
Examples use Angular names (Signals, standalone components, SCSS partials). Map them to React, Vue or Svelte
equivalents.

- **Separate files**: never put HTML, CSS and TypeScript in the same file (no inline templates or styles).
- **Reactivity**: prefer Signals (or the framework's fine-grained reactive primitive) over manual change detection.
  Use `computed` for derived state and `effect` only for side effects. No manual `detectChanges`.
- **Reusable components and styles (DRY)**: use the shared components index (e.g. `shared/components/index.ts`)
  and the existing style partials (`_variables.scss`, `_mixins.scss`, `_components.scss`) before writing new ones.
  Search before creating.
- **Smart vs presentational**: containers fetch and hold state; presentational components take inputs and emit
  outputs, and never call services.
- **Typed API layer**: one service per API area; typed request/response models, one per file; no `any`.
- **Routing**: lazy-loaded feature routes; guards and resolvers instead of ad-hoc checks inside components.
- **Forms**: typed reactive forms; validation messages come from locale keys.
- **Localization**: no hard-coded user-visible text. Every key is in all locale files ({{LANGUAGES}}), and RTL
  layouts use logical CSS properties (`margin-inline-start`, not `margin-left`).
- **Accessibility**: semantic elements, labels on every control, focus management on dialogs, colour contrast that
  meets WCAG AA.
- **Subscriptions**: never leak them. Use `takeUntilDestroyed`/async pipe or Signals, and never nest subscribes.
