# Coding rules (binding for implementers and reviewers)

These rules are binding. When two rules conflict, the more specific one wins. The project's own rules file
({{REPO_RULES_FILES}}) wins over this file wherever it says more.

## Architecture and principles
- Follow the project architecture and its coding standards: clean code, SOLID, DRY and design patterns, applied to
  this codebase and without inventing extra layers just "to be SOLID".
- **Single responsibility**: one class, one job. UI never touches databases or APIs. State holders never build UI.
  Repositories never emit UI state. Data sources know nothing about the UI.
- **Open/closed**: add behaviour with a new type, enum getter, strategy or error subtype. Do not grow god classes or
  copy `switch`es on the same enum.
- **Liskov**: a subtype is a safe drop-in. Every error subtype exposes a usable message and code.
- **Interface segregation**: small, feature-focused interfaces, with no methods added "for later".
- **Dependency inversion**: outer layers depend on abstractions; implementations are wired in the composition root.
- Prefer small functions over long ones. Each has one job at one level of abstraction and is easy to read.

## Reuse first: search before creating
Searching for reusable code is a required step, not an optimization. Before creating any component, helper,
style, model, service, extension or package-based solution, search in this order:
1. the current feature (helpers, models, enums, extensions, similar screens/handlers);
2. completed similar features (same pattern, interaction, layout or data transformation);
3. shared project code (core/common/shared folders, utilities, infrastructure);
4. the design system or theme (tokens, styles, decorations, shared components), for UI work;
5. existing dependencies (inspect the package manifest before writing custom infrastructure);
6. a new dependency, only when existing code and dependencies cannot reasonably do the job and it materially
   reduces complexity or risk;
7. a new custom implementation, only after 1–6 come up empty.

Reuse before recreating, compose before duplicating, and extend or generalize before creating a parallel
component. Do not add excessive configuration to avoid creating a genuinely different component. Keep generalized
code at the narrowest scope that fits; do not move feature code into shared folders just to call it reusable.
After implementing, re-check the changed files for new duplication, and name the meaningful reuse decisions in
the report.

## Files and types
- Never put more than one entity/model/interface/class per file (one public type per file; file name = type name).
- Never put enums in the same file as entities or models; they go in their own files.
- No long files, unless a long file really is the best way. Split by responsibility (SOLID).
- Generated files are never hand-edited; regenerate them with their tool.

## Values, strings and configuration
- Never use hard-coded strings or magic numbers. Use enums, constants files, environment variables or config.
  Exceptions: free text, wire values mapped at the IO boundary, and layout spacing where the stack allows it.
- Prefer environment variables (`.env`) over committed config files for anything that differs per environment, and
  keep every `.env.*.example` in sync with each new key.
- Never hard-code user-visible text. Every user-visible string goes in every locale file ({{LANGUAGES}}) in the same
  change, with a real translation.
- Use enums for typed values (roles, statuses, kinds), never string literals.

## Functions
- **Max {{FN_MAX_LINES}} lines per function** of any kind (methods, handlers, UI build functions, helpers, local
  functions).
- The limit is judged by SOLID, not line count alone. A short function that mixes jobs (load + map + emit, or
  layout + business rules) must still be split. Splitting a cohesive function into arbitrary fragments only to get
  under the limit is not a fix.

## Errors
- Use the project's own error/failure type for app-level failures, with a usable code and message.
- No catch-alls and no empty catch blocks. Map framework/SDK exceptions to the app's error type at the boundary
  (data or infrastructure layer). Never show `toString()` of an exception to a user.

## Comments
- {{COMMENT_POLICY}}

## Data and migrations
- Never modify the database directly, and never modify auto-generated migration files under any condition. Schema
  changes go only through the framework's migration generator.
- Never delete or reset data (databases, volumes, files outside the change) as part of implementation.

## Dependencies and tools
- Always use the latest stable, compatible versions of packages, dependencies and tools (check the registry or the
  web for the current version). If a newer incompatible version exists, report the package, the version used, the
  newer version and why it is incompatible. Do not migrate onto it unasked.
- Do not add a second package that substantially overlaps an existing one.
- Search for and use the best available skill for the task before implementing it.

## Verification
- {{LIVE_CHECK}}: run it after finishing every change that touches a live surface, and paste the real output.
