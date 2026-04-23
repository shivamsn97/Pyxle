# Plugins

Pyxle plugins are reusable pieces of functionality — database layers, auth systems, storage adapters — that a host app composes via `pyxle.config.json` rather than hand-wiring in its entry point. The design is deliberately Django-inspired: declare what you want, and the framework handles discovery, startup order, and lifecycle.

> **Status (0.3.0).** This guide covers the Phase A plugin surface: lifecycle hooks, named services, and middleware contribution. Page contribution (plugins shipping their own `.pyxl` pages that get merged into the host's route tree — the "pyxle-auth ships a default `/sign-in` page" use case) is a Phase B follow-up. Everything documented here is stable; the additions in Phase B will be strictly additive.

## TL;DR

Declare plugins in `pyxle.config.json`:

```json
{
  "plugins": [
    "pyxle-db",
    {"name": "pyxle-auth", "settings": {"cookieDomain": ".example.com"}}
  ]
}
```

Pyxle imports each plugin, calls its `on_startup` hook inside the ASGI lifespan, and exposes shared services to your loaders and actions:

```python
@server
async def load(request):
    auth = request.app.state.pyxle_plugins.require("auth.service")
    user = await auth.resolve_session(...)
    return {"user": user}
```

## Config schema

Each entry in `plugins` is either a **string** or an **object**:

```json
{
  "plugins": [
    "pyxle-db",
    {
      "name": "pyxle-auth",
      "module": "pyxle_auth.plugin",
      "attribute": "plugin",
      "settings": {"cookieDomain": ".pyxle.app"}
    }
  ]
}
```

| Field | Required | Default | Description |
|---|---|---|---|
| `name` | ✅ | — | User-facing name. Used for service-namespace identification and error messages. |
| `module` | — | `{name.replace('-', '_')}.plugin` | Python module where the plugin object lives. |
| `attribute` | — | `"plugin"` | Attribute on `module` to fetch. A `PyxlePlugin` subclass is instantiated; an instance is used as-is. |
| `settings` | — | `{}` | Per-app config dict forwarded to the plugin instance via `self.settings`. |

The string form is sugar for `{"name": "...", "module": "..._plugin.plugin"}`. Both sugar and object form work side-by-side.

## Authoring a plugin

A plugin is a regular Python package that exports a `PyxlePlugin` subclass (or instance) named `plugin`:

```python
# pyxle_hello/plugin.py
from pyxle.plugins import PyxlePlugin, PluginContext


class HelloService:
    def greet(self, name: str) -> str:
        return f"Hello, {name}!"


class Plugin(PyxlePlugin):
    name = "pyxle-hello"
    version = "0.1.0"

    async def on_startup(self, ctx: PluginContext) -> None:
        # Register services under a short namespace so consumers can
        # ``ctx.require("hello.service")``.
        ctx.register("hello.service", HelloService())

    async def on_shutdown(self, ctx: PluginContext) -> None:
        # Flush, close connections, stop background tasks.
        pass


# Either export the class (Pyxle instantiates it) or an instance:
plugin = Plugin
```

Reading plugin settings inside the hook:

```python
class Plugin(PyxlePlugin):
    name = "pyxle-hello"

    async def on_startup(self, ctx: PluginContext) -> None:
        prefix = self.settings.get("greetingPrefix", "Hello")
        ctx.register("hello.service", HelloService(prefix=prefix))
```

Settings come from the `settings` object on the config entry — the framework doesn't validate them, so the plugin is responsible for its own schema.

## Lifecycle

```
startup order:  A → B → C   (declaration order from pyxle.config.json)
shutdown order: C → B → A   (reverse — so earlier plugins' services
                             are still available during later teardown)
```

Startup failures abort the ASGI app immediately — a plugin that can't reach its database should raise, and Pyxle propagates it so Starlette refuses to serve traffic. Shutdown failures are logged but don't abort teardown of the remaining plugins.

## Consuming services from your app

Inside any `@server` loader or `@action`:

```python
@server
async def load(request):
    ctx = request.app.state.pyxle_plugins
    db = ctx.require("db.database")
    rows = await db.fetchall("SELECT * FROM posts LIMIT 20")
    return {"posts": [dict(r) for r in rows]}
```

`.require(name)` raises `PluginServiceError` with the list of available service names when the key is missing — so typos are obvious at the first request instead of silently resolving to `None`.

For optional services, use `.get(name, default)`:

```python
telemetry = ctx.get("telemetry.client")  # None if no telemetry plugin installed
if telemetry:
    telemetry.record("page.load", {"route": "/posts"})
```

## Middleware contribution

A plugin can declare ASGI middleware it wants appended to the host app's stack:

```python
class Plugin(PyxlePlugin):
    name = "pyxle-requestid"

    def middleware(self):
        return [
            ("pyxle_requestid.middleware:RequestIdMiddleware", {"header": "x-request-id"}),
        ]
```

Each entry is `(import_string, options)` — the import string can be either `"package.module:Class"` or `"package.module.Class"`. Options are passed through as `Middleware(cls, **options)`, matching the shape of `pyxle.config.json::middleware`.

## Service naming conventions

| Namespace | Owner |
|---|---|
| `db.*` | `pyxle-db` |
| `auth.*` | `pyxle-auth` |
| `<plugin-short-name>.*` | Each official plugin gets its own prefix. |
| `app.*` | Reserved for the host app's own ad-hoc registrations. |

Plugins should document every name they register so consumers know what to ask for.

## Error handling

| Condition | Exception |
|---|---|
| Bad config entry (missing name, non-list, etc.) | `ConfigError` at load time |
| Module can't be imported | `PluginResolutionError` at startup |
| Attribute is missing / wrong type | `PluginResolutionError` at startup |
| `on_startup` raises | `PluginError` wrapping the original — ASGI startup aborts |
| `require()` misses | `PluginServiceError` at request time |

## Limitations (Phase A)

- Plugins cannot contribute their own `.pyxl` pages yet. To ship a default sign-in page today, the plugin author provides the source string and the host app imports it — a Phase B feature will let plugins contribute a `pages_dir()` directly.
- Plugin migrations aren't auto-discovered. A plugin that needs schema changes should register a "run migrations" method the host app calls from its own startup code. Phase B adds `migrations_dir()` + auto-application.
- Plugins cannot depend on each other by declaring it explicitly. Ordering is manual via the config list — put `pyxle-db` before `pyxle-auth` because auth depends on a database.

Phase B will address all three. Phase A ships now because the lifecycle + service registry alone already removes most of the hand-wiring in host apps.

## See also

- [`runtime-api.md`](../reference/runtime-api.md) — `@server` / `@action` reference for consumers
- [Middleware](middleware.md) — app-level middleware, for the `pyxle.config.json::middleware` array
