const CACHE_NAME = 'fm-uqqc-pwa-v61';
const ASSET_ROOT = '/assets/factory_management/uqqc/';
const FRAPPE_ASSET_ROOT = '/assets/frappe/dist/';
const SHELL = ['/uqqc', ...['client.js?v=54', 'i18n.js?v=44', 'brand.css?v=49', 'manifest.json', 'logo.png', 'icon.svg'].map(name => ASSET_ROOT + name)];

self.addEventListener('install', event => {
    event.waitUntil((async () => {
        const cache = await caches.open(CACHE_NAME);
        await cache.addAll(SHELL);
        const page = await cache.match('/uqqc');
        const html = await page.text();
        const assets = [...html.matchAll(/(?:href|src)=["'](\/assets\/frappe\/dist\/[^"']+)["']/g)]
            .map(match => match[1]);
        await cache.addAll([...new Set(assets)]);
        await self.skipWaiting();
    })());
});
self.addEventListener('activate', event => {
    event.waitUntil(caches.keys().then(keys => Promise.all(
        keys.filter(key => key.startsWith('fm-uqqc-') && key !== CACHE_NAME).map(key => caches.delete(key))
    )).then(() => self.clients.claim()));
});
self.addEventListener('message', event => {
    if (event.data?.type === 'SKIP_WAITING') self.skipWaiting();
});
self.addEventListener('fetch', event => {
    const request = event.request;
    const url = new URL(request.url);
    if (request.method !== 'GET' || url.origin !== self.location.origin) return;
    const isPage = url.pathname.replace(/\/$/, '') === '/uqqc';
    // Only pages under this worker's /uqqc scope use this native asset cache.
    if (!isPage && !url.pathname.startsWith(ASSET_ROOT) && !url.pathname.startsWith(FRAPPE_ASSET_ROOT)) return;
    event.respondWith((async () => {
        const cache = await caches.open(CACHE_NAME);
        if (!isPage) {
            const asset = await cache.match(request, { ignoreSearch: true });
            if (asset) return asset;
        }
        try {
            const response = await fetch(request);
            if (response.ok) await cache.put(isPage ? '/uqqc' : request, response.clone()).catch(() => {});
            return response;
        } catch {
            return await cache.match(isPage ? '/uqqc' : request, { ignoreSearch: true }) || Response.error();
        }
    })());
});
