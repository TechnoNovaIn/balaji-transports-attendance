const CACHE_NAME = 'balaji-workforce-v1';
const STATIC_ASSETS = [
  '/static/css/style.css',
  '/static/js/app.js',
  '/static/js/attendance.js',
  '/static/js/dashboard.js',
  '/static/icons/icon-192.png',
  '/static/icons/icon-512.png',
  '/manifest.json'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(STATIC_ASSETS)).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // Only handle same-origin GET requests; never intercept POST or /api/ calls
  if (request.method !== 'GET' || url.origin !== self.location.origin || url.pathname.startsWith('/api/')) {
    return;
  }

  // Static assets: cache-first with background refresh
  if (url.pathname.startsWith('/static/') || url.pathname === '/manifest.json') {
    event.respondWith(
      caches.match(request).then((cached) => {
        const networkFetch = fetch(request).then((response) => {
          if (response && response.status === 200) {
            const copy = response.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(request, copy));
          }
          return response;
        }).catch(() => cached);
        return cached || networkFetch;
      })
    );
    return;
  }

  // Navigation / HTML pages: always network-first so auth and CSRF tokens stay fresh
  if (request.mode === 'navigate') {
    event.respondWith(
      fetch(request).catch(() =>
        new Response(
          '<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Offline · Balaji Transports</title><style>body{font-family:sans-serif;background:#f6f8fb;color:#17233c;display:grid;place-items:center;min-height:100vh;margin:0;padding:24px;text-align:center}.card{background:#fff;border:1px solid #e9edf3;border-radius:14px;padding:28px;max-width:360px}button{margin-top:16px;background:#4563eb;color:#fff;border:0;border-radius:8px;padding:10px 18px;font-weight:700;cursor:pointer}</style></head><body><div class="card"><h2>You are offline</h2><p>An active internet connection is required to sign in and mark GPS attendance.</p><button onclick="location.reload()">Try again</button></div></body></html>',
          { headers: { 'Content-Type': 'text/html; charset=utf-8' } }
        )
      )
    );
  }
});
