## Mobile checkpoints (in addition to 1–22)
- **M1. Class/member layout**: member order exactly as the rules file says in EVERY new or changed class (e.g. static →
  constants → final fields → fields → getters → constructors → lifecycle → build/render → private build helpers → public →
  private).
- **M2. Models**: value equality (Equatable/data class/struct), immutable fields, a `copyWith` covering every field (nullable
  fields clearable through the project's clear pattern), every (de)serializer updated; no maps for domain or UI data; computed
  display values on the model/extension, not in the view.
- **M3. State management**: one state type per screen/feature with a status enum (or the project's pattern); no state
  subclasses where the rules forbid them; a static accessor like `Cubit.of(context, listen:false)` where the project uses it;
  views never touch DB/API; state holders never build UI; repositories never emit UI state.
- **M4. Data layer**: one table (or a tight pair) per local data source; SQL only in data sources; owner filter on every
  owner-scoped query; reads inside a transaction use the transaction executor (deadlock otherwise); `core` never imports
  `features`.
- **M5. Design fidelity** (UI batches): the production screen against the approved design/preview, side by side, value by value
  (padding, sizes, colours, radii, text styles, icons, order, states); every design scenario mapped to a real state;
  preview-only parts NOT copied (scenario switches, fixtures, state selector bars, locale toggles, preview harness, demo toasts,
  preview keys/models).
- **M6. Styles and constants**: theme tokens only (colour and text-style roles, never appearance-named or ad-hoc styles; no
  one-off style copies); magic values (page sizes, durations, limits, keys) in constants files; shared widgets/components
  reused (sheets, dialogs, rows, banners, buttons).
- **M7. Navigation**: named/typed routes through the app router only; sheets and dialogs close with their OWN context; no
  anonymous inline routes.
- **M8. Localization and direction**: keys in every locale file and regenerated key classes; plural keys use the plural API;
  no values baked into keys; RTL/bidi handled (numbers, hosts and times isolated LTR; user text first-strong isolated).
- **M9. Pagination and packages**: the project's paging library for paged lists, with first-page/empty/error builders set
  (defaults often show hard-coded English); no overlapping packages; latest compatible versions, and the owner is told about
  newer incompatible ones.
- **M10. Device and manual checks**: in every language, at a large text scale, landscape, offline, and with a profile build for
  large data. If they cannot be run, report NOT RUN explicitly every time. Never imply that they passed.
