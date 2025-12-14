"""HTML document template helpers for SSR responses."""

from __future__ import annotations

import json
from dataclasses import dataclass
from html import escape
from typing import Any

from pyxle.devserver.routes import PageRoute
from pyxle.devserver.settings import DevServerSettings
from pyxle.devserver.styles import load_inline_stylesheets


@dataclass(frozen=True)
class DocumentShell:
  """Represents the static prefix/suffix for an HTML document."""

  prefix: str
  suffix: str


class ManifestLookupError(RuntimeError):
  """Raised when manifest-backed assets cannot be resolved."""


def render_document(
  *,
  settings: DevServerSettings,
  page: PageRoute,
  body_html: str,
  props: dict[str, Any],
  script_nonce: str,
  head_elements: tuple[str, ...],
) -> str:
  """Compose the HTML document for a rendered page."""
  try:
    shell = build_document_shell(
      settings=settings,
      page=page,
      props=props,
      script_nonce=script_nonce,
      head_elements=head_elements,
    )
  except ManifestLookupError:
    return _render_manifest_error(page)
  return f"{shell.prefix}{body_html}{shell.suffix}"


def build_document_shell(
  *,
  settings: DevServerSettings,
  page: PageRoute,
  props: dict[str, Any],
  script_nonce: str,
  head_elements: tuple[str, ...],
) -> DocumentShell:
  props_payload = _serialize_props(props)
  page_path_literal = json.dumps(page.client_asset_path)
  head_injections = render_head_markup(head_elements)
  head_block = (
    "\n  <meta data-pyxle-head-start=\"1\" />"
    + head_injections
    + "\n  <meta data-pyxle-head-end=\"1\" />"
  )
  nonce_attr = _format_nonce_attr(script_nonce)
  global_styles = _render_global_styles_markup(settings)

  if not settings.debug and settings.page_manifest is not None:
    manifest_entry = settings.page_manifest.get(page.path)
    if not isinstance(manifest_entry, dict):
      raise ManifestLookupError
    client_info = manifest_entry.get("client")
    if not isinstance(client_info, dict):
      raise ManifestLookupError
    js_file = client_info.get("file")
    if not isinstance(js_file, str) or not js_file:
      raise ManifestLookupError
    css_assets = client_info.get("css", [])
    css_links: list[str] = []
    if isinstance(css_assets, list):
      for asset in css_assets:
        if isinstance(asset, str):
          css_links.append(f'<link rel="stylesheet" href="/client/{asset}" />')
    css_html = "".join(f"\n    {link}" for link in css_links)
    js_src = f"/client/{js_file}"

    prefix = """<!DOCTYPE html>
<html lang=\"en\">
  <head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />{css_html}{global_styles}{head_block}
  </head>
  <body>
  <div id=\"root\">""".format(
      css_html=css_html,
      global_styles=global_styles,
      head_block=head_block,
    )
    suffix = """
  </div>
  <script id=\"__PYXLE_PROPS__\" type=\"application/json\"{nonce_attr}>{props_payload}</script>
  <script{nonce_attr}>window.__PYXLE_PAGE_PATH__ = {page_path_literal};</script>
  <script type=\"module\" src=\"{js_src}\"></script>
  </body>
</html>
""".format(
      nonce_attr=nonce_attr,
      props_payload=props_payload,
      page_path_literal=page_path_literal,
      js_src=js_src,
    )
    return DocumentShell(prefix=prefix, suffix=suffix)

  vite_origin = f"http://{settings.vite_host}:{settings.vite_port}"
  react_refresh_preamble = _render_react_refresh_preamble(vite_origin, nonce_attr)
  prefix = """<!DOCTYPE html>
<html lang=\"en\">
  <head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <script type=\"module\" src=\"{vite_origin}/@vite/client\"{nonce_attr}></script>{react_refresh_preamble}{global_styles}{head_block}
  </head>
  <body>
  <div id=\"root\">""".format(
    vite_origin=vite_origin,
    nonce_attr=nonce_attr,
    react_refresh_preamble=react_refresh_preamble,
    global_styles=global_styles,
    head_block=head_block,
  )
  suffix = """
  </div>
  <script id=\"__PYXLE_PROPS__\" type=\"application/json\"{nonce_attr}>{props_payload}</script>
  <script{nonce_attr}>window.__PYXLE_PAGE_PATH__ = {page_path_literal};</script>
  <script type=\"module\" src=\"{vite_origin}/client-entry.js\"></script>
  </body>
</html>
""".format(
    nonce_attr=nonce_attr,
    props_payload=props_payload,
    page_path_literal=page_path_literal,
    vite_origin=vite_origin,
  )
  return DocumentShell(prefix=prefix, suffix=suffix)


def _serialize_props(props: dict[str, Any]) -> str:
    payload = json.dumps(props, ensure_ascii=False, separators=(",", ":"))
    return payload.replace("</", "<\\/")


