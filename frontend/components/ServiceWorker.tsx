"use client";

import { useEffect } from "react";

/**
 * Registers the service worker.
 *
 * Only in production: a service worker in front of the dev server caches the shell and then
 * serves it back over HMR, which looks exactly like "my edit did nothing".
 *
 * Registration is deferred to `load` so it never competes with the first paint for
 * bandwidth — on a phone the shell mattering more than the cache is the whole point.
 */
export function ServiceWorker() {
  useEffect(() => {
    if (process.env.NODE_ENV !== "production") return;
    if (!("serviceWorker" in navigator)) return;

    const register = () => {
      navigator.serviceWorker.register("/sw.js").catch(() => {
        // A failed registration must never be user-visible: the app works fine without it.
      });
    };

    if (document.readyState === "complete") register();
    else window.addEventListener("load", register, { once: true });

    return () => window.removeEventListener("load", register);
  }, []);

  return null;
}
