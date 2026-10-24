const CACHE = 'factory-qc-v53';
const SHELL = ['/assets/factory_management/js/qc.js?v=51', '/assets/factory_management/js/qc-i18n.json?v=44', '/assets/factory_management/css/qc-layout.css?v=11', '/assets/factory_management/images/qc-logo.png', '/assets/factory_management/manifest.json'];

async function cachePublicPage() {
  // Frappe's Web Page embeds session data. Cache only its public Guest variant.
  const page = await fetch('/qc', {cache: 'reload', credentials: 'omit'});
  if (!page.ok) return;
  const cache = await caches.open(CACHE);
  await cache.put('/qc', page.clone());
  const html = await page.text();
  const assets = [...html.matchAll(/(?:href|src)="([^"]+)"/g)]
    .map(match => match[1])
    .filter(url => url.startsWith('/assets/frappe/dist/') && /\.(?:css|js)(?:\?.*)?$/.test(url));
  for (const url of new Set(assets)) {
    try {
      const response = await fetch(url, {cache: 'reload'});
      if (response.ok) await cache.put(url, response);
    } catch (_) {}
  }
}

self.addEventListener('install', event => {
  event.waitUntil((async () => {
    const cache = await caches.open(CACHE);
    try { await cachePublicPage(); } catch (_) {}
    for (const url of SHELL) {
      try {
        const response = await fetch(url, {cache: 'reload'});
        if (response.ok) await cache.put(url, response);
      } catch (_) {}
    }
    await self.skipWaiting();
  })());
});
self.addEventListener('activate', event => {
  event.waitUntil((async () => {
    for (const key of await caches.keys()) {
      if (key.startsWith('factory-qc-') && key !== CACHE) await caches.delete(key);
    }
    await self.clients.claim();
  })());
});
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);
  if (url.origin !== self.location.origin || event.request.method !== 'GET') return;
  if (url.pathname.startsWith('/api/')) return;
  if (url.pathname === '/qc' && event.request.mode === 'navigate') {
    event.respondWith(fetch(event.request).then(response => {
      if (response.ok) event.waitUntil(cachePublicPage().catch(() => {}));
      return response;
    }).catch(async () => (await caches.match('/qc')) || Response.error()));
    return;
  }
  if (url.pathname.startsWith('/assets/factory_management/') || url.pathname.startsWith('/assets/frappe/dist/')) {
    event.respondWith(caches.match(event.request).then(hit => hit || fetch(event.request)));
  }
});
