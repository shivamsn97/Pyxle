"""Utilities for writing client-side assets required by the dev server."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

from .settings import DevServerSettings

CLIENT_ENTRY_FILENAME = "client-entry.js"
CLIENT_HTML_FILENAME = "index.html"
VITE_CONFIG_FILENAME = "vite.config.js"
TSCONFIG_FILENAME = "tsconfig.json"


def _write_text_if_changed(path: Path, contents: str) -> None:
    if path.exists():
        current = path.read_text(encoding="utf-8")
        if current == contents:
            return
    path.write_text(contents, encoding="utf-8")


def write_client_bootstrap_files(settings: DevServerSettings) -> None:
    client_root = settings.client_build_dir
    client_root.mkdir(parents=True, exist_ok=True)

    files = {
        CLIENT_HTML_FILENAME: _render_client_index(),
        CLIENT_ENTRY_FILENAME: _render_client_entry(settings),
        VITE_CONFIG_FILENAME: _render_vite_config(settings),
        TSCONFIG_FILENAME: _render_tsconfig(),
        "pyxle/index.js": _render_client_runtime_index(),
        "pyxle/slot.jsx": _render_slot_runtime(),
        "pyxle/index.d.ts": _render_client_runtime_index_types(),
        "pyxle/link.d.ts": _render_client_runtime_link_types(),
        "pyxle/slot.d.ts": _render_slot_runtime_types(),
    }

    for relative_path, contents in files.items():
        target = client_root / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        _write_text_if_changed(target, contents)


def _render_client_index() -> str:
    return (
        dedent(
            """
            <!doctype html>
            <html lang="en">
              <head>
                <meta charset="utf-8" />
                <meta name="viewport" content="width=device-width, initial-scale=1" />
                <title>Pyxle App</title>
              </head>
              <body>
                <div id="root"></div>
                <script type="module" src="./client-entry.js"></script>
              </body>
            </html>
            """
        ).strip()
        + "\n"
    )


def _render_client_runtime_index() -> str:
    return (
        dedent(
            """
            import React from 'react';
            import {
              Slot,
              SlotProvider,
              useSlot,
              useSlots,
              mergeSlotLayers,
              normalizeSlots,
            } from './slot.jsx';

            const prefetchedHrefs = new Set();
            const viewportCallbacks = new Map();
            let viewportObserver = null;

            function getRouter() {
              if (typeof window === 'undefined') {
                return null;
              }
              return window.__PYXLE_ROUTER__ ?? null;
            }

            function getViewportObserver() {
              if (viewportObserver || typeof window === 'undefined' || !('IntersectionObserver' in window)) {
                return viewportObserver;
              }
              viewportObserver = new IntersectionObserver(
                (entries) => {
                  for (const entry of entries) {
                    if (!entry.isIntersecting) {
                      continue;
                    }
                    const callback = viewportCallbacks.get(entry.target);
                    if (callback) {
                      callback();
                    }
                  }
                },
                { rootMargin: '200px' },
              );
              return viewportObserver;
            }

            function unsubscribeFromViewport(node) {
              if (viewportCallbacks.has(node)) {
                viewportCallbacks.delete(node);
              }
              if (viewportObserver) {
                viewportObserver.unobserve(node);
              }
            }

            function triggerPrefetch(href) {
              if (!href || prefetchedHrefs.has(href)) {
                return;
              }
              prefetchedHrefs.add(href);
              const router = getRouter();
              router?.prefetch(href).catch(() => {});
            }

            function scheduleIdlePrefetch(href) {
              if (typeof window === 'undefined') {
                return;
              }
              if ('requestIdleCallback' in window) {
                window.requestIdleCallback(() => triggerPrefetch(href));
              } else {
                setTimeout(() => triggerPrefetch(href), 200);
              }
            }

            function shouldSkip(event) {
              if (event.metaKey || event.altKey || event.ctrlKey || event.shiftKey) {
                return true;
              }
              const target = event.currentTarget;
              if (!target) {
                return false;
              }
              const routerAttr = target.getAttribute('data-pyxle-router');
              return routerAttr && routerAttr.toLowerCase() === 'off';
            }

            function mergeRefs(ref, node) {
              if (typeof ref === 'function') {
                ref(node);
              } else if (ref && typeof ref === 'object') {
                ref.current = node;
              }
            }

            function normalizeHref(candidate) {
              if (candidate == null) {
                return null;
              }
              try {
                const url = new URL(candidate, window.location.origin);
                if (url.origin !== window.location.origin) {
                  return null;
                }
                return url;
              } catch (error) {
                return null;
              }
            }

            export const Link = React.forwardRef(function PyxleLink(props, forwardedRef) {
              const {
                href,
                prefetch = true,
                replace = false,
                scroll,
                shallow,
                passHref,
                onClick,
                onMouseEnter,
                children,
                ...rest
              } = props ?? {};

              const internalRef = React.useRef(null);

              React.useEffect(() => {
                const node = internalRef.current;
                if (!node || !prefetch) {
                  return () => {};
                }
                const url = normalizeHref(href);
                if (!url) {
                  return () => {};
                }
                const observer = getViewportObserver();
                if (!observer) {
                  scheduleIdlePrefetch(url.href);
                  return () => {};
                }
                const handler = () => triggerPrefetch(url.href);
                viewportCallbacks.set(node, handler);
                observer.observe(node);
                return () => {
                  unsubscribeFromViewport(node);
                };
              }, [href, prefetch]);

              const handleMouseEnter = React.useCallback(
                (event) => {
                  if (typeof onMouseEnter === 'function') {
                    onMouseEnter(event);
                  }
                  if (event.defaultPrevented || !prefetch) {
                    return;
                  }
                  const url = normalizeHref(href);
                  if (!url) {
                    return;
                  }
                  triggerPrefetch(url.href);
                },
                [href, onMouseEnter, prefetch],
              );

              const handleClick = React.useCallback(
                async (event) => {
                  if (typeof onClick === 'function') {
                    onClick(event);
                  }
                  if (event.defaultPrevented || shouldSkip(event)) {
                    return;
                  }
                  const url = normalizeHref(href);
                  if (!url) {
                    return;
                  }
                  event.preventDefault();
                  const router = getRouter();
                  if (!router) {
                    window.location.assign(url.href);
                    return;
                  }
                  const didNavigate = await router.navigate(url.href, {
                    replace,
                    scroll,
                    shallow,
                  });
                  if (!didNavigate) {
                    window.location.assign(url.href);
                  }
                },
                [href, onClick, replace, scroll, shallow],
              );

              const renderedHref = typeof href === 'string'
                ? href
                : (typeof href === 'object' && href !== null && 'toString' in href)
                  ? String(href)
                  : (rest.href ?? '#');

              const elementProps = {
                ...rest,
                href: renderedHref,
                onClick: handleClick,
                onMouseEnter: handleMouseEnter,
                ref: (node) => {
                  internalRef.current = node;
                  mergeRefs(forwardedRef, node);
                },
              };

              if (passHref && href) {
                elementProps.href = typeof href === 'string' ? href : String(href);
              }

              return React.createElement('a', elementProps, children);
            });

            export function navigate(href, options = {}) {
              const url = normalizeHref(href);
              if (!url) {
                window.location.assign(href);
                return Promise.resolve(false);
              }
              const router = getRouter();
              if (!router) {
                window.location.assign(url.href);
                return Promise.resolve(false);
              }
              return router.navigate(url.href, options);
            }

            export function prefetch(href) {
              const url = normalizeHref(href);
              if (!url) {
                return Promise.resolve(false);
              }
              const router = getRouter();
              if (!router) {
                return Promise.resolve(false);
              }
              return router.prefetch(url.href);
            }

            export { Slot, SlotProvider, useSlot, useSlots, mergeSlotLayers, normalizeSlots, getRouter };
            export default Link;
            """
        ).strip()
        + "\n"
    )


def _render_vite_config(settings: DevServerSettings) -> str:
    vite_host = settings.vite_host
    vite_port = settings.vite_port
    return (
        dedent(
            f"""
            import {{ defineConfig }} from 'vite';
            import react from '@vitejs/plugin-react';
            import path from 'node:path';

            const clientRoot = __dirname;
            const projectRoot = path.resolve(clientRoot, '..', '..');
            const pyxleClientDir = path.resolve(clientRoot, 'pyxle');
            const base = process.env.PYXLE_VITE_BASE ?? '/';

            export default defineConfig({{
              base,
              root: clientRoot,
              publicDir: path.resolve(projectRoot, 'public'),
              plugins: [react()],
              resolve: {{
                alias: [
                  {{ find: '/pages', replacement: path.resolve(clientRoot, 'pages') }},
                  {{ find: '/routes', replacement: path.resolve(clientRoot, 'routes') }},
                  {{ find: /^pyxle\\/client$/, replacement: path.resolve(pyxleClientDir, 'index.js') }},
                  {{ find: /^pyxle\\/client\\/(.+)$/, replacement: path.resolve(pyxleClientDir, '$1') }},
                ],
              }},
              server: {{
                host: '{vite_host}',
                port: Number(process.env.PYXLE_VITE_PORT ?? {vite_port}),
                strictPort: false,
                fs: {{
                  allow: [projectRoot],
                }},
              }},
            }});
            """
        ).strip()
        + "\n"
    )


def _render_slot_runtime() -> str:
    return (
        dedent(
            """
            import React, { createContext, useContext, useMemo } from 'react';

            const SlotContext = createContext(Object.freeze({}));

            export function normalizeSlots(candidate) {
              if (!candidate || typeof candidate !== 'object') {
                return {};
              }
              const normalized = {};
              for (const [name, factory] of Object.entries(candidate)) {
                if (typeof factory === 'function') {
                  normalized[name] = factory;
                }
              }
              return normalized;
            }

            function appendSlotFactory(registry, name, factory) {
              if (typeof factory !== 'function') {
                return;
              }
              if (!registry[name]) {
                registry[name] = [];
              }
              registry[name].push(factory);
            }

            export function mergeSlotLayers(layers, pageSlots = {}) {
              const registry = {};
              const list = Array.isArray(layers) ? layers : [];
              for (const layer of list) {
                if (!layer || !layer.slots) {
                  continue;
                }
                const slots = normalizeSlots(layer.slots);
                for (const [name, factory] of Object.entries(slots)) {
                  appendSlotFactory(registry, name, factory);
                }
              }
              const normalizedPageSlots = normalizeSlots(pageSlots);
              for (const [name, factory] of Object.entries(normalizedPageSlots)) {
                appendSlotFactory(registry, name, factory);
              }
              return registry;
            }

            export function SlotProvider({ slots, children }) {
              const value = useMemo(
                () => (slots && typeof slots === 'object' ? slots : {}),
                [slots],
              );
              return React.createElement(SlotContext.Provider, { value }, children);
            }

            export function useSlots() {
              return useContext(SlotContext);
            }

            export function useSlot(name) {
              const slots = useSlots();
              const entry = slots?.[name];
              if (!entry) {
                return null;
              }
              if (Array.isArray(entry)) {
                return entry.length ? entry : null;
              }
              if (typeof entry === 'function') {
                return [entry];
              }
              return null;
            }

            export function Slot({ name, props = {}, fallback = null }) {
              const slotFactories = useSlot(name);
              if (slotFactories && slotFactories.length) {
                return slotFactories.map((factory, index) => {
                  const rendered = factory(props);
                  if (rendered == null) {
                    return rendered;
                  }
                  return React.createElement(
                    React.Fragment,
                    { key: `slot-${name}-${index}` },
                    rendered,
                  );
                });
              }
              if (typeof fallback === 'function') {
                return fallback(props);
              }
              return fallback ?? null;
            }
            """
        ).strip()
        + "\n"
    )


def _render_client_runtime_index_types() -> str:
    return (
        dedent(
            """
            import type { LinkProps } from './link';
            import type { SlotDictionary } from './slot';

            export type NavigationTarget = string | URL | Location;

            export interface NavigationOptions {
              replace?: boolean;
              scroll?: boolean | 'preserve';
              shallow?: boolean;
              updateHistory?: boolean;
            }

            export interface PyxleRouter {
              navigate(href: NavigationTarget, options?: NavigationOptions): Promise<boolean>;
              prefetch(href: NavigationTarget): Promise<boolean>;
            }

            export declare function navigate(href: NavigationTarget, options?: NavigationOptions): Promise<boolean>;
            export declare function prefetch(href: NavigationTarget): Promise<boolean>;
            export declare function getRouter(): PyxleRouter | null;

            export { Link, type LinkProps } from './link';
            export { Slot, SlotProvider, useSlot, useSlots, type SlotDictionary } from './slot';

            export default Link;
            """
        ).strip()
        + "\n"
    )


def _render_client_runtime_link_types() -> str:
    return (
        dedent(
            """
            import type React from 'react';

            export interface LinkProps extends React.AnchorHTMLAttributes<HTMLAnchorElement> {
              href: string;
              prefetch?: boolean;
              replace?: boolean;
              scroll?: boolean | 'preserve';
              shallow?: boolean;
              passHref?: boolean;
            }

            export declare const Link: React.ForwardRefExoticComponent<LinkProps & React.RefAttributes<HTMLAnchorElement>>;
            export default Link;
            """
        ).strip()
        + "\n"
    )


def _render_slot_runtime_types() -> str:
    return (
        dedent(
            """
            import type React from 'react';

            export type SlotFactory<TProps = any> = (props: TProps) => React.ReactNode;
            export type SlotDictionary = Record<string, SlotFactory<any>>;
            export type SlotRegistry = Record<string, SlotFactory<any>[]>;

            export interface SlotLayer {
              kind?: string;
              reset?: boolean;
              slots?: SlotDictionary | null | undefined;
            }

            export interface SlotProviderProps {
              slots?: SlotRegistry | null | undefined;
              children?: React.ReactNode;
            }

            export interface SlotProps<TProps = any> {
              name: string;
              props?: TProps;
              fallback?: React.ReactNode | SlotFactory<TProps> | null;
            }

            export declare function normalizeSlots(candidate: unknown): SlotDictionary;
            export declare function mergeSlotLayers(layers: SlotLayer[], pageSlots?: SlotDictionary): SlotRegistry;
            export declare function SlotProvider(props: SlotProviderProps): React.ReactElement;
            export declare function useSlots(): SlotRegistry;
            export declare function useSlot<TProps = any>(name: string): SlotFactory<TProps>[] | null;
            export declare function Slot<TProps = any>(props: SlotProps<TProps>): React.ReactElement | React.ReactElement[] | null;
            """
        ).strip()
        + "\n"
    )


def _render_client_entry(settings: DevServerSettings) -> str:
    content = (
      dedent(
        """
        __PYXLE_GLOBAL_SCRIPT_IMPORTS__
        import React from 'react';
        import ReactDOM from 'react-dom/client';
        __PYXLE_GLOBAL_STYLE_IMPORTS__

        const componentModules = {
              ...import.meta.glob('/pages/**/*.jsx'),
              ...import.meta.glob('/routes/**/*.jsx'),
            };
            __PYXLE_OVERLAY_BLOCK__
            const NAVIGATION_HEADER = 'x-pyxle-navigation';
            const HEAD_START_SELECTOR = 'meta[data-pyxle-head-start]';
            const HEAD_END_SELECTOR = 'meta[data-pyxle-head-end]';
            const PREFETCH_TRIGGER = 'hover';
            const STALE_STYLE_ATTR = 'data-pyxle-stale-style';
            const NEW_STYLE_ATTR = 'data-pyxle-new-style';
            const STYLESHEET_LOAD_TIMEOUT = 3000;

            let reactRoot = null;
            let currentPagePath = window.__PYXLE_PAGE_PATH__ || '';
            let navigationController = null;

            const navigationCache = new Map();
            const navigationPromises = new Map();
            const moduleCache = new Map();

            const router = {
              navigate: (href, options = {}) => navigateTo(href, options),
              prefetch: (href) => prefetchNavigation(href),
            };

            window.__PYXLE_ROUTER__ = router;

            const availableModules = Object.keys(componentModules);
            if (!currentPagePath && availableModules.length > 0) {
              currentPagePath = availableModules[0];
            }

            function parseInitialProps() {
              try {
                const propsTag = document.getElementById('__PYXLE_PROPS__');
                const rawProps = propsTag?.textContent ?? '{}';
                return rawProps ? JSON.parse(rawProps) : {};
              } catch (error) {
                console.error('[Pyxle] Failed to parse initial props', error);
                return {};
              }
            }

            function serializeProps(props) {
              try {
                return JSON.stringify(props).replace(/</g, '\\u003C');
              } catch (error) {
                console.warn('[Pyxle] Failed to serialize props payload', error);
                return '{}';
              }
            }

            function updatePropsTag(props) {
              const propsTag = document.getElementById('__PYXLE_PROPS__');
              if (!propsTag) {
                return;
              }
              propsTag.textContent = serializeProps(props);
            }

            function updateHead(markup) {
              const head = document.head;
              if (!head) {
                return;
              }
              const start = head.querySelector(HEAD_START_SELECTOR);
              const end = head.querySelector(HEAD_END_SELECTOR);
              if (!start || !end) {
                return;
              }
              const fragmentHtml = (markup ?? '').trim();
              const existingNodes = [];
              const staleStylesheets = [];
              const newStylesheets = [];
              let node = start.nextSibling;
              while (node && node !== end) {
                existingNodes.push(node);
                node = node.nextSibling;
              }
              const processed = new Set();
              const signatureMap = new Map();
              for (const existing of existingNodes) {
                const signature = getNodeSignature(existing);
                if (!signatureMap.has(signature)) {
                  signatureMap.set(signature, []);
                }
                signatureMap.get(signature).push(existing);
              }

              const template = document.createElement('template');
              template.innerHTML = fragmentHtml;
              const nextNodes = Array.from(template.content.childNodes);
              for (const nextNode of nextNodes) {
                const signature = getNodeSignature(nextNode);
                const pool = signatureMap.get(signature);
                const candidate = pool?.shift?.();
                if (candidate) {
                  processed.add(candidate);
                  candidate.removeAttribute?.(STALE_STYLE_ATTR);
                  syncNodeContent(candidate, nextNode);
                  continue;
                }
                const nodeToInsert = nextNode;
                head.insertBefore(nodeToInsert, end);
                if (isStylesheetNode(nodeToInsert)) {
                  nodeToInsert.setAttribute(NEW_STYLE_ATTR, '1');
                  newStylesheets.push(nodeToInsert);
                }
              }

              for (const existing of existingNodes) {
                if (!processed.has(existing) && existing.parentNode === head) {
                  if (isStylesheetNode(existing)) {
                    existing.setAttribute(STALE_STYLE_ATTR, '1');
                    staleStylesheets.push(existing);
                  } else {
                    head.removeChild(existing);
                  }
                }
              }

              if (staleStylesheets.length) {
                const finalize = () => cleanupStaleStylesheets(staleStylesheets);
                if (newStylesheets.length) {
                  waitForStylesheets(newStylesheets).then(finalize);
                } else {
                  setTimeout(finalize, 0);
                }
              }
            }

            function getNodeSignature(node) {
              if (!node) {
                return '';
              }
              if (node.nodeType !== Node.ELEMENT_NODE) {
                return `text:${node.textContent ?? ''}`;
              }
              const element = node;
              const key = element.getAttribute?.('data-pyxle-head-key');
              if (key) {
                return `key:${key}`;
              }
              const tag = element.tagName?.toLowerCase?.() ?? '';
              if (tag === 'meta') {
                const name = element.getAttribute('name');
                const property = element.getAttribute('property');
                const content = element.getAttribute('content');
                return `meta:${name ?? property ?? ''}:${content ?? ''}`;
              }
              if (tag === 'link') {
                return `link:${element.getAttribute('rel') ?? ''}:${element.getAttribute('href') ?? ''}`;
              }
              if (tag === 'script') {
                return `script:${element.getAttribute('src') ?? ''}:${element.textContent ?? ''}`;
              }
              return element.outerHTML ?? '';
            }

            function syncNodeContent(target, source) {
              if (!target || !source) {
                return;
              }
              if (target.nodeType !== source.nodeType) {
                target.replaceWith(source);
                return;
              }
              if (target.nodeType === Node.TEXT_NODE) {
                if (target.textContent !== source.textContent) {
                  target.textContent = source.textContent;
                }
                return;
              }
              if (target.tagName?.toLowerCase?.() === 'title') {
                if (target.textContent !== source.textContent) {
                  target.textContent = source.textContent ?? '';
                }
                return;
              }
              const isMeta = target.tagName?.toLowerCase?.() === 'meta';
              const isLink = target.tagName?.toLowerCase?.() === 'link';
              if (isMeta || isLink) {
                const sourceAttrs = Array.from(source.attributes ?? []);
                const targetAttrs = new Set(Array.from(target.attributes ?? []).map((attr) => attr.name));
                for (const attr of sourceAttrs) {
                  target.setAttribute(attr.name, attr.value);
                  targetAttrs.delete(attr.name);
                }
                for (const attrName of targetAttrs) {
                  target.removeAttribute(attrName);
                }
                return;
              }
              target.replaceWith(source);
            }

            function isStylesheetNode(node) {
              if (!node || node.nodeType !== Node.ELEMENT_NODE) {
                return false;
              }
              if (node.tagName?.toLowerCase?.() !== 'link') {
                return false;
              }
              const rel = node.getAttribute('rel') ?? '';
              return rel.toLowerCase().includes('stylesheet');
            }

            function cleanupStaleStylesheets(nodes) {
              for (const node of nodes) {
                if (!node) {
                  continue;
                }
                node.removeAttribute(STALE_STYLE_ATTR);
                if (node.parentNode === document.head) {
                  document.head.removeChild(node);
                }
              }
            }

            function waitForStylesheets(nodes) {
              return Promise.all(
                nodes.map((node) => {
                  return new Promise((resolve) => {
                    if (!node) {
                      resolve();
                      return;
                    }
                    const cleanup = () => {
                      node.removeAttribute(NEW_STYLE_ATTR);
                      resolve();
                    };
                    let settled = false;
                    const onComplete = () => {
                      if (settled) {
                        return;
                      }
                      settled = true;
                      clearTimeout(timer);
                      cleanup();
                    };
                    const timer = setTimeout(onComplete, STYLESHEET_LOAD_TIMEOUT);
                    node.addEventListener('load', onComplete, { once: true });
                    node.addEventListener('error', onComplete, { once: true });
                    try {
                      if (node.sheet && node.sheet.cssRules !== null) {
                        onComplete();
                      }
                    } catch (error) {
                      if (String(error?.name).toLowerCase() === 'securityerror') {
                        // Ignore cross-origin access errors; rely on load/error events.
                      }
                    }
                  });
                }),
              );
            }

            async function loadPageModule(pagePath) {
              if (moduleCache.has(pagePath)) {
                return moduleCache.get(pagePath);
              }
              const loader = componentModules[pagePath];
              if (!loader) {
                throw new Error(`[Pyxle] No module found for ${pagePath}`);
              }
              const promise = loader()
                .then((mod) => {
                  moduleCache.set(pagePath, Promise.resolve(mod));
                  return mod;
                })
                .catch((error) => {
                  moduleCache.delete(pagePath);
                  throw error;
                });
              moduleCache.set(pagePath, promise);
              return promise;
            }

            async function renderPage(pagePath, props) {
              const module = await loadPageModule(pagePath);
              const Page = module.default;
              if (!Page) {
                throw new Error(`[Pyxle] Page module ${pagePath} is missing a default export.`);
              }
              const container = document.getElementById('root');
              if (!container) {
                throw new Error("[Pyxle] Hydration container '#root' not found");
              }

              const element = React.createElement(Page, props);
              if (!reactRoot) {
                const placeholder = container.firstElementChild;
                const shouldClientRender = placeholder?.hasAttribute('data-pyxle-component');
                if (shouldClientRender) {
                  container.innerHTML = '';
                  reactRoot = ReactDOM.createRoot(container);
                  reactRoot.render(element);
                } else {
                  reactRoot = ReactDOM.hydrateRoot(container, element);
                }
              } else {
                reactRoot.render(element);
              }

              currentPagePath = pagePath;
              window.__PYXLE_PAGE_PATH__ = pagePath;
              updatePropsTag(props);
            }

            function normalizeUrl(target) {
              if (target instanceof URL) {
                return target;
              }
              if (typeof target === 'string') {
                try {
                  return new URL(target, window.location.href);
                } catch (error) {
                  return null;
                }
              }
              if (target && typeof target.href === 'string') {
                try {
                  return new URL(target.href, window.location.href);
                } catch (error) {
                  return null;
                }
              }
              return null;
            }

            function getCacheKey(url) {
              return `${url.pathname}${url.search}`;
            }

            function shouldHandleClick(event) {
              if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.altKey || event.ctrlKey || event.shiftKey) {
                return null;
              }
              const anchor = event.target?.closest?.('a[href]');
              if (!anchor) {
                return null;
              }
              if (anchor.dataset.pyxleRouter === 'off' || anchor.hasAttribute('download')) {
                return null;
              }
              const rel = anchor.getAttribute('rel');
              if (rel && rel.toLowerCase().includes('external')) {
                return null;
              }
              const targetAttr = anchor.getAttribute('target');
              if (targetAttr && targetAttr.toLowerCase() !== '_self') {
                return null;
              }
              const url = normalizeUrl(anchor.href);
              if (!url || url.origin !== window.location.origin) {
                return null;
              }
              const href = anchor.getAttribute('href') || '';
              if (href.startsWith('#')) {
                return null;
              }
              if (url.pathname === window.location.pathname && url.search === window.location.search && url.hash && url.hash !== window.location.hash) {
                return null;
              }
              return { anchor, url };
            }

            function handleLinkClick(event) {
              const result = shouldHandleClick(event);
              if (!result) {
                return;
              }
              event.preventDefault();
              navigateTo(result.url).catch(() => {});
            }

            function handlePopState(event) {
              if (!event.state || !event.state.pyxle) {
                window.location.reload();
                return;
              }
              navigateTo(new URL(window.location.href), {
                updateHistory: false,
                scroll: 'preserve',
              }).catch(() => {});
            }

            function markNavigating(active) {
              const root = document.documentElement;
              if (!root) {
                return;
              }
              if (active) {
                root.setAttribute('data-pyxle-navigation', '1');
              } else {
                root.removeAttribute('data-pyxle-navigation');
              }
            }

            async function requestNavigationPayload(url, { useController = true } = {}) {
              const cacheKey = getCacheKey(url);
              if (navigationCache.has(cacheKey)) {
                return navigationCache.get(cacheKey);
              }
              const controller = new AbortController();
              if (useController) {
                if (navigationController) {
                  navigationController.abort();
                }
                navigationController = controller;
              }
              try {
                const response = await fetch(`${url.pathname}${url.search}`, {
                  method: 'GET',
                  credentials: 'same-origin',
                  headers: {
                    [NAVIGATION_HEADER]: '1',
                    'x-requested-with': 'pyxle',
                    accept: 'application/json',
                  },
                  signal: controller.signal,
                  cache: 'no-store',
                });
                const contentType = response.headers.get('content-type') || '';
                if (!contentType.includes('application/json')) {
                  return null;
                }
                const payload = await response.json().catch(() => null);
                if (!payload || payload.ok !== true) {
                  return null;
                }
                navigationCache.set(cacheKey, payload);
                return payload;
              } catch (error) {
                if (!(error instanceof DOMException && error.name === 'AbortError')) {
                  console.error('[Pyxle] Failed to fetch navigation payload', error);
                }
                throw error;
              } finally {
                if (useController && navigationController === controller) {
                  navigationController = null;
                }
              }
            }

            function prefetchNavigation(target) {
              const url = normalizeUrl(target);
              if (!url || url.origin !== window.location.origin) {
                return Promise.resolve(false);
              }
              const cacheKey = getCacheKey(url);
              if (navigationCache.has(cacheKey)) {
                return Promise.resolve(true);
              }
              if (navigationPromises.has(cacheKey)) {
                return navigationPromises.get(cacheKey);
              }
              const promise = requestNavigationPayload(url, { useController: false })
                .then(async (payload) => {
                  if (!payload) {
                    navigationCache.delete(cacheKey);
                    return false;
                  }
                  const pagePath = payload.page?.clientAssetPath;
                  if (pagePath) {
                    await prefetchModule(pagePath);
                  }
                  return true;
                })
                .catch(() => false)
                .finally(() => {
                  navigationPromises.delete(cacheKey);
                });
              navigationPromises.set(cacheKey, promise);
              return promise;
            }

            async function prefetchModule(pagePath) {
              if (!pagePath || moduleCache.has(pagePath)) {
                return true;
              }
              try {
                await loadPageModule(pagePath);
                return true;
              } catch (error) {
                return false;
              }
            }

            async function navigateTo(target, options = {}) {
              const url = normalizeUrl(target);
              if (!url) {
                return false;
              }
              if (url.origin !== window.location.origin) {
                window.location.assign(url.href);
                return false;
              }

              markNavigating(true);
              try {
                const cacheKey = getCacheKey(url);
                let payload = navigationCache.get(cacheKey);
                if (!payload) {
                  payload = await requestNavigationPayload(url, { useController: true });
                }
                if (!payload) {
                  window.location.assign(url.href);
                  return false;
                }

                const nextPagePath = payload.page?.clientAssetPath ?? currentPagePath;
                const nextProps = payload.props ?? {};
                await prefetchModule(nextPagePath);
                await renderPage(nextPagePath, nextProps);
                updateHead(payload.headMarkup ?? '');

                if (options.updateHistory === false) {
                  window.history.replaceState({ pyxle: true, pagePath: nextPagePath }, '', `${url.pathname}${url.search}${url.hash}`);
                } else {
                  const method = options.replace ? 'replaceState' : 'pushState';
                  window.history[method]({ pyxle: true, pagePath: nextPagePath }, '', `${url.pathname}${url.search}${url.hash}`);
                }

                if (options.scroll !== 'preserve') {
                  window.scrollTo(0, 0);
                }

                return true;
              } catch (error) {
                if (!(error instanceof DOMException && error.name === 'AbortError')) {
                  console.error('[Pyxle] Client navigation failed; falling back to full reload', error);
                  window.location.assign(url.href);
                }
                return false;
              } finally {
                markNavigating(false);
              }
            }

            function handleLinkHover(event) {
              if (PREFETCH_TRIGGER !== 'hover') {
                return;
              }
              const anchor = event.target?.closest?.('a[href]');
              if (!anchor || anchor.dataset.pyxleRouter === 'off' || anchor.dataset.pyxlePrefetch === 'off') {
                return;
              }
              const href = anchor.getAttribute('href');
              if (!href || href.startsWith('#')) {
                return;
              }
              const url = normalizeUrl(href);
              if (!url || url.origin !== window.location.origin) {
                return;
              }
              prefetchNavigation(url).catch(() => {});
            }

            async function bootstrap() {
              const initialProps = parseInitialProps();
              await renderPage(currentPagePath, initialProps);
              if (!window.history.state || !window.history.state.pyxle) {
                window.history.replaceState({ pyxle: true, pagePath: currentPagePath }, '', window.location.href);
              }
            }

            bootstrap().catch(() => {});

            __PYXLE_OVERLAY_BOOTSTRAP__
            document.addEventListener('click', handleLinkClick);
            document.addEventListener('mouseenter', handleLinkHover, { capture: true });
            window.addEventListener('popstate', handlePopState);
            """
        ).strip()
        + "\n"
    )


    overlay_block = dedent(
        """
        const OVERLAY_CONTAINER_ID = '__PYXLE_ERROR_OVERLAY__';
        const OVERLAY_RECONNECT_DELAY = 1000;

        function ensureOverlayRoot() {
          let container = document.getElementById(OVERLAY_CONTAINER_ID);
          if (!container) {
            container = document.createElement('div');
            container.id = OVERLAY_CONTAINER_ID;
            document.body.appendChild(container);
          }
          if (!container.__pyxle_overlay_root) {
            container.__pyxle_overlay_root = ReactDOM.createRoot(container);
          }
          return container.__pyxle_overlay_root;
        }

        function OverlayDocument({ event, stackLines, breadcrumbs }) {
          return React.createElement(
            'div',
            {
              style: {
                position: 'fixed',
                inset: 0,
                backgroundColor: 'rgba(15, 23, 42, 0.92)',
                color: '#f8fafc',
                fontFamily: 'system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
                padding: '2rem',
                overflowY: 'auto',
                zIndex: 2147483647,
              },
            },
            [
              React.createElement(
                'div',
                { key: 'header', style: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' } },
                [
                  React.createElement(
                    'div',
                    { key: 'title', style: { fontSize: '1.5rem', fontWeight: 700 } },
                    `⚠️ Loader/render error in ${event.routePath}`,
                  ),
                  React.createElement(
                    'div',
                    { key: 'actions', style: { display: 'flex', gap: '0.5rem' } },
                    [
                      React.createElement(
                        'button',
                        {
                          key: 'retry',
                          style: {
                            backgroundColor: '#22c55e',
                            color: '#0f172a',
                            padding: '0.5rem 0.9rem',
                            borderRadius: '0.5rem',
                            fontWeight: 600,
                            border: 'none',
                            cursor: 'pointer',
                          },
                          onClick: () => window.location.reload(),
                        },
                        'Retry',
                      ),
                      React.createElement(
                        'button',
                        {
                          key: 'dismiss',
                          style: {
                            backgroundColor: 'transparent',
                            color: '#f8fafc',
                            padding: '0.5rem 0.9rem',
                            borderRadius: '0.5rem',
                            fontWeight: 600,
                            border: '1px solid rgba(148, 163, 184, 0.6)',
                            cursor: 'pointer',
                          },
                          onClick: clearOverlay,
                        },
                        'Dismiss',
                      ),
                    ],
                  ),
                ],
              ),
              React.createElement(
                'div',
                { key: 'message', style: { marginBottom: '1rem', fontSize: '1.1rem' } },
                event.message,
              ),
              breadcrumbs.length
                ? React.createElement(
                    'div',
                    {
                      key: 'breadcrumbs',
                      style: {
                        display: 'flex',
                        flexDirection: 'column',
                        gap: '0.75rem',
                        marginBottom: '1rem',
                      },
                    },
                    breadcrumbs.map((crumb, index) =>
                      React.createElement(
                        'div',
                        {
                          key: `crumb-${index}`,
                          style: {
                            padding: '0.9rem 1rem',
                            borderRadius: '0.75rem',
                            backgroundColor: 'rgba(148, 163, 184, 0.08)',
                            border: '1px solid rgba(148, 163, 184, 0.2)',
                            display: 'flex',
                            flexDirection: 'column',
                            gap: '0.35rem',
                          },
                        },
                        [
                          React.createElement(
                            'div',
                            {
                              key: 'crumb-header',
                              style: {
                                display: 'flex',
                                justifyContent: 'space-between',
                                alignItems: 'center',
                                fontWeight: 600,
                              },
                            },
                            [
                              React.createElement('span', { key: 'label' }, crumb.label ?? `Stage ${index + 1}`),
                              React.createElement(
                                'span',
                                {
                                  key: 'status',
                                  style: {
                                    textTransform: 'uppercase',
                                    fontSize: '0.75rem',
                                    letterSpacing: '0.08em',
                                    padding: '0.1rem 0.5rem',
                                    borderRadius: '999px',
                                    border: '1px solid rgba(148, 163, 184, 0.6)',
                                  },
                                },
                                String(crumb.status ?? 'unknown').toUpperCase(),
                              ),
                            ],
                          ),
                          crumb.detail
                            ? React.createElement(
                                'p',
                                {
                                  key: 'detail',
                                  style: {
                                    margin: 0,
                                    color: 'rgba(226, 232, 240, 0.85)',
                                    fontSize: '0.9rem',
                                  },
                                },
                                crumb.detail,
                              )
                            : null,
                        ],
                      ),
                    ),
                  )
                : null,
              stackLines.length
                ? React.createElement(
                    'pre',
                    {
                      key: 'stack',
                      style: {
                        backgroundColor: 'rgba(15, 23, 42, 0.6)',
                        borderRadius: '0.75rem',
                        padding: '1rem',
                        fontSize: '0.85rem',
                        lineHeight: 1.5,
                        whiteSpace: 'pre-wrap',
                      },
                    },
                    stackLines.join('\\n'),
                  )
                : null,
            ],
          );
        }

        function renderOverlay(event) {
          const root = ensureOverlayRoot();
          const stackLines = (event.stack ?? '').split('\\n').filter(Boolean);
          const breadcrumbs = Array.isArray(event.breadcrumbs) ? event.breadcrumbs : [];
          root.render(
            React.createElement(OverlayDocument, { event, stackLines, breadcrumbs }),
          );
        }

        function clearOverlay() {
          const container = document.getElementById(OVERLAY_CONTAINER_ID);
          if (!container || !container.__pyxle_overlay_root) {
            return;
          }
          container.__pyxle_overlay_root.render(null);
        }

        function connectOverlayChannel() {
          const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
          const url = `${protocol}//${window.location.host}/__pyxle__/overlay`;
          const socket = new WebSocket(url);

          socket.onmessage = (event) => {
            try {
              const payload = JSON.parse(event.data);
              if (payload.type === 'error') {
                renderOverlay(payload.payload ?? {});
              } else if (payload.type === 'clear') {
                clearOverlay();
              } else if (payload.type === 'reload') {
                const changed = Array.isArray(payload.payload?.changedPaths)
                  ? payload.payload.changedPaths
                  : [];
                const reason = changed.length ? changed.join(', ') : 'server changes';
                console.info(`[Pyxle] Reloading due to ${reason}`);
                window.location.reload();
              }
            } catch (error) {
              console.error('[Pyxle] Failed to parse overlay message', error);
            }
          };

          socket.onclose = () => {
            setTimeout(connectOverlayChannel, OVERLAY_RECONNECT_DELAY);
          };

          socket.onerror = () => {
            socket.close();
          };
        }
        """
    ).strip()
    overlay_bootstrap_call = "connectOverlayChannel();\n"

    if settings.debug:
        overlay_injection = overlay_block + "\n\n" if overlay_block else ""
        content = content.replace("__PYXLE_OVERLAY_BLOCK__", overlay_injection, 1)
        content = content.replace("__PYXLE_OVERLAY_BOOTSTRAP__", overlay_bootstrap_call, 1)
    else:
        content = content.replace("__PYXLE_OVERLAY_BLOCK__", "", 1)
        content = content.replace("__PYXLE_OVERLAY_BOOTSTRAP__", "", 1)

    script_block = ""
    if settings.global_scripts:
      script_lines = [f"import '{script.import_specifier}';" for script in settings.global_scripts]
      script_block = "\n".join(script_lines) + "\n"
    content = content.replace("__PYXLE_GLOBAL_SCRIPT_IMPORTS__\n", script_block, 1)

    style_block = ""
    if settings.global_stylesheets:
      style_lines = [f"import '{sheet.import_specifier}';" for sheet in settings.global_stylesheets]
      style_block = "\n".join(style_lines) + "\n"
    content = content.replace("__PYXLE_GLOBAL_STYLE_IMPORTS__\n", style_block, 1)
    return content


def _render_tsconfig() -> str:
    return (
        dedent(
            """
            {
              "compilerOptions": {
                "target": "ESNext",
                "useDefineForClassFields": true,
                "module": "ESNext",
                "moduleResolution": "Node",
                "strict": true,
                "jsx": "react-jsx",
                "esModuleInterop": true,
                "allowJs": true,
                "allowSyntheticDefaultImports": true,
                "resolveJsonModule": true,
                "isolatedModules": true,
                "skipLibCheck": true,
                "baseUrl": ".",
                "paths": {
                  "/pages/*": ["pages/*"],
                  "/routes/*": ["routes/*"],
                  "pyxle/client": ["pyxle/index"],
                  "pyxle/client/*": ["pyxle/*"]
                },
                "types": ["vite/client"]
              },
              "include": [
                "./client-entry.js",
                "./pages/**/*.jsx",
                "./pyxle/**/*"
              ]
            }
            """
        ).strip()
        + "\n"
    )


__all__ = [
    "CLIENT_ENTRY_FILENAME",
    "CLIENT_HTML_FILENAME",
    "VITE_CONFIG_FILENAME",
    "TSCONFIG_FILENAME",
    "write_client_bootstrap_files",
    "_render_client_entry",
  "_render_client_runtime_index",
    "_render_client_runtime_index_types",
    "_render_client_runtime_link_types",
    "_render_client_index",
    "_render_slot_runtime",
    "_render_slot_runtime_types",
    "_render_tsconfig",
    "_render_vite_config",
]
