## Mobile rules
Examples use Flutter names (Cubit, GetIt, `AppColors`). Map them to the project's equivalents (ViewModel, Hilt,
Redux, theme tokens …).

### Layers and state
- Stay with the project's layers (e.g. Data → Presentation). Do not add a domain/use-case layer, or a second
  state-management, routing or DI library, unless asked.
- Every state holder (Cubit/Bloc/ViewModel) exposes a static accessor where the project uses one
  (`static XCubit of(BuildContext c, {bool listen = false})`). Use `listen: true` only where the widget must rebuild.
- State is **one** state class plus a status enum in the same `{name}_state.dart` file (`initial`, `loading`,
  `success`, `failure`, plus the statuses the feature really needs). It has value equality, final fields and
  `copyWith`. No hierarchy of state subclasses.
- Data sources are split by origin into `data_sources/local/` (DB, preferences, secure storage, files) and
  `data_sources/remote/` (HTTP/SDK). One local data source owns one table, or one tightly coupled pair. The
  repository composes data sources.

### Files and naming
- One public type per file. The only exception is the state class and its status enum, which share `{name}_state.dart`.
- File names are snake_case with a **type** suffix (`home_screen.dart`, `item_widget.dart`, `user_model.dart`,
  `user_cubit.dart`, `items_repository.dart`).
- Widget classes end with `Widget`. Routed full-screen destinations end with `Screen`. Dialogs and sheets are
  `Widget`s.
- Private build helpers are named `_build<Name>Widget`.

### Class layout
Order members top to bottom: static properties → constants → final variables → variables → getters → equality
props → constructors → static functions → lifecycle (`initState`, `dispose`, `close`) → `build` → `_build*` →
public functions → private functions.

### Widgets
- Keep `build` short. Extract **sections** (header, list, empty state, footer, repeated row), not the whole body.
  Do not create a `*ContentWidget`/`*BodyWidget` that only wraps what `build` returns. The Screen owns its
  scaffold, app bar and section composition.
- A chunk used only in this screen becomes a private `_buildXWidget`. One reused within the feature goes in the
  feature's `widgets/` folder. One used by several features goes in the shared widgets folder. Feature-only widgets
  never go in shared folders.

### Models, enums and maps
- Every model has value equality, `final` fields and `copyWith`. Computed display values live on the model or an
  extension, never duplicated in widgets.
- Never use a `Map` for domain or UI data; create a model. JSON maps are allowed only at the IO boundary.
- A repeated `switch` on an enum becomes a getter on the enum. A single exhaustive `switch` that builds different
  widgets is fine.

### UI, styles and constants
- Never hard-code colours or text styles; use the theme tokens. **Name styles by role, not appearance**
  (`rowTitle`, `bodySecondary`, `metricCompact`, `surface`, `critical`, not `body16BlackW600`).
  Appearance-named members are deprecated, and new or edited code never uses them.
- Never `copyWith` a text style. When a role legitimately needs a variant, give the role function a named
  parameter.
- Numeric roles use tabular figures.
- Magic values (page sizes, timeouts, cache keys, durations, limits) go in constants files. Padding, spacing, radii
  and icon sizes may stay inline.

### Navigation and localization
- All routes are named routes registered in the app router. Never build anonymous routes inside widgets.
- User-visible strings use generated locale keys. Add every key to all locale files ({{LANGUAGES}}) and regenerate
  the keys. Key names use underscores (dots break generated identifiers). Never localize technical identifiers.

### Pagination and packages
- Use the project's paging library for paged lists, and do not page short, fully loaded lists.
- Inspect the package manifest before adding a package. Use the latest version compatible with the SDK and the
  existing constraints. Report newer incompatible versions instead of migrating.

### Design previews (when the project has them)
- Approved previews are visual templates: copy them 1:1 ("Copy & Bind"). Copy the layout, then replace the preview's
  scenario switch with the real state (loading → skeleton, empty → empty state, error → error state, loaded → real
  models).
- Missing items are built with the same tokens and shared widgets as the preview, without redesigning it.
  Preview-only parts (scenario switches, fixtures, state bars, locale toggles, harnesses, preview keys) never reach
  production.
- Existing design tokens and shared components override generic advice from any design skill.
