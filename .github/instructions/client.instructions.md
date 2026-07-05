# Client Instructions

Canonical source: `AGENTS.md`.

- Put Web changes in `apps/finagent-web/`.
- Put desktop changes in `apps/finagent-desktop/`.
- For Web changes, run `npm ci`, `npm run lint`, and `npm run build` from `apps/finagent-web/`.
- For desktop changes, build the Web app first, then run the desktop build.
- Keep API/schema changes backward compatible where possible.
