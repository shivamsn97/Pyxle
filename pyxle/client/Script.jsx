/**
 * <Script> — declarative, strategy-based script loader.
 *
 * Strategies
 * ----------
 *   beforeInteractive  Script must be in the initial HTML and block hydration.
 *                      Only works for <Script> tags that are statically
 *                      present in a .pyxl file at build time — the compiler
 *                      extracts them and the SSR template injects the tag
 *                      directly into <head>.  A dynamically-rendered
 *                      <Script strategy="beforeInteractive"> cannot honour
 *                      the contract (the page is already interactive by the
 *                      time it mounts); we degrade to `afterInteractive`
 *                      and warn in the console.
 *
 *   afterInteractive   Load on mount after React hydration (default).
 *                      Use for non-critical third-party libs.
 *
 *   lazyOnload         Load when the browser goes idle
 *                      (via requestIdleCallback, or setTimeout as fallback).
 *                      Use for analytics, telemetry — anything you want to
 *                      avoid competing with hydration or user interaction.
 *
 * Props
 * -----
 *   src       URL of the external script.  If omitted, `children` is used
 *             as inline script content (only recommended for short setup
 *             snippets — everything else belongs in a real module).
 *   async, defer, module, noModule
 *             Mirror the respective <script> attributes.
 *   onLoad    Called after the script finishes loading.  Fires immediately
 *             if the same src was already loaded via another <Script>.
 *   onError   Called with an Error if the load fails.
 *
 * Dedup
 * -----
 * Loads are de-duplicated per src across all <Script> instances and across
 * the framework's bootstrap loader (which also consumes
 * window.__PYXLE_SCRIPTS__).  Multiple <Script src="x" /> usages result in
 * exactly one network request.
 */

import { useEffect } from 'react';

const LOADED_ATTR = 'data-pyxle-script-loaded';
const FAILED_ATTR = 'data-pyxle-script-failed';

// Module-level cache: src -> Promise<void> that resolves on load / rejects on error.
const _scriptPromises = new Map();


function _ensureScriptLoaded(src, options) {
  const cached = _scriptPromises.get(src);
  if (cached) return cached;

  const existing = document.querySelector(`script[src="${CSS.escape(src)}"]`);
  if (existing) {
    const promise = new Promise((resolve, reject) => {
      if (existing.getAttribute(LOADED_ATTR) === 'true') {
        resolve();
      } else if (existing.getAttribute(FAILED_ATTR) === 'true') {
        reject(new Error(`Script previously failed to load: ${src}`));
      } else {
        existing.addEventListener('load', () => resolve(), { once: true });
        existing.addEventListener(
          'error',
          () => reject(new Error(`Failed to load script: ${src}`)),
          { once: true },
        );
      }
    });
    _scriptPromises.set(src, promise);
    return promise;
  }

  const script = document.createElement('script');
  script.src = src;
  if (options.async) script.async = true;
  if (options.defer) script.defer = true;
  if (options.module) script.type = 'module';
  if (options.noModule) script.setAttribute('nomodule', '');
  if (options.crossOrigin) script.crossOrigin = options.crossOrigin;
  if (options.integrity) script.integrity = options.integrity;
  if (options.referrerPolicy) script.referrerPolicy = options.referrerPolicy;

  const promise = new Promise((resolve, reject) => {
    script.addEventListener(
      'load',
      () => {
        script.setAttribute(LOADED_ATTR, 'true');
        resolve();
      },
      { once: true },
    );
    script.addEventListener(
      'error',
      () => {
        script.setAttribute(FAILED_ATTR, 'true');
        reject(new Error(`Failed to load script: ${src}`));
      },
      { once: true },
    );
  });

  document.head.appendChild(script);
  _scriptPromises.set(src, promise);
  return promise;
}


export function Script({
  src,
  strategy = 'afterInteractive',
  async: asyncProp,
  defer,
  module,
  noModule,
  onLoad,
  onError,
  children,
  ...attrs
}) {
  // SSR: the compiler extracts <Script> usage into metadata; the template
  // emits beforeInteractive scripts inline and lists others in
  // window.__PYXLE_SCRIPTS__.  Nothing to render here.
  if (typeof window === 'undefined') {
    return null;
  }

  useEffect(() => {
    // Inline snippet — run the source exactly once per instance.
    if (!src) {
      if (typeof children !== 'string' || children.length === 0) return undefined;
      const script = document.createElement('script');
      script.textContent = children;
      if (module) script.type = 'module';
      document.head.appendChild(script);
      if (onLoad) onLoad();
      return () => {
        if (script.parentNode) script.parentNode.removeChild(script);
      };
    }

    // Honor strategy.  beforeInteractive can only be satisfied at build time;
    // if a component winds up rendering with that strategy we degrade.
    let effectiveStrategy = strategy;
    if (effectiveStrategy === 'beforeInteractive') {
      console.warn(
        `[Pyxle Script] strategy="beforeInteractive" requires the <Script> ` +
        `to be statically present in a .pyxl file at build time. ` +
        `Falling back to "afterInteractive" for dynamically rendered src: ${src}`,
      );
      effectiveStrategy = 'afterInteractive';
    }

    const load = () => {
      _ensureScriptLoaded(src, {
        async: asyncProp,
        defer,
        module,
        noModule,
        crossOrigin: attrs.crossOrigin,
        integrity: attrs.integrity,
        referrerPolicy: attrs.referrerPolicy,
      }).then(
        () => { if (onLoad) onLoad(); },
        (err) => { if (onError) onError(err); },
      );
    };

    if (effectiveStrategy === 'lazyOnload') {
      if (typeof requestIdleCallback === 'function') {
        const handle = requestIdleCallback(load);
        return () => {
          if (typeof cancelIdleCallback === 'function') cancelIdleCallback(handle);
        };
      }
      const handle = setTimeout(load, 200);
      return () => clearTimeout(handle);
    }

    // afterInteractive (and beforeInteractive fallback)
    load();
    return undefined;
  // Callbacks intentionally omitted from deps — they should not re-trigger loads.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [src, strategy, module, noModule]);

  return null;
}
