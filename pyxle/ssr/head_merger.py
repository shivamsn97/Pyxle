"""Head element merging and deduplication utilities."""

from __future__ import annotations

import re
from html.parser import HTMLParser


class HeadElementAttributeParser(HTMLParser):
    """Parse HTML elements to extract attributes for deduplication."""

    def __init__(self):
        super().__init__()
        self.tag_name: str | None = None
        self.attributes: dict[str, str] = {}
        self.found = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Capture the first tag and its attributes."""
        if not self.found:
            self.tag_name = tag.lower()
            # Convert attrs list to dict, handling None values for boolean attrs
            self.attributes = {name.lower(): (value or name) for name, value in attrs}
            self.found = True

    def get_tag_and_attributes(self, html: str) -> tuple[str | None, dict[str, str]]:
        """Parse HTML and return (tag_name, attributes_dict)."""
        try:
            self.feed(html)
            return self.tag_name, self.attributes
        except Exception:
            # If parsing fails, return None
            return None, {}


class HeadElementSplitter(HTMLParser):
    """Split an HTML head block into individual element strings."""

    def __init__(self):
        super().__init__()
        self.elements: list[str] = []
        self.current_element: list[str] = []
        self.current_tag: str | None = None
        self.depth: int = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Start a new element."""
        if self.depth == 0:
            # Reconstruct the tag with attributes
            attr_parts = []
            for name, value in attrs:
                if value:
                    attr_parts.append(f'{name}="{value}"')
                else:
                    attr_parts.append(name)
            attrs_str = " " + " ".join(attr_parts) if attr_parts else ""
            
            is_self_closing = self._is_self_closing(tag)
            if is_self_closing:
                self.current_element = [f"<{tag}{attrs_str}/>"]
            else:
                self.current_element = [f"<{tag}{attrs_str}>"]
            
            self.current_tag = tag.lower()
            if is_self_closing:
                self._save_element()
            else:
                self.depth = 1

    def handle_endtag(self, tag: str) -> None:
        """End the current element."""
        if self.depth > 0 and tag.lower() == self.current_tag:
            self.current_element.append(f"</{tag}>")
            self.depth -= 1
            if self.depth == 0:
                self._save_element()

    def handle_data(self, data: str) -> None:
        """Add data between tags."""
        if self.depth > 0:
            self.current_element.append(data)

    def _is_self_closing(self, tag: str) -> bool:
        """Check if tag is self-closing."""
        return tag.lower() in {"meta", "link", "br", "hr", "img", "input", "area", "base", "col", "embed", "source", "track", "wbr"}

    def _save_element(self) -> None:
        """Save the current element and reset."""
        if self.current_element:
            element = "".join(self.current_element).strip()
            if element:
                self.elements.append(element)
        self.current_element = []
        self.current_tag = None

    def split(self, html_block: str) -> list[str]:
        """Parse and split the HTML block into individual elements."""
        try:
            self.feed(html_block)
            return self.elements
        except Exception:
            # If parsing fails, return empty list (elements might be malformed)
            return []


def _needs_splitting(html_block: str) -> bool:
    """Check if a head block contains multiple top-level HTML elements."""
    parser = HeadElementSplitter()
    parser.split(html_block)
    return len(parser.elements) > 1


def _split_head_block_into_elements(html_block: str) -> list[str]:
    """Split a head block containing multiple HTML elements into individual element strings.
    
    Uses HTMLParser to robustly handle both self-closing tags (<meta />, <link />)
    and paired tags (<title>...</title>).
    """
    splitter = HeadElementSplitter()
    return splitter.split(html_block)


def _extract_dedupe_key(html: str) -> str | None:
    """Extract deduplication key from HTML element string."""
    html = html.strip()
    if not html:
        return None

    # Parse the HTML element to extract tag and attributes
    parser = HeadElementAttributeParser()
    tag_name, attrs = parser.get_tag_and_attributes(html)

    if not tag_name:
        return None

    # Manual key: data-head-key="X"
    if "data-head-key" in attrs:
        return f"key:{attrs['data-head-key']}"

    # Title tag
    if tag_name == "title":
        return "title"

    # Meta tag
    if tag_name == "meta":
        # Meta tag with name
        if "name" in attrs:
            return f"meta:name:{attrs['name']}"
        # Meta tag with property
        if "property" in attrs:
            return f"meta:property:{attrs['property']}"
        # Meta tag with charset (dedupe by type)
        if "charset" in attrs:
            return "meta:charset"

    # Link tag
    if tag_name == "link":
        rel = attrs.get("rel", "")
        href = attrs.get("href", "")
        # For canonical, dedupe by rel only (only one canonical)
        if rel.lower() == "canonical":
            return "link:canonical"
        # For others, dedupe by rel + href
        if rel:
            return f"link:{rel}:{href}"

    # Script tag with src
    if tag_name == "script":
        if "src" in attrs:
            return f"script:src:{attrs['src']}"

    # No deduplication key (keep all instances)
    return None