def render_head_markup(elements: tuple[str, ...]) -> str:
    default_title = "" if _head_contains_title(elements) else "\n    <title>Pyxle</title>"
    return default_title + _render_custom_head(elements)


def _render_custom_head(elements: tuple[str, ...]) -> str:
    if not elements:
        return ""

    rendered: list[str] = []
    for fragment in elements:
        if not fragment:
            continue

        lines = fragment.splitlines() or [fragment]
        for line in lines:
            rendered.append(f"\n    {line}")

    return "".join(rendered)


def _head_contains_title(elements: tuple[str, ...]) -> bool:
    for fragment in elements:
        if "<title" in fragment.lower():
            return True
    return False


def _render_react_refresh_preamble(vite_origin: str, nonce_attr: str) -> str:
    return """
    <script type=\"module\"{nonce_attr}>
      import RefreshRuntime from \"{vite_origin}/@react-refresh\";
      RefreshRuntime.injectIntoGlobalHook(window);
      window.$RefreshReg$ = () => {{}};
      window.$RefreshSig$ = () => (type) => type;
      window.__vite_plugin_react_preamble_installed__ = true;
    </script>
""".format(vite_origin=vite_origin, nonce_attr=nonce_attr)


def _render_manifest_error(page: PageRoute) -> str:
    page_path = escape(page.path)
    return """<!DOCTYPE html>
<html lang=\"en\">
  <head>
    <meta charset=\"utf-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
    <title>Pyxle • Missing Manifest Entry</title>
    <style>
      body {{ font-family: ui-sans-serif, system-ui; padding: 2rem; }}
      pre {{ background: #f3f4f6; padding: 1rem; border-radius: 0.5rem; }}
    </style>
  </head>
  <body>
    <main>
      <h1>Unable to locate page manifest entry</h1>
      <p>Pyxle could not find a compiled asset bundle for <code>{page_path}</code>.</p>
      <pre>Re-run `pyxle build` and ensure dist/page-manifest.json is deployed.</pre>
    </main>
  </body>
</html>
""".format(page_path=page_path)


def render_error_document(
    *,
    settings: DevServerSettings,
    page: PageRoute,
    error: BaseException,
) -> str:
    """Render a developer-friendly fallback when SSR fails."""

    vite_origin = f"http://{settings.vite_host}:{settings.vite_port}"
    error_type = escape(error.__class__.__name__)
    message = escape(str(error) or str(error.__class__.__name__))
    page_path = escape(page.path)

    return """<!DOCTYPE html>
<html lang=\"en\">
  <head>
    <meta charset=\"utf-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
    <title>Pyxle • Error</title>
    <script type=\"module\" src=\"{vite_origin}/@vite/client\"></script>
    <style>
      body {{
        font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, \"Segoe UI\", sans-serif;
        margin: 0;
        padding: 3rem 1.5rem;
        background: #111827;
        color: #f9fafb;
      }}
      .pyxle-error {{
        max-width: 48rem;
        margin: 0 auto;
        background: rgba(17, 24, 39, 0.65);
        border: 1px solid rgba(209, 213, 219, 0.2);
        border-radius: 0.75rem;
        padding: 2rem;
        box-shadow: 0 30px 60px rgba(15, 23, 42, 0.45);
      }}
      .pyxle-error code {{
        font-family: Menlo, Monaco, Consolas, \"Liberation Mono\", monospace;
        background: rgba(15, 23, 42, 0.6);
        padding: 0.25rem 0.5rem;
        border-radius: 0.5rem;
        color: #fca5a5;
      }}
    </style>
  </head>
  <body>
    <main class=\"pyxle-error\">
      <h1>Server Render Failed</h1>
      <p>While rendering <code>{page_path}</code>, Pyxle encountered a <strong>{error_type}</strong>.</p>
      <pre>{message}</pre>
      <p>Check your loader or component implementation and the server logs for full details.</p>
    </main>
  </body>
</html>
""".format(
        vite_origin=vite_origin,
        page_path=page_path,
        error_type=error_type,
        message=message,
    )


def _format_nonce_attr(value: str | None) -> str:
    if not value:
        return ""
    return f' nonce="{value}"'


def _render_global_styles_markup(settings: DevServerSettings) -> str:
  if not settings.global_stylesheets:
    return ""
  fragments: list[str] = []
  for sheet, contents in load_inline_stylesheets(settings.global_stylesheets):
    escaped = _escape_style_contents(contents)
    fragments.append(f"\n  <style data-pyxle-style=\"{sheet.identifier}\">{escaped}</style>")
  return "".join(fragments)


def _escape_style_contents(value: str) -> str:
  if not value:
    return ""
  return value.replace("</", "<\\/")

__all__ = [
  "DocumentShell",
  "ManifestLookupError",
  "build_document_shell",
  "render_document",
  "render_error_document",
  "render_head_markup",
]
