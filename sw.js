const CACHE_NAME = 'dc-restaurantes-v1_0_1';
const STATIC_ASSETS = [
  '/',
  '/index.html',
  '/styles.css',
  '/app.js',
  '/chart.umd.min.js',
  '/xlsx.full.min.js',
  '/manifest.json',
  '/assets/icon-192.png',
  '/assets/icon-512.png',
  '/assets/icon-maskable.png',
  '/assets/logo-emblema.png'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(STATIC_ASSETS).catch((err) => console.log('PWA cache prefetch note:', err));
    }).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.map((key) => {
          if (key !== CACHE_NAME) {
            return caches.delete(key);
          }
        })
      );
    }).then(() => self.clients.claim())
  );
});

// Estrategia Network-First con fallback a caché
self.addEventListener('fetch', (event) => {
  if (event.request.method !== 'GET') return;
  const url = new URL(event.request.url);
  // No interceptar peticiones externas (Firebase Firestore, Google APIs, CDNs)
  if (url.origin !== self.location.origin) return;

  event.respondWith(
    fetch(event.request)
      .then((networkResponse) => {
        if (networkResponse && networkResponse.status === 200 && url.origin === self.location.origin) {
          const responseClone = networkResponse.clone();
          caches.open(CACHE_NAME).then((cache) => {
            cache.put(event.request, responseClone);
          });
        }
        return networkResponse;
      })
      .catch(() => {
        return caches.match(event.request).then((cachedResponse) => {
          if (cachedResponse) return cachedResponse;
          if (event.request.mode === 'navigate') {
            return caches.match('/index.html');
          }
        });
      })
  );
});
