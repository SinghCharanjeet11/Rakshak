/* Rakshak service worker.
 *
 * ─────────────────────────────────────────────────────────────────────────────
 * THE ONE RULE THAT MATTERS: never serve a compliance verdict from cache.
 * ─────────────────────────────────────────────────────────────────────────────
 * A stale report is worse than no report. If someone opens this offline and sees a
 * cached "score 100", they may believe an agent run was clean when it was not, and the
 * whole product is a claim about trustworthy verdicts. So every request to the API is
 * network-only: no cache read, no cache write, no fallback. Offline means the UI loads
 * and says it cannot reach the backend — never that everything passed.
 *
 * What IS cached: the app shell and static assets, so the installed app opens instantly
 * and survives a flaky connection.
 */

const VERSION = "rakshak-v1";
const SHELL = `${VERSION}-shell`;
const ASSETS = `${VERSION}-assets`;

// Precached so a cold install can open offline.
const SHELL_URLS = ["/", "/verify", "/rules", "/offline"];

/** Anything that must always come from the network. */
function isVerdictTraffic(url) {
  return (
    url.pathname.startsWith("/api/") ||
    // the backend runs on its own origin/port in dev and prod
    /:8000$/.test(url.host) ||
    url.pathname.includes("/verify/batch")
  );
}

function isStaticAsset(url) {
  return (
    url.pathname.startsWith("/_next/static/") ||
    url.pathname.startsWith("/logo-") ||
    url.pathname.startsWith("/icon") ||
    url.pathname.startsWith("/splash-") ||
    url.pathname.startsWith("/apple-icon") ||
    /\.(png|jpg|jpeg|svg|webp|woff2?|ico)$/.test(url.pathname)
  );
}

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(SHELL)
      // addAll rejects the whole batch if one URL 404s, which would leave the SW
      // uninstalled; tolerate individual misses instead.
      .then((cache) => Promise.allSettled(SHELL_URLS.map((u) => cache.add(u))))
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys.filter((k) => !k.startsWith(VERSION)).map((k) => caches.delete(k)),
        ),
      )
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") return;

  let url;
  try {
    url = new URL(request.url);
  } catch {
    return;
  }

  // 1. Verdicts and every other API call: network only. Deliberately no fallback.
  if (isVerdictTraffic(url)) return;

  // 2. Static assets: cache-first. Immutable and hashed, so staleness is not a risk.
  if (isStaticAsset(url) && url.origin === self.location.origin) {
    event.respondWith(
      caches.match(request).then(
        (hit) =>
          hit ??
          fetch(request).then((res) => {
            if (res.ok) {
              const copy = res.clone();
              caches.open(ASSETS).then((c) => c.put(request, copy));
            }
            return res;
          }),
      ),
    );
    return;
  }

  // 3. Navigations: network-first so a deploy is picked up, cache as the offline net.
  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request)
        .then((res) => {
          const copy = res.clone();
          caches.open(SHELL).then((c) => c.put(request, copy));
          return res;
        })
        .catch(async () =>
          (await caches.match(request)) ??
          (await caches.match("/offline")) ??
          new Response("Offline", { status: 503, headers: { "Content-Type": "text/plain" } }),
        ),
    );
  }
});
