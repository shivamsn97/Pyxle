/**
 * useAction — call a Pyxle @action server function from a React component.
 *
 * Usage:
 *   const updateName = useAction('update_name');
 *   await updateName({ name: 'Alice' });
 *   // updateName.pending — true while the request is in-flight
 *   // updateName.error  — error message string on failure, null otherwise
 *   // updateName.data   — last successful response data, null initially
 *
 * The hook resolves the action endpoint automatically from the current page path.
 * Pass an explicit `pagePath` option if calling an action defined on another page.
 */

import { useState, useCallback, useRef } from 'react';

function getCsrfToken() {
  if (typeof document === 'undefined') return '';
  const match = document.cookie.match(/(?:^|;\s*)pyxle-csrf=([^;]*)/);
  return match ? decodeURIComponent(match[1]) : '';
}

function resolveActionUrl(actionName, pagePath) {
  let page = pagePath;
  if (!page) {
    if (typeof window !== 'undefined') {
      page = window.location.pathname;
    } else if (typeof globalThis.__PYXLE_CURRENT_PATHNAME__ === 'string') {
      // SSR: use the request path the framework injected before rendering,
      // so the server and client agree on the form's action URL and
      // React doesn't fire a hydration mismatch warning.
      page = globalThis.__PYXLE_CURRENT_PATHNAME__;
    } else {
      page = '/';
    }
  }
  const segment = page.replace(/^\//, '') || 'index';
  return `/api/__actions/${segment}/${actionName}`;
}

/**
 * @param {string} actionName  Name of the @action function on the server.
 * @param {{ pagePath?: string, onMutate?: (payload: unknown) => void }} [options]
 */
export function useAction(actionName, options = {}) {
  const { pagePath, onMutate } = options;
  const [pending, setPending] = useState(false);
  const [error, setError] = useState(null);
  const [data, setData] = useState(null);
  const abortRef = useRef(null);

  const execute = useCallback(
    async (payload) => {
      if (abortRef.current) {
        abortRef.current.abort();
      }
      const controller = new AbortController();
      abortRef.current = controller;

      setError(null);
      setPending(true);

      if (typeof onMutate === 'function') {
        onMutate(payload);
      }

      try {
        const url = resolveActionUrl(actionName, pagePath);
        const csrfToken = getCsrfToken();
        const headers = { 'Content-Type': 'application/json' };
        if (csrfToken) headers['x-csrf-token'] = csrfToken;
        const response = await fetch(url, {
          method: 'POST',
          headers,
          body: JSON.stringify(payload ?? {}),
          signal: controller.signal,
        });

        const json = await response.json();

        if (!response.ok || json.ok === false) {
          const message = json.error ?? `Action failed with status ${response.status}`;
          setError(message);
          return { ok: false, error: message, data: json.data ?? null };
        }

        const { ok: _ok, error: _err, ...rest } = json;
        setData(rest);
        return { ok: true, ...rest };
      } catch (err) {
        if (err.name === 'AbortError') {
          return { ok: false, error: 'Request aborted' };
        }
        const message = err.message ?? 'Network error';
        setError(message);
        return { ok: false, error: message };
      } finally {
        if (abortRef.current === controller) {
          setPending(false);
          abortRef.current = null;
        }
      }
    },
    [actionName, pagePath, onMutate],
  );

  execute.pending = pending;
  execute.error = error;
  execute.data = data;

  return execute;
}
