/**
 * <Image> — a thin wrapper around the native <img> with four useful
 * behaviours on top:
 *
 *   1. Native lazy-loading    via the standard `loading` attribute,
 *                             controlled by `priority` / `lazy`.
 *   2. Blur-up placeholder    `placeholder="blur"` renders a blurred
 *                             background image (from `blurDataURL`) or a
 *                             solid color until the real image loads, then
 *                             smoothly transitions to sharp.
 *   3. Loading / error state  `onLoad` / `onError` callbacks fire once per
 *                             transition; the element also exposes the
 *                             state via `data-pyxle-image-state`.
 *   4. Graceful fallback      An optional `fallbackSrc` kicks in on error
 *                             so a broken image URL doesn't leave a blank
 *                             box (can still be combined with `onError`).
 *
 * Everything else — `srcSet`, `sizes`, `className`, `style`, `onClick`, … —
 * passes straight through to the underlying <img>.
 */

import { useEffect, useRef, useState } from 'react';

const STATE_LOADING = 'loading';
const STATE_LOADED = 'loaded';
const STATE_ERROR = 'error';


export function Image({
  src,
  alt = '',
  width,
  height,
  priority = false,
  lazy = true,
  placeholder = 'empty',
  blurDataURL,
  placeholderColor = '#e5e5e5',
  fallbackSrc,
  onLoad,
  onError,
  className,
  style,
  ...props
}) {
  const [state, setState] = useState(STATE_LOADING);
  const [currentSrc, setCurrentSrc] = useState(src);
  const imgRef = useRef(null);

  // Reset loading state when src changes.
  useEffect(() => {
    setState(STATE_LOADING);
    setCurrentSrc(src);
  }, [src]);

  // If an image is already cached by the browser (common on hover-prefetch
  // or client-side navigation), the `load` event never fires on the new
  // element.  Check `complete` after mount and sync state manually.
  //
  // Symmetrically: when SSR renders an `<img>` with a broken `src`, the
  // browser may finish the failed fetch before React hydrates, meaning the
  // synthetic `onError` listener is attached too late to see the event.  In
  // that case `complete` is still true but `naturalWidth` is 0 — treat as
  // error and drive the fallback / onError path.
  useEffect(() => {
    const el = imgRef.current;
    if (!el || !el.complete || state !== STATE_LOADING) return;

    if (el.naturalWidth > 0) {
      setState(STATE_LOADED);
      if (onLoad) onLoad({ nativeEvent: null, target: el, fromCache: true });
    } else {
      // Image finished fetching but has no pixels — treat as error.
      if (fallbackSrc && currentSrc !== fallbackSrc) {
        setCurrentSrc(fallbackSrc);
      } else {
        setState(STATE_ERROR);
        if (onError) onError({ nativeEvent: null, target: el });
      }
    }
    // Only run on mount and when src changes; callbacks intentionally omitted.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentSrc]);

  function handleLoad(event) {
    setState(STATE_LOADED);
    if (onLoad) onLoad(event);
  }

  function handleError(event) {
    if (fallbackSrc && currentSrc !== fallbackSrc) {
      setCurrentSrc(fallbackSrc);
      return; // wait for the fallback to load / fail
    }
    setState(STATE_ERROR);
    if (onError) onError(event);
  }

  const showPlaceholder = placeholder === 'blur' && state === STATE_LOADING;

  const mergedStyle = {
    ...(showPlaceholder
      ? {
          backgroundColor: blurDataURL ? undefined : placeholderColor,
          backgroundImage: blurDataURL ? `url("${blurDataURL}")` : undefined,
          backgroundSize: 'cover',
          backgroundPosition: 'center',
          backgroundRepeat: 'no-repeat',
          filter: blurDataURL ? 'blur(20px)' : undefined,
        }
      : {}),
    // Smooth transition once the image renders on top.
    transition: placeholder === 'blur' ? 'filter 250ms ease-out' : undefined,
    ...style,
  };

  return (
    <img
      ref={imgRef}
      src={currentSrc}
      alt={alt}
      width={width}
      height={height}
      loading={priority ? 'eager' : lazy ? 'lazy' : 'eager'}
      decoding={priority ? 'sync' : 'async'}
      onLoad={handleLoad}
      onError={handleError}
      className={className}
      style={mergedStyle}
      data-pyxle-image-state={state}
      {...props}
    />
  );
}
