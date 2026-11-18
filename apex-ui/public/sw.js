// APEX UI service worker. Caches the same-origin UI shell only.
// Never touches /api/ requests, cross-origin requests or non-GET requests, so
// no personal data, chat content or dashboard payload is ever written to the cache.
const CACHE = "apex-ui-v16";
const SHELL = ["/", "/manifest.json", "/icons/icon-192.png", "/icons/icon-512.png"];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  const url = new URL(request.url);
  if (request.method !== "GET" || url.origin !== self.location.origin) return;
  // The API is now served from this same origin. Its answers are personal and must always be
  // live, so they are never cached and never answered from cache.
  if (url.pathname.startsWith("/api/")) return;

  // Vite's /assets/* files are content-hashed, so a cached copy is always the right one.
  if (url.pathname.startsWith("/assets/")) {
    event.respondWith(
      caches.match(request).then((hit) => hit || fetch(request).then((res) => {
        if (res.ok) { const copy = res.clone(); caches.open(CACHE).then((c) => c.put(request, copy)); }
        return res;
      }))
    );
    return;
  }

  // Everything else (the HTML shell, icons, face-detector model): answer from cache at once
  // and refresh the cache in the background, so a new deploy shows up on the next open.
  event.respondWith(
    caches.open(CACHE).then((cache) =>
      cache.match(request, { ignoreSearch: request.mode === "navigate" }).then((hit) => {
        const refresh = fetch(request).then((res) => {
          if (res.ok && res.type === "basic") cache.put(request, res.clone());
          return res;
        }).catch(() => hit);
        // The page itself always comes from the server when it answers, so a new deploy shows at
        // once; the stored copy is only for when the server cannot be reached.
        return request.mode === "navigate" ? refresh.then((res) => res || hit) : (hit || refresh);
      })
    )
  );
});
