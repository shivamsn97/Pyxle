# pyxle-auth

> 🚧 **Coming soon — not yet released.**
>
> `pyxle-auth` is being developed in internal beta and is **not** available on PyPI yet. There is nothing to `pip install` today. This page is a placeholder so we can link to it from the plugin docs once the package ships.

## What it will be

Email + password session authentication for Pyxle apps, wired in via the [plugin system](../guides/plugins.md):

- **Argon2id** password hashing with sane production defaults.
- `HttpOnly` / `Secure` session cookies with **sliding expiration** and a hard absolute cap.
- Per-IP **and** per-email **rate limits** on sign-in / sign-up to blunt credential-stuffing.
- A short helper API:

  ```python
  from pyxle_auth import get_auth_service, InvalidCredentials

  @action
  async def sign_in(request):
      body = await request.json()
      auth = get_auth_service()
      try:
          user, cookie = await auth.sign_in(
              email=body["email"], password=body["password"],
              ip=request.client.host,
              user_agent=request.headers.get("user-agent", ""),
          )
      except InvalidCredentials:
          raise ActionError("Invalid email or password", status_code=401)
      ...
  ```

- Will depend on [`pyxle-db`](pyxle-db.md) as a peer plugin.

## Status

- **Source**: internal repo — not public yet.
- **PyPI**: not published.
- **ETA**: very soon. Subscribe on [pyxle.dev](https://pyxle.dev) to be notified when it lands.

## See also

- [Plugins guide](../guides/plugins.md) — plugin system overview.
- [Plugins API reference](../reference/plugins-api.md) — the API third-party plugins build on today.
- [pyxle-db](pyxle-db.md) — companion database plugin (also coming soon).
