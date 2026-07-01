const CACHE = 'onff-v4';
const BASE = '/observatorio-formacao-farmaceutica/';

const PRECACHE = [
  BASE,
  BASE + 'index.html',
  BASE + 'static/css/style.css',
  BASE + 'static/js/app.js',
  BASE + 'static/js/glossario.js',
  BASE + 'static/manifest.json',
  BASE + 'static/img/logo.png',
  BASE + 'static/img/icon-192.png',
  BASE + 'static/img/icon-512.png',
  BASE + 'static/vendor/chart.umd.min.js',
  BASE + 'static/vendor/leaflet/leaflet.js',
  BASE + 'static/vendor/leaflet/leaflet.css'
];

self.addEventListener('install', e => {
  // Cache resiliente: cada recurso individualmente; uma falha não aborta a
  // instalação do service worker (essencial para a elegibilidade de instalação).
  e.waitUntil(
    caches.open(CACHE).then(c =>
      Promise.allSettled(PRECACHE.map(u => c.add(u)))
    ).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', e => {
  const { request } = e;
  if (request.method !== 'GET') return;
  const url = new URL(request.url);

  // Cache-first for static assets; network-first for HTML
  const isHtml = request.headers.get('accept') && request.headers.get('accept').includes('text/html');

  if (isHtml) {
    // Network first → fall back to cache
    e.respondWith(
      fetch(request)
        .then(res => {
          const clone = res.clone();
          caches.open(CACHE).then(c => c.put(request, clone));
          return res;
        })
        .catch(() => caches.match(request).then(r => r || caches.match(BASE + 'index.html')))
    );
  } else {
    // Cache first → fall back to network
    e.respondWith(
      caches.match(request).then(cached => {
        if (cached) return cached;
        return fetch(request).then(res => {
          if (res.ok) {
            const clone = res.clone();
            caches.open(CACHE).then(c => c.put(request, clone));
          }
          return res;
        });
      })
    );
  }
});
