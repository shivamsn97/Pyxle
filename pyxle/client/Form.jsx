/**
 * Form — a progressive-enhancement form component that integrates with @action.
 *
 * When JavaScript is available, form submission is intercepted and dispatched
 * to the given action via fetch. When JS is disabled, the form falls back to a
 * standard HTML POST to the action endpoint.
 *
 * Usage:
 *   <Form action="create_post" onSuccess={(data) => navigate('/posts')}>
 *     <input name="title" />
 *     <button type="submit">Create</button>
 *   </Form>
 *
 * Props:
 *   action       {string}   Name of the @action function on the server.
 *   pagePath     {string?}  Override the page used to resolve the endpoint.
 *   onSuccess    {function} Called with the response data on success.
 *   onError      {function} Called with the error message on failure.
 *   resetOnSuccess {boolean} Reset form fields after a successful submission (default true).
 *   children     {node}     Form contents (inputs, buttons, etc.).
 *   ...rest                 Any additional props forwarded to <form>.
 */

import React, { useRef, useState, useCallback } from 'react';

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
      // SSR: use the framework-injected request path so the form's action
      // URL matches the one the client will compute at hydration.
      page = globalThis.__PYXLE_CURRENT_PATHNAME__;
    } else {
      page = '/';
    }
  }
  const segment = page.replace(/^\//, '') || 'index';
  return `/api/__actions/${segment}/${actionName}`;
}

export function Form({
  action,
  pagePath,
  onSuccess,
  onError,
  resetOnSuccess = true,
  children,
  ...rest
}) {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState(null);
  const formRef = useRef(null);

  const actionUrl = resolveActionUrl(action, pagePath);

  const handleSubmit = useCallback(
    async (event) => {
      event.preventDefault();
      if (pending) return;

      const form = formRef.current;
      if (!form) return;

      const formData = new FormData(form);
      const payload = Object.fromEntries(formData.entries());

      setError(null);
      setPending(true);

      try {
const csrfToken = getCsrfToken();
                const headers = { 'Content-Type': 'application/json' };
                if (csrfToken) headers['x-csrf-token'] = csrfToken;
                const response = await fetch(actionUrl, {
          method: 'POST',
          headers,
          body: JSON.stringify(payload),
        });

        const json = await response.json();

        if (!response.ok || json.ok === false) {
          const message = json.error ?? `Action failed with status ${response.status}`;
          setError(message);
          if (typeof onError === 'function') {
            onError(message);
          }
          return;
        }

        const { ok: _ok, error: _err, ...data } = json;

        if (resetOnSuccess && form) {
          form.reset();
        }

        if (typeof onSuccess === 'function') {
          onSuccess(data);
        }
      } catch (err) {
        const message = err.message ?? 'Network error';
        setError(message);
        if (typeof onError === 'function') {
          onError(message);
        }
      } finally {
        setPending(false);
      }
    },
    [actionUrl, pending, onSuccess, onError, resetOnSuccess],
  );

  return (
    <form
      ref={formRef}
      method="POST"
      action={actionUrl}
      onSubmit={handleSubmit}
      {...rest}
    >
      {children}
      {error && (
        <p role="alert" style={{ color: 'red', marginTop: '0.5rem' }}>
          {error}
        </p>
      )}
    </form>
  );
}
