/* Minimal app-shell service worker. v1 only caches the start page so the PWA
 * installs cleanly and survives quick offline blips. No push, no background
 * sync, no API caching (the agent is dynamic and dry-run safe — re-fetches
 * are fine). */

const CACHE = "mom-shell-v1";
const SHELL = ["/", "/manifest.webmanifest"];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))),
    ),
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  // Never cache API or non-GET requests.
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.pathname.startsWith("/agent/") || url.origin !== location.origin) {
    return;
  }
  // Stale-while-revalidate for shell GETs.
  event.respondWith(
    caches.match(req).then((cached) => {
      const fetched = fetch(req)
        .then((res) => {
          if (res.ok) {
            const copy = res.clone();
            caches.open(CACHE).then((c) => c.put(req, copy));
          }
          return res;
        })
        .catch(() => cached);
      return cached ?? fetched;
    }),
  );
});
