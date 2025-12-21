# Testing Strategy

Pyxle projects are regular Python + React apps, so you can use your preferred testing stack. The Pyxle repo itself uses:

- `pytest --cov=pyxle --cov-report=term-missing`
- `vitest --coverage`

## Recommended approach for apps

### Python

- Test loaders, API routes, and middleware with `pytest` + `httpx.AsyncClient` or `starlette.testclient.TestClient`.
- Because loaders receive the Starlette `Request`, you can construct fake requests via `Request(scope)` for unit tests or spin up an ASGI app for integration tests.

### React/JS

- Use `vitest` + `@testing-library/react` to test compiled components (they are plain JSX modules).
- If you prefer TypeScript, add a `tsconfig.json` and let Vite handle it; Pyxle does not limit file extensions in `pages/` (only `.pyx` is special).

### End-to-end

- Any Playwright/Cypress-style tool works. Start `pyxle dev`, run the E2E suite against `http://127.0.0.1:8000`.

## CI tips

1. Install Python + Node deps (`pyxle install --python --node`).
2. Run Tailwind build (`npm run build:css`).
3. Execute tests.
4. Run `pyxle build` and upload `dist/` artifacts.

## Compare with Next.js

Next.js leans on Jest/Playwright; Pyxle leaves the choice to you. The only Pyxle-specific addition is the `.pyx` compiler, which you can drive via `pyxle compile` inside tests if you need to assert on generated artifacts.

### Example GitHub Actions matrix

```yaml
jobs:
	test:
		runs-on: ubuntu-latest
		strategy:
			matrix:
				python: ['3.11']
				node: ['20']
		steps:
			- uses: actions/checkout@v4
			- uses: actions/setup-python@v5
				with:
					python-version: ${{ matrix.python }}
			- uses: actions/setup-node@v4
				with:
					node-version: ${{ matrix.node }}
			- run: pip install -r requirements.txt
			- run: npm install
			- run: npm run build:css
			- run: pytest
			- run: vitest run --coverage
```

---
**Navigation:** [← Previous](langkit.md) | [Next →](../reference/index.md)