# ---------------------------------------------------------------------------
# XSS sanitization for HEAD elements
# ---------------------------------------------------------------------------

# Matches event-handler attributes: onclick="...", onerror='...', onload=val
_EVENT_HANDLER_ATTR_RE = re.compile(
    r"""\s+on[a-z]+\s*=\s*(?:"[^"]*"|'[^']*'|\S+)""",
    re.IGNORECASE,
)

# Matches javascript:/vbscript: protocols in href/src/action attributes
_DANGEROUS_URL_ATTR_RE = re.compile(
    r"""((?:href|src|action)\s*=\s*['"]?)\s*(javascript|vbscript)\s*:""",
    re.IGNORECASE,
)

# Opening and closing <title> tag patterns
_TITLE_OPEN_RE = re.compile(r"<title[^>]*>", re.IGNORECASE)
_TITLE_CLOSE_RE = re.compile(r"</title\s*>", re.IGNORECASE)


def sanitize_head_element(html: str) -> str:
    """Sanitize a single HEAD element to prevent XSS injection.

    Applies three layers of protection:

    1. **Title text escaping** — escapes ``<`` and ``>`` inside
       ``<title>…</title>`` so that injected closing tags and script tags
       become inert text.
    2. **Event-handler stripping** — removes ``on*`` attributes
       (``onclick``, ``onerror``, ``onload``, …).
    3. **Dangerous URL neutralisation** — replaces ``javascript:`` and
       ``vbscript:`` protocol URLs in ``href`` / ``src`` / ``action``
       attributes with an empty string.
    """
    html = html.strip()
    if not html:
        return html

    # Layer 1: escape angle brackets inside <title> text content
    html = _escape_title_text_content(html)

    # Layer 2: strip event-handler attributes
    html = _EVENT_HANDLER_ATTR_RE.sub("", html)

    # Layer 3: neutralise dangerous protocol URLs
    html = _DANGEROUS_URL_ATTR_RE.sub(r"\1", html)

    return html


def _escape_title_text_content(html: str) -> str:
    """Escape ``<`` and ``>`` between ``<title>`` and ``</title>``.

    Uses the *last* ``</title>`` occurrence so that an injected early
    ``</title>`` is captured and escaped rather than treated as the real
    closing tag.
    """
    open_match = _TITLE_OPEN_RE.search(html)
    if open_match is None:
        return html

    close_matches = list(_TITLE_CLOSE_RE.finditer(html))
    if not close_matches:
        return html

    last_close = close_matches[-1]
    prefix = html[: open_match.end()]
    content = html[open_match.end() : last_close.start()]
    suffix = html[last_close.start() :]

    # Only escape angle brackets — preserve existing character entities
    escaped = content.replace("<", "&lt;").replace(">", "&gt;")
    return prefix + escaped + suffix


