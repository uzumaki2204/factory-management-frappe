const CACHE = 'factory-qc-v59';
const QC_SCRIPT_PATH = '/assets/factory_management/js/qc.js';
const SHELL = ['/assets/factory_management/js/qc-i18n.json?v=45', '/assets/factory_management/css/qc-layout.css?v=12', '/assets/factory_management/images/qc-logo.png', '/assets/factory_management/manifest.json'];

function qcScriptUrl(html) {
  const scripts = [...html.matchAll(/<script\b[^>]*\bsrc=["']([^"']+)["']/gi)];
  for (const match of scripts) {
    let url;
    try { url = new URL(match[1], self.location.origin); }
    catch (_) { continue; }
    if (url.origin === self.location.origin && url.pathname === QC_SCRIPT_PATH)
      return url.pathname + url.search;
  }
  throw new Error('QC client script missing from page');
}

async function cachePublicPage(targetCache = null) {
  // Frappe's Web Page embeds session data. Cache only its public Guest variant.
  const page = await fetch('/qc', {cache: 'reload', credentials: 'omit'});
  if (!page.ok) throw new Error('QC page unavailable');
  const pageForCache = page.clone();
  const html = await page.text();
  const scriptUrl = qcScriptUrl(html);
  const cache = targetCache || await caches.open(CACHE);
  let script = await cache.match(scriptUrl);
  if (!script) {
    script = await fetch(scriptUrl, {cache: 'reload', credentials: 'omit'});
    if (!script.ok) throw new Error('QC client script unavailable');
    await cache.put(scriptUrl, script.clone());
  }
  const assets = [...html.matchAll(/(?:href|src)="([^"]+)"/g)]
    .map(match => match[1])
    .filter(url => url.startsWith('/assets/frappe/dist/') && /\.(?:css|js)(?:\?.*)?$/.test(url));
  for (const url of new Set(assets)) {
    try {
      const response = await fetch(url, {cache: 'reload'});
      if (response.ok) await cache.put(url, response);
    } catch (_) {}
  }
  await cache.put('/qc', pageForCache);
}

self.addEventListener('install', event => {
  event.waitUntil((async () => {
    const cache = await caches.open(CACHE);
    await cachePublicPage(cache);
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
