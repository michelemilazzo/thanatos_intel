// Thanatos Switchboard service worker (v14)
// STRATEGY:
//  - HTML shell (/ops/, /ops/index.html) = NETWORK-FIRST (fallback cache, fallback Response(503))
//  - Asset statici (manifest, icone, socket.io, /assets/...) = CACHE-FIRST
//  - API /api/*  = MAI cachate (bypass totale del SW)
// Push handler + click-to-open invariati.
// Fix v14: tutte le respondWith ora ritornano una Response valida in ogni ramo,
// evitando "Failed to convert value to 'Response'" quando la rete cade.
const VERSION = 'sw-v14-2026-07-01';
const STATIC = ['/ops/manifest.json', '/ops/icon-192.png',
                '/ops/icon-512.png', '/ops/socket.io.min.js'];

function offlineHtml() {
  return new Response(
    '<!doctype html><meta charset=utf-8><title>Offline</title>' +
    '<style>body{background:#0A0E1A;color:#C8A96E;font-family:Georgia,serif;' +
    'display:flex;align-items:center;justify-content:center;height:100vh;margin:0;text-align:center}' +
    'div{max-width:320px;padding:24px}</style>' +
    '<div><h2>Connessione non disponibile</h2>' +
    '<p style=color:#A4A9BC>Riprova tra qualche istante.</p></div>',
    { status: 503, headers: { 'Content-Type': 'text/html; charset=utf-8' } }
  );
}

self.addEventListener('install', e => {
  e.waitUntil(
    caches.open(VERSION)
      .then(c => c.addAll(STATIC).catch(() => {}))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys => Promise.all(
      keys.filter(k => k !== VERSION).map(k => caches.delete(k))
    )).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', e => {
  if (e.request.method !== 'GET') return;
  const url = new URL(e.request.url);

  // MAI intercettare API/socket/method
  if (url.pathname.startsWith('/api/') ||
      url.pathname.startsWith('/socket.io') ||
      url.pathname.startsWith('/method/')) return;

  // HTML shell → network-first (fallback cache, fallback offline page)
  const isShell = url.pathname === '/ops/' || url.pathname === '/ops/index.html';
  if (isShell) {
    e.respondWith((async () => {
      try {
        const resp = await fetch(e.request);
        if (resp && resp.ok) {
          const clone = resp.clone();
          caches.open(VERSION).then(c => c.put(e.request, clone)).catch(() => {});
        }
        return resp;
      } catch (_) {
        const cached = await caches.match(e.request);
        return cached || offlineHtml();
      }
    })());
    return;
  }

  // Asset statici → cache-first (fallback network, fallback stub)
  if (STATIC.includes(url.pathname) ||
      url.pathname.startsWith('/assets/') ||
      url.pathname.startsWith('/ops/icon-')) {
    e.respondWith((async () => {
      const cached = await caches.match(e.request);
      if (cached) return cached;
      try {
        const resp = await fetch(e.request);
        if (resp && resp.ok) {
          const clone = resp.clone();
          caches.open(VERSION).then(c => c.put(e.request, clone)).catch(() => {});
        }
        return resp;
      } catch (_) {
        return new Response('', { status: 504, statusText: 'Gateway Timeout' });
      }
    })());
  }
});

self.addEventListener('push', e => {
  let data = {};
  try { data = e.data ? e.data.json() : {}; } catch (_) { data = {body: e.data?.text() || ''}; }
  const title = data.title || 'Thanatos Switchboard';
  const opts = {
    body: data.body || '',
    icon: '/ops/icon-192.png',
    badge: '/ops/icon-192.png',
    tag: data.tag || 'sb-msg',
    data: { lead: data.lead || null, url: data.url || '/ops/' },
    requireInteraction: !!data.urgent,
  };
  e.waitUntil(self.registration.showNotification(title, opts));
});

self.addEventListener('notificationclick', e => {
  e.notification.close();
  const url = e.notification.data?.url || '/ops/';
  e.waitUntil(
    self.clients.matchAll({type:'window', includeUncontrolled:true}).then(clients => {
      for (const c of clients) {
        if (c.url.includes('/ops/') && 'focus' in c) {
          c.postMessage({type:'open-lead', lead: e.notification.data?.lead});
          return c.focus();
        }
      }
      return self.clients.openWindow(url);
    })
  );
});

self.addEventListener('message', e => {
  if (e.data && e.data.type === 'skip-waiting') self.skipWaiting();
});
