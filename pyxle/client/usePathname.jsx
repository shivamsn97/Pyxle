/**
 * usePathname — reactively track the current URL pathname.
 *
 * Usage:
 *   const pathname = usePathname();
 *   // Re-renders whenever Pyxle performs a client-side navigation.
 *
 * During SSR the hook reads the request pathname from
 * `globalThis.__PYXLE_CURRENT_PATHNAME__` (set by the SSR worker before
 * render), which keeps the server and client output in sync and avoids
 * hydration mismatches on active-link highlighting.  It falls back to
 * '/' only when that global is missing (e.g. a unit test rendering
 * without going through the SSR pipeline).
 */

import { useState, useEffect } from 'react';

function _getInitialPathname() {
  if (typeof window !== 'undefined') {
    return window.location.pathname;
  }
  if (typeof globalThis.__PYXLE_CURRENT_PATHNAME__ === 'string') {
    return globalThis.__PYXLE_CURRENT_PATHNAME__;
  }
  return '/';
}

export function usePathname() {
  const [pathname, setPathname] = useState(_getInitialPathname);

  useEffect(() => {
    // Sync on mount in case the SSR value differs.
    setPathname(window.location.pathname);

    function onRouteChange() {
      setPathname(window.location.pathname);
    }

    window.addEventListener('pyxle:routechange', onRouteChange);
    window.addEventListener('popstate', onRouteChange);
    return () => {
      window.removeEventListener('pyxle:routechange', onRouteChange);
      window.removeEventListener('popstate', onRouteChange);
    };
  }, []);

  return pathname;
}
