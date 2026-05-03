# pyxle-auth

> **Internal beta — not yet public.** `pyxle-auth` is currently in internal beta and isn't published on PyPI yet. The docs below describe the API as it will ship. Public release is coming very soon.

Email + password session authentication for Pyxle apps. Argon2id password hashing, `HttpOnly`/`Secure` cookies with sliding expiration, per-identifier rate limits on sign-in and sign-up.

- **Package**: [`pyxle-auth`](https://pypi.org/project/pyxle-auth/)
- **Source**: `pyxle-framework/pyxle-plugins/packages/pyxle-auth`
- **Requires**: `pyxle-framework >= 0.3.0`, [`pyxle-db`](pyxle-db.md) as a peer plugin.

## Install

```bash
pip install pyxle-auth
```

Then list **after** `pyxle-db` in `pyxle.config.json`:

```json
{
  "plugins": [
    "pyxle-db",
    {
      "name": "pyxle-auth",
      "settings": {
        "cookieDomain": ".pyxle.app",
        "cookieSecure": true,
        "sessionTtlSeconds": 2592000,
        "strict": true
      }
    }
  ]
}
```

Order matters: `pyxle-auth` calls `plugin_ctx.require("db.database")` during startup, so `pyxle-db` must run first.

## Using the service

```python
from pyxle_auth import get_auth_service, InvalidCredentials

@action
async def sign_in(request):
    body = await request.json()
    auth = get_auth_service()
    try:
        user, cookie = await auth.sign_in(
            email=body["email"],
            password=body["password"],
            ip=request.client.host,
            user_agent=request.headers.get("user-agent", ""),
        )
    except InvalidCredentials:
        raise ActionError("Invalid email or password", status_code=401)

    # Return the cookie to the client
    from starlette.responses import JSONResponse
    response = JSONResponse({"ok": True, "userId": user.id})
    response.set_cookie(**cookie.kwargs())
    return response
```

`get_auth_service()` returns the `AuthService` — the same instance for every request. It wraps the active database from `pyxle-db` with argon2 hashing and session lifecycle.

## Resolving the current user

```python
from pyxle_auth import get_auth_service, get_auth_settings

@server
async def load(request):
    auth = get_auth_service()
    settings = get_auth_settings()
    cookie_value = request.cookies.get(settings.cookie_name, "")
    user = await auth.resolve_session(cookie_value=cookie_value)
    return {"user": {"id": user.id, "email": user.email} if user else None}
```

`resolve_session` extends the session's `expires_at` on each hit (sliding expiration). It returns `None` for missing / expired / revoked sessions — no exceptions on the happy-path no-session case.

## Signing out

```python
@action
async def sign_out(request):
    auth = get_auth_service()
    settings = get_auth_settings()
    cookie_value = request.cookies.get(settings.cookie_name, "")
    delete_cookie = await auth.sign_out(cookie_value=cookie_value)

    from starlette.responses import JSONResponse
    response = JSONResponse({"ok": True})
    response.set_cookie(**delete_cookie.kwargs())
    return response
```

## Config reference

All settings are optional. Defaults tuned for production; relax explicitly for local dev.

### Password policy

| Key | Type | Default | Description |
|---|---|---|---|
| `argonTimeCost` | `integer` | `3` | argon2 `t` parameter. Higher = slower to verify, safer against offline attacks. |
| `argonMemoryKib` | `integer` | `65536` | argon2 memory parameter in KiB. Default 64 MiB. |
| `argonParallelism` | `integer` | `2` | argon2 `p` parameter (lanes). |
| `passwordMinLength` | `integer` | `8` | Rejected on sign-up below this length. |
| `passwordMaxLength` | `integer` | `1024` | Rejected above this length (defensive; passwords should fit in a single HTTP header pair). |

For tests, knock argon down to `{ argonTimeCost: 1, argonMemoryKib: 8, argonParallelism: 1 }` — a real password verification otherwise costs hundreds of ms per test.

### Sessions

| Key | Type | Default | Description |
|---|---|---|---|
| `sessionTtlSeconds` | `integer` | `2592000` (30d) | Sliding expiration. Every valid request that resolves a session extends `expires_at` by this much. |
| `sessionAbsoluteMaxSeconds` | `integer` | `7776000` (90d) | Hard cap from session creation. After this, the session is revoked regardless of activity. |

### Cookie

| Key | Type | Default | Description |
|---|---|---|---|
| `cookieName` | `string` | `"pyxle_session"` | Cookie name. |
| `cookieSecure` | `boolean` | `true` | Set the `Secure` flag. Keep `true` in production. |
| `cookieSameSite` | `string` | `"Lax"` | `Lax` / `Strict` / `None`. `None` requires `Secure=true`. |
| `cookieDomain` | `string \| null` | `null` | E.g. `".pyxle.app"` for cross-subdomain sharing. `null` → bound to the current host. |
| `cookiePath` | `string` | `"/"` | Cookie `Path` attribute. |

### Rate limits

| Key | Type | Default | Description |
|---|---|---|---|
| `rateLimitSignInPerHour` | `integer` | `10` | Max sign-in attempts per hour per IP **and** per email address (separate buckets). |
| `rateLimitSignUpPerHour` | `integer` | `5` | Max sign-up attempts per hour per IP. |

Successful sign-in resets the bucket so legitimate users aren't locked out after a few typos.

### Other

| Key | Type | Default | Description |
|---|---|---|---|
| `requireEmailVerified` | `boolean` | `false` | If `true`, `sign_in` raises `EmailNotVerified` for accounts without a verified email. |
| `strict` | `boolean` | `true` | Hard-requires `cookieSecure=true`. Set `false` for local HTTP dev. |
| `ensureSchema` | `boolean` | `true` | Run `AuthService.ensure_schema()` at startup, creating the `users` / `sessions` / `ratelimit_buckets` tables if absent. Set `false` if your own migrations file already creates them. |

### Unknown keys are rejected

Mistyping `cookeiSecure` instead of `cookieSecure` raises at startup — the error lists every supported key. No silent fallbacks to default.

## Registered services

| Service name | Type | Returned by |
|---|---|---|
| `auth.service` | `AuthService` | `get_auth_service()` |
| `auth.settings` | `AuthSettings` | `get_auth_settings()` |

## Error types

| Exception | When it's raised | HTTP translation |
|---|---|---|
| `InvalidCredentials` | Wrong password, or email doesn't exist (indistinguishable to prevent user enumeration). | 401 |
| `AccountExists` | Sign-up with an email already in the database. | 409 |
| `RateLimited` | Too many attempts in the current hour bucket. `retry_after_seconds` attached. | 429 |
| `WeakPassword` | Password fails the configured policy. | 400 |
| `EmailNotVerified` | `requireEmailVerified=True` and the user hasn't verified. | 403 |

Best practice: let the `@action` handler catch the specific exceptions it cares about and convert to `ActionError` with a user-safe message. Never display the exception's internal string directly — some of the error messages include cause detail meant for logs only.

## Schema

`pyxle-auth` creates three tables in the database provided by `pyxle-db`:

```
users               (id, email, password_hash, email_verified_at, created_at, plan)
sessions            (token_sha256, user_id, created_at, expires_at, user_agent, ip)
ratelimit_buckets   (key, count, expires_at)
```

Session tokens are **not** stored in the database — only `SHA-256(token)` is. A database leak doesn't let an attacker resurrect sessions without separately capturing the raw tokens.

If your app's own migration file already creates these tables, pass `"ensureSchema": false` in the plugin settings to skip the `CREATE TABLE IF NOT EXISTS` pass at startup.

## Testing

For unit tests, weaken the argon params so the suite doesn't spend seconds on hashes:

```json
{
  "plugins": [
    "pyxle-db",
    {
      "name": "pyxle-auth",
      "settings": {
        "argonTimeCost": 1,
        "argonMemoryKib": 8,
        "argonParallelism": 1,
        "cookieSecure": false,
        "strict": false
      }
    }
  ]
}
```

Or instantiate `AuthService` directly and call `AuthSettings().for_tests()` — see the plugin's own test suite for the exact pattern.

## Direct instantiation (without the plugin system)

```python
from pyxle_db import connect
from pyxle_auth import AuthService, AuthSettings

db = await connect("app.db")
auth = AuthService(db, AuthSettings())
await auth.ensure_schema()
```

Appropriate for tests, CLI scripts, or apps that don't use Pyxle's ASGI server. For a normal Pyxle app, the plugin wiring saves you this boilerplate.

## See also

- [Plugins guide](../guides/plugins.md) — plugin system overview.
- [Plugins API reference](../reference/plugins-api.md) — `PluginContext`, `plugin(name)` lookup.
- [pyxle-db](pyxle-db.md) — peer dependency.
- [Security](../guides/security.md) — CSRF protection and other security guidance.
