// Thanatos Switchboard service worker (v5)
// STRATEGY:
//  - HTML shell (/ops/, /ops/index.html) = NETWORK-FIRST (fallback cache)
//    -> aggiornamenti si vedono subito, cache serve solo offline
//  - Asset statici (manifest, icone, socket.io, /assets/...) = CACHE-FIRST
//  - API /api/*  = MAI cachate
// Push handler + click-to-open invariati.
const VERSION = 'sw-v13-2026-07-01';
const STATIC = ['/ops/manifest.json', '/ops/icon-192.png',
                '/ops/icon-512.png', '/ops/socket.io.min.js'];

self.addEventListener('install', e => {
  e.waitUntil(
    caches.open(VERSION).then(c => c.addAll(STATIC)).then(() => self.skipWaiting())
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
  // MAI cachare API/socket/method
  if (url.pathname.startsWith('/api/') ||
      url.pathname.startsWith('/socket.io') ||
      url.pathname.startsWith('/method/')) return;

  // HTML shell → network-first (aggiornamenti immediati)
  const isShell = url.pathname === '/ops/' || url.pathname === '/ops/index.html';
  if (isShell) {
    e.respondWith(
      fetch(e.request).then(resp => {
        if (resp && resp.ok) {
          const clone = resp.clone();
          caches.open(VERSION).then(c => c.put(e.request, clone));
        }
        return resp;
      }).catch(() => caches.match(e.request))
    );
    return;
  }

  // Assets statici → cache-first
  if (STATIC.includes(url.pathname) || url.pathname.startsWith('/assets/') ||
      url.pathname.startsWith('/ops/icon-')) {
    e.respondWith(
      caches.match(e.request).then(r => r || fetch(e.request).then(resp => {
        if (resp && resp.ok) {
          const clone = resp.clone();
          caches.open(VERSION).then(c => c.put(e.request, clone));
        }
        return resp;
      }))
    );
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

// Permetti alla pagina di forzare il ricaricamento del SW
self.addEventListener('message', e => {
  if (e.data && e.data.type === 'skip-waiting') self.skipWaiting();
});
