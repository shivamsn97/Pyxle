/**
 * usePathname — reactively track the current URL pathname.
 *
 * Usage:
 *   const pathname = usePathname();
 *   // Re-renders whenever Pyxle performs a client-side navigation.
 *
 * Returns window.location.pathname on the client. During SSR returns '/'.
 */

import { useState, useEffect } from 'react';

export function usePathname() {
  const [pathname, setPathname] = useState(
    typeof window !== 'undefined' ? window.location.pathname : '/'
  );

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
