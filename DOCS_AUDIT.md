# Pyxle Docs Audit Report

**Audited revisions:**
- `pyxle-framework/pyxle` @ `main` (`b72f1bc`)
- `pyxle-framework/pyxle-dev` @ `main` (`878cb77`)

**Scope:** Every public-facing doc page under `pyxle/docs/` (getting-started, core-concepts, guides, reference, faq, README) cross-referenced against the actual framework source (`pyxle/*`) plus the scaffold template (`pyxle/templates/scaffold/`).

**Not audited in depth (flagged for follow-up):**
- `pyxle/docs/architecture/*.md` (11 internals files, ~150 KB)
- `pyxle/docs/advanced/*.md`
- `pyxle/docs/guides/for-ai-agents.md` (24 KB)
- How `pyxle-dev/pages/docs/[[...slug]].pyxl` actually resolves doc pages at runtime

---

## 1. Confirmed — docs match the framework

These API surfaces were explicitly verified against the source:

| Area | Source | Status |
|------|--------|--------|
| `@server`, `@action`, `LoaderError`, `ActionError` (signatures, defaults, attributes) | `pyxle/runtime.py` | OK |
| `pyxle.config.json` schema (pagesDir, publicDir, buildDir, starlette, vite, debug, middleware, routeMiddleware, styling, cors, csrf, `"csrf": false` shorthand) | `pyxle/config.py` | OK |
| All `PYXLE_*` env var overrides (HOST, PORT, VITE_HOST, VITE_PORT, DEBUG, PAGES_DIR, PUBLIC_DIR, BUILD_DIR) | `pyxle/config.py::apply_env_overrides` | OK |
| `.env` file load order + `PYXLE_PUBLIC_` prefix semantics | `pyxle/env.py` | OK |
| CLI commands (`init`, `install`, `dev`, `build`, `serve`, `check`, `typecheck`, `routes`) with all documented flags & defaults | `pyxle/cli/__init__.py` | OK |
| Client exports from `pyxle/client` (`Head`, `Script`, `Image`, `ClientOnly`, `Form`, `useAction`, `usePathname`, `Link`, `navigate`, `prefetch`, `refresh`) | `pyxle/client/index.js` | OK (but see 2.1) |
| `<Form>` props: `action`, `pagePath`, `onSuccess`, `onError`, `resetOnSuccess`, children | `pyxle/client/Form.jsx` | OK |
| `useAction` options (`pagePath`, `onMutate`) and attached state (`pending`, `error`, `data`) + abort-in-flight | `pyxle/client/useAction.jsx` | OK |
| `<Image>` props + eager/lazy loading behaviour | `pyxle/client/Image.jsx` | OK |
| `<Script>` props (render-null behaviour matches docs) | `pyxle/client/Script.jsx` | OK |
| `<ClientOnly>` fallback behaviour | `pyxle/client/ClientOnly.jsx` | OK |
| Routing primitives: `[param]`, `[...param]`, `[[...param]]`, `(group)` | `pyxle/routing/paths.py` | OK |
| Layout/template nesting, `slots` + `createSlots` exports | `pyxle/devserver/layouts.py` | OK |
| `<Head>` merge precedence (layout -> HEAD var -> page JSX -> runtime) and all dedup rules incl. `data-head-key` | `pyxle/ssr/head_merger.py` | OK |
| CSRF cookie name `pyxle-csrf`, header `x-csrf-token`, double-submit validation | `pyxle/devserver/csrf.py`, `client/Form.jsx`, `client/useAction.jsx` | OK |
| Action endpoint `POST /api/__actions/{page_path}/{action_name}` | `client/useAction.jsx`, `client/Form.jsx` | OK |
| Version claim "0.2.3 (beta)" in FAQ and `docs/README.md` | `pyproject.toml` version = 0.2.3, classifier = "4 - Beta" | OK |
| "95%+ coverage" claim in FAQ | `pyproject.toml` `coverage.report.fail_under = 95` | OK |
| `[langkit]` optional extras install path in `docs/guides/editor-setup.md` | `pyproject.toml` `[project.optional-dependencies].langkit` | OK |
| Project-structure.md file tree (presence of `.gitignore`, `package.json`, `postcss.config.cjs`, `tailwind.config.cjs`, `pyxle.config.json`, `requirements.txt`, `pages/api/pulse.py`, `pages/index.pyxl`, `pages/layout.pyxl`, `pages/styles/tailwind.css`, `public/branding/pyxle-mark.svg`, `public/styles/tailwind.css`, `public/favicon.ico`) | `pyxle/templates/scaffold/`, `pyxle/cli/init.py::build_template_registry` | OK |

---

## 2. Parity issues — docs drift from framework

