// Thanatos Switchboard service worker
// Shell cache + push notification handler. La PWA è network-first sui dati;
// solo asset statici (shell, manifest, icone) sono cache-first.
const VERSION = 'sw-v3-2026-07-01';
const SHELL = ['/ops/', '/ops/manifest.json', '/ops/icon-192.png', '/ops/icon-512.png'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(VERSION).then(c => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys => Promise.all(
      keys.filter(k => k !== VERSION).map(k => caches.delete(k))
    )).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);
  // mai cachare API/socket/api di frappe
  if (url.pathname.startsWith('/api/') ||
      url.pathname.startsWith('/socket.io') ||
      url.pathname.startsWith('/method/')) return;
  // cache-first per shell e asset statici
  if (e.request.method === 'GET' && (SHELL.includes(url.pathname) ||
       url.pathname.startsWith('/assets/'))) {
    e.respondWith(
      caches.match(e.request).then(r => r || fetch(e.request).then(resp => {
        if (resp.ok) {
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
