## Web (profile)
W1. No inline template or style; HTML, SCSS and TS in separate files.
W2. Signals/computed for state; no manual change detection; no leaked or nested subscriptions.
W3. Shared components and style partials reused (name them); nothing re-styled by hand when a shared class exists.
W4. Typed models, one per file; no `any`.
W5. Loading, empty and error states rendered for every request.
W6. Every control labelled; keyboard reachable; dialogs trap and restore focus.
W7. Logical CSS properties for RTL; every key in all locale files.
W8. Lazy route for any new feature area; the bundle budget still passes.