### 2.1 `usePathname` is exported but undocumented

- **Source:** `pyxle/client/usePathname.jsx` is a fully implemented hook, re-exported from `pyxle/client/index.js`.
- **Problem:** It is **not** listed in `docs/reference/client-api.md` (neither in the header import example nor the "Hooks" section) and **not** in `docs/guides/client-components.md`.
- **Only mention in docs:** `docs/guides/editor-setup.md` references `<Slot>` / `usePathname` completions indirectly — no standalone documentation exists.
- **Fix:** Add `usePathname` to the client-api reference and client-components guide. Document its signature, SSR-safe default of `'/'`, and the `pyxle:routechange` / `popstate` listeners.

### 2.2 Scaffold `package.json` has no `dev:css` / `build:css` scripts, but multiple docs tell users to run them

- **Source:** `pyxle/templates/scaffold/package.json` ships only `dev`, `build`, `lint`.
- **Docs that reference the missing scripts:**
  - `docs/getting-started/quick-start.md` step 3 ("In a separate terminal, start the Tailwind watcher: `npm run dev:css`").
  - `docs/getting-started/project-structure.md` lists `npm run dev:css` and `npm run build:css` in the npm scripts table.
  - `pyxle/cli/init.py::log_next_steps` literally prints `npm run dev:css   # watches Tailwind...` in the post-init "Next steps" console output.
- **Context:** `docs/guides/styling.md` is aware of the shift and correctly describes the PostCSS/Vite-managed path that replaces the standalone watcher. The other three surfaces are stale.
- **Fix:** Choose one path. Either (a) add `dev:css`/`build:css` back to the scaffold `package.json`, or (b) update quick-start, project-structure, and `init.py::log_next_steps` to reflect the Vite-managed flow that styling.md already documents.

### 2.3 Quick-start describes a landing page that doesn't match the scaffold

- **Docs claim** (`docs/getting-started/quick-start.md`): "You should see the Pyxle landing page with a **hero section, feature cards, and a dark mode toggle**."
- **Actual scaffold** (`pyxle/templates/scaffold/pages/index.pyxl`): Renders a small centered card with the Pyxle logo, version string, current time, a "Get started" hint, and 4 external links (Docs / Homepage / GitHub / API). No hero section. No feature cards. No dark mode toggle.
- **Fix:** Rewrite the "Open localhost:8000" paragraph to describe what ships today, or refresh the scaffold to match.

### 2.4 Example scaffold snippets in project-structure.md are fiction

- **`pages/index.pyxl` example in docs:**
  ```python
  @server
  async def load_home(request):
      return {"message": "Hello, world!"}
  ```
  **Actual scaffold:** returns `{"version": __version__, "time": ..., "message": "You're ready to build with Pyxle."}`.

- **`pages/layout.pyxl` example in docs:**
  ```jsx
  export default function AppLayout({ children }) {
    return <div className="min-h-screen">{children}</div>;
  }
  ```
  **Actual scaffold:** exports `slots` + `createSlots`, uses `<>{children}</>` (no wrapping `<div>`, no `min-h-screen`).

- **Fix:** Either show the real scaffold contents or prefix the docs snippets with "illustrative — see the actual scaffold for the shipping version."

### 2.5 `RouteContext` property table in middleware.md is incomplete

- **Source:** `pyxle/devserver/route_hooks.py::RouteContext` exposes: `target`, `path`, `source_relative_path`, `source_absolute_path`, `module_key`, `content_hash`, `has_loader`, `head_elements`, `allowed_methods`.
- **Docs table** (`docs/guides/middleware.md`) lists only: `target`, `path`, `source_relative_path`, `module_key`, `has_loader`, `allowed_methods`.
- **Missing:** `source_absolute_path`, `content_hash`, `head_elements`.
- **Fix:** Add the missing three rows, or explicitly mark them internal if they shouldn't be part of the public hook contract.

### 2.6 `error.pyxl` props: `type` field not obviously populated

- **Docs claim** (`docs/guides/error-handling.md`): The `error` prop passed to an `error.pyxl` component has `message`, `statusCode`, `type`, `data`.
- **Source:** `pyxle/runtime.py` defines `LoaderError` with `message`, `status_code`, `data` only — no `type` attribute. The `type` value presumably comes from an error-rendering wrapper (`pyxle/devserver/error_pages.py` or the SSR template).
- **Action:** Read `error_pages.py` / SSR error-document code to verify that `type` (exception class name) is actually injected. If not, remove it from the docs; if yes, document where it originates.

### 2.7 `<Slot>` component referenced but not exported