def merge_head_elements(
    *,
    head_variable: tuple[str, ...],
    head_jsx_blocks: tuple[str, ...],
    layout_head_jsx_blocks: tuple[str, ...] = (),
    runtime_head_blocks: tuple[str, ...] = (),
) -> tuple[str, ...]:
    """Merge HEAD elements from every source with deduplication.

    Precedence order (higher priority overrides lower):

    1. Layout JSX blocks — static extraction from ancestor ``layout.pyx``
       and ``template.pyx`` files.
    2. Page ``HEAD`` variable — server-side declaration in the page module.
    3. Page JSX blocks — static extraction of ``<Head>`` blocks in the
       page file at compile time.
    4. Runtime ``<Head>`` registrations — produced when the ``<Head>``
       component executes during SSR and calls ``renderToStaticMarkup``
       on its children. These reflect the actual rendered output,
       including evaluated JSX expressions, so they always win over
       static extraction.

    Deduplication rules (higher priority always wins, first occurrence
    wins within the same priority):

    - ``<title>`` — dedupe by tag name
    - ``<meta name="X">`` — dedupe by ``name`` attribute
    - ``<meta property="X">`` — dedupe by ``property`` attribute
    - ``<meta charset>`` — only one allowed
    - ``<link rel="canonical">`` — only one allowed
    - ``<link rel="X" href="Y">`` — dedupe by ``rel`` + ``href``
    - ``<script src="X">`` — dedupe by ``src``
    - ``data-head-key="X"`` — manual deduplication key

    Elements without a dedupe key are kept (e.g. preconnect links).

    Note: Head blocks may contain multiple HTML elements in a single
    string (from ``<Head>...</Head>`` JSX blocks). This function splits
    them into individual elements before deduplication.

    Runtime ordering note: ``runtime_head_blocks`` arrives in React
    render order (outer layouts register first, the page registers
    last). We process this list in *reverse* so the deepest registration
    (the page) is examined first and wins via the standard
    "first-occurrence-wins-within-priority" rule. This matches the
    react-helmet convention that components closer to the leaf win.
    """

    # Dictionary: dedupe_key -> (html, priority)
    # Higher priority values override lower priority values
    seen_keys: dict[str | None, tuple[str, int]] = {}

    # Split head blocks into individual elements, then sanitise each one.
    layout_elements = []
    for block in layout_head_jsx_blocks:
        for el in _split_head_block_into_elements(block):
            layout_elements.append(sanitize_head_element(el))

    head_var_elements = [sanitize_head_element(el) for el in head_variable]

    page_elements = []
    for block in head_jsx_blocks:
        for el in _split_head_block_into_elements(block):
            page_elements.append(sanitize_head_element(el))

    # Runtime blocks: reversed so the deepest (page) registration is
    # processed first and wins over outer (layout) registrations within
    # the same priority tier. See the docstring for rationale.
    runtime_elements = []
    for block in reversed(runtime_head_blocks):
        for el in _split_head_block_into_elements(block):
            runtime_elements.append(sanitize_head_element(el))

    # Priority 1: Layout JSX blocks (lowest priority)
    for element in layout_elements:
        element = element.strip()
        if element:
            dedupe_key = _extract_dedupe_key(element)
            if dedupe_key is None:
                # No dedupe key, we'll handle separately (always include non-deupeable items)
                if None not in seen_keys:
                    seen_keys[None] = (element, 1)
            else:
                # Store if we haven't seen this key or if this has higher priority
                if dedupe_key not in seen_keys:
                    seen_keys[dedupe_key] = (element, 1)

    # Priority 2: Page HEAD variable
    for element in head_var_elements:
        element = element.strip()
        if element:
            dedupe_key = _extract_dedupe_key(element)
            if dedupe_key is None:
                # No dedupe key, always add to result later
                # Use a special marker to track non-deupeable items
                pass
            elif dedupe_key not in seen_keys or seen_keys[dedupe_key][1] < 2:
                # Override if this is the first occurrence or has higher priority
                seen_keys[dedupe_key] = (element, 2)

    # Priority 3: Page JSX blocks (static compile-time extraction)
    for element in page_elements:
        element = element.strip()
        if element:
            dedupe_key = _extract_dedupe_key(element)
            if dedupe_key is None:
                # No dedupe key, always add to result later
                pass
            elif dedupe_key not in seen_keys or seen_keys[dedupe_key][1] < 3:
                # Override if this is the first occurrence or has higher priority
                seen_keys[dedupe_key] = (element, 3)

    # Priority 4: Runtime <Head> registrations (highest priority)
    #
    # These come from <Head> components executing during SSR. They
    # contain fully evaluated JSX (including expressions like
    # ``{pageTitle}``) and therefore always supersede the static
    # extraction in priority 3 when the same dedupe key is present.
    for element in runtime_elements:
        element = element.strip()
        if element:
            dedupe_key = _extract_dedupe_key(element)
            if dedupe_key is None:
                # No dedupe key, always add to result later
                pass
            elif dedupe_key not in seen_keys or seen_keys[dedupe_key][1] < 4:
                seen_keys[dedupe_key] = (element, 4)

    # Build result: include all deduped elements in order, plus non-deupeable items
    result: list[str] = []
    non_deupeable: list[str] = []

    # Collect non-deupeable items from all sources
    for element in layout_elements:
        element = element.strip()
        if element and _extract_dedupe_key(element) is None:
            non_deupeable.append(element)

    for element in head_var_elements:
        element = element.strip()
        if element and _extract_dedupe_key(element) is None:
            non_deupeable.append(element)

    for element in page_elements:
        element = element.strip()
        if element and _extract_dedupe_key(element) is None:
            non_deupeable.append(element)

    for element in runtime_elements:
        element = element.strip()
        if element and _extract_dedupe_key(element) is None:
            non_deupeable.append(element)

    # Add deduped items first (in order they were first seen)
    for key in seen_keys:
        if key is not None:  # Skip the None marker
            html, _ = seen_keys[key]
            result.append(html)

    # Add non-deupeable items (e.g., preconnect links without href)
    result.extend(non_deupeable)

    return tuple(result)


__all__ = ["merge_head_elements", "sanitize_head_element"]

