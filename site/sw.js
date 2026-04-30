/* Area52 service worker — minimal offline shell + smart caching */
const VERSION = 'a52-v1';
const APP_SHELL = [
  '/',
  '/area52_live.html',
  '/manifest.webmanifest',
  '/icon-192.png',
  '/icon-512.png'
];

self.addEventListener('install', (e) => {
  e.waitUntil(
    caches.open(VERSION).then((c) => c.addAll(APP_SHELL)).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== VERSION).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (e) => {
  const req = e.request;
  if (req.method !== 'GET') return;

  const url = new URL(req.url);

  // Never cache live inventory / Scryfall / Moxfield API calls — always fetch fresh.
  if (url.pathname.startsWith('/api/') ||
      url.pathname.startsWith('/scryfall/') ||
      url.pathname.startsWith('/moxfield/')) {
    return; // default network behavior
  }

  // HTML navigations: network-first so updates ship immediately, fall back to cache offline.
  if (req.mode === 'navigate' || req.headers.get('accept')?.includes('text/html')) {
    e.respondWith(
      fetch(req).then((res) => {
        const copy = res.clone();
        caches.open(VERSION).then((c) => c.put(req, copy)).catch(()=>{});
        return res;
      }).catch(() => caches.match(req).then((m) => m || caches.match('/area52_live.html')))
    );
    return;
  }

  // Static assets: cache-first.
  e.respondWith(
    caches.match(req).then((cached) =>
      cached || fetch(req).then((res) => {
        if (res.ok && (url.origin === self.location.origin || url.host === 'fonts.googleapis.com' || url.host === 'fonts.gstatic.com')) {
          const copy = res.clone();
          caches.open(VERSION).then((c) => c.put(req, copy)).catch(()=>{});
        }
        return res;
      }).catch(() => cached)
    )
  );
});