- **Docs claim** (`docs/guides/editor-setup.md`): Pyxle components for autocomplete include `<Link>, <Script>, <Image>, <Head>, <Slot>, <ClientOnly>, <Form>`.
- **Source:** No `Slot.jsx` file exists in `pyxle/client/`. `index.js` does not export a `Slot` component. The `SlotProvider`/`normalizeSlots`/`mergeSlotLayers` imports in generated layout wrappers (`pyxle/devserver/layouts.py`) reference `pyxle/client/slot.jsx`, but that file is **not present** in the `pyxle/client/` directory listing.
- **Action:** Verify whether `pyxle/client/slot.jsx` exists elsewhere (generated at install time? shipped via another mechanism?). If the file is genuinely missing, **this is a framework bug** — any project that uses a `layout.pyxl` or `template.pyxl` would hit a missing-import error at SSR time, not just a doc problem. If `<Slot>` is a first-class component that users should call directly, document it in client-api.md; if it's internal scaffolding only, remove it from editor-setup.md.

### 2.8 `docs/guides/deployment.md` description of `pyxle build` mentions `npm run build:css`

- **Docs claim:** `pyxle build` "runs `npm run build` (which runs `build:css` for Tailwind, then Vite bundling)".
- **Scaffold reality:** `package.json` has only `build: "vite build"` — no chained `build:css`. Related to 2.2.
- **Fix:** align with whichever resolution 2.2 takes.

---

## 3. Unverified claims (worth a second pass before next release)

None of the below were proven wrong — but each is asserted in docs without a direct verification path in this audit:

1. **FAQ:** "1100+ tests" — not counted against `tests/` tree.
2. **`docs/guides/error-handling.md`:** `not-found.pyxl` directory scoping ("a `not-found.pyxl` in `pages/docs/` handles 404s within `/docs/*`") — not verified against the router.
3. **`docs/reference/runtime-api.md`:** The `HEAD` Python variable accepting `str | list[str]` static + `def HEAD(data)` callable forms — handled in `pyxle/compiler/parser.py` but the parser (40 KB) was not read end-to-end.
4. **`docs/guides/security.md`:** The exact XSS-sanitisation list (event handler stripping, `javascript:`/`vbscript:` removal, `<title>` text escaping) — `pyxle/ssr/head_merger.py::sanitize_head_element` confirms these three layers plus an extra `<base>` rejection and `data:` URL stripping that the docs do **not** mention. Consider documenting the extra two protections.
5. **`docs/reference/client-api.md`** states `refresh()` "does not reload the page or change scroll position" — this is a behavioural claim about `pyxle/runtime.js` (not in repo — likely generated). Verify against the runtime bundle.
6. **Architecture docs** (`docs/architecture/*.md`, 11 files) — not audited. Each should be checked against the corresponding source module (`pyxle/compiler/parser.py`, `pyxle/build/pipeline.py`, `pyxle/devserver/starlette_app.py`, `pyxle/ssr/renderer.py`, etc.).

---

## 4. Suggested fix order

1. **High** — resolve 2.7 (`<Slot>` / `slot.jsx`). If the file is missing this is a framework bug, not a doc bug. Blocks users of `layout.pyxl`.
2. **High** — resolve 2.2 (missing `dev:css`/`build:css` scripts). Affects every new user following quick-start.
3. **Medium** — 2.1 (document `usePathname`), 2.5 (complete `RouteContext` table), 2.6 (verify/document `error.type`).
4. **Low** — 2.3 and 2.4 (scaffold-example drift in quick-start and project-structure).
5. **Backlog** — 3 items; full architecture-docs pass.

---

## Appendix: Files inspected

**Pyxle repo:**
- Source: `pyxle/__init__.py`, `config.py`, `env.py`, `runtime.py`, `cli/__init__.py`, `cli/init.py`, `cli/scaffold.py`, `client/index.js`, `client/Head.jsx`, `client/Script.jsx`, `client/Image.jsx`, `client/ClientOnly.jsx`, `client/Form.jsx`, `client/useAction.jsx`, `client/usePathname.jsx`, `routing/__init__.py`, `routing/paths.py`, `ssr/__init__.py`, `ssr/head_merger.py`, `devserver/settings.py`, `devserver/scanner.py`, `devserver/layouts.py`, `devserver/route_hooks.py`, `build/__init__.py`, `templates/scaffold/` (all files), `pyproject.toml`, `README.md`.
- Docs: `docs/README.md`, `docs/faq.md`, `docs/getting-started/*.md`, `docs/core-concepts/*.md`, `docs/reference/*.md`, `docs/guides/*.md` (except `for-ai-agents.md`).

**pyxle-dev repo:**
- `README.md`, `pyxle.config.json`, root tree listing. The docs slug renderer at `pages/docs/[[...slug]].pyxl` was noted but not audited (likely reads docs from the Pyxle repo at build/request time).
