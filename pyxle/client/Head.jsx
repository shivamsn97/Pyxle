/**
 * <Head> — declare elements that belong in the document <head>.
 *
 * Works on both tiers of the render pipeline:
 *
 *   • SSR       — renders children to static markup and registers them
 *                 with the framework's head registry, so they land in the
 *                 initial HTML response.
 *
 *   • Client    — on mount, adopts the equivalent SSR-rendered elements
 *                 (matched by tag + key attribute) so we don't duplicate
 *                 them.  On update, the adopted nodes are removed and
 *                 fresh ones inserted, so state-driven head changes (e.g.
 *                 a dynamic <title>) actually update the document.
 *                 On unmount, everything this instance owns is removed and
 *                 the previous <title> is restored.
 *
 * Multiple <Head> components compose — each one owns the nodes it rendered.
 */
import { useEffect } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

const OWNER_ATTR = 'data-pyxle-head-client';
// Key attributes that identify "the same" head element across renders.
// Order matters: we pick the first one that the declared element has.
const KEY_ATTRS = ['name', 'property', 'rel', 'href', 'src', 'charset', 'http-equiv'];


function _findEquivalentHeadElement(target) {
  const tag = target.tagName.toLowerCase();
  const keyAttr = KEY_ATTRS.find((a) => target.hasAttribute(a));
  if (!keyAttr) {
    // Without a discriminating attribute we can't safely adopt — caller will
    // insert a fresh copy instead.
    return null;
  }

  const keyValue = target.getAttribute(keyAttr);
  const escape = (typeof CSS !== 'undefined' && CSS.escape) || ((s) => s);
  const selector = `${tag}[${keyAttr}="${escape(keyValue)}"]:not([${OWNER_ATTR}])`;

  try {
    return document.head.querySelector(selector);
  } catch {
    return null;
  }
}


function _applyHeadMarkup(markup) {
  if (!markup) return { nodes: [], previousTitle: null };

  const template = document.createElement('template');
  template.innerHTML = markup;
  const parsed = Array.from(template.content.childNodes).filter(
    (n) => n.nodeType === 1,
  );

  const nodes = [];
  let previousTitle = null;

  for (const declared of parsed) {
    if (declared.tagName === 'TITLE') {
      // Only one <title> wins; save the prior value so unmount can restore it.
      if (previousTitle === null) previousTitle = document.title;
      document.title = declared.textContent || '';
      continue;
    }

    const existing = _findEquivalentHeadElement(declared);
    if (existing) {
      existing.setAttribute(OWNER_ATTR, '');
      nodes.push(existing);
    } else {
      declared.setAttribute(OWNER_ATTR, '');
      document.head.appendChild(declared);
      nodes.push(declared);
    }
  }

  return { nodes, previousTitle };
}


export function Head({ children }) {
  // Server-side: register markup with the framework's head registry so
  // the template emits it into the initial HTML.
  if (typeof window === 'undefined') {
    if (typeof globalThis.__PYXLE_HEAD_REGISTRY__ !== 'undefined') {
      try {
        const headMarkup = renderToStaticMarkup(<>{children}</>);
        globalThis.__PYXLE_HEAD_REGISTRY__.register(headMarkup);
      } catch (error) {
        console.error('[Pyxle Head] SSR extraction failed:', error);
      }
    }
    return null;
  }

  // Client-side: render children to a stable string so we can use it as
  // the effect dependency (children itself changes identity every render).
  let markup = '';
  try {
    markup = renderToStaticMarkup(<>{children}</>);
  } catch (error) {
    console.error('[Pyxle Head] client render failed:', error);
  }

  useEffect(() => {
    const { nodes, previousTitle } = _applyHeadMarkup(markup);
    return () => {
      for (const node of nodes) {
        if (node.parentNode) node.parentNode.removeChild(node);
      }
      if (previousTitle !== null) {
        document.title = previousTitle;
      }
    };
  }, [markup]);

  return null;
}
