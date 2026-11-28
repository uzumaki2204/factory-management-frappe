const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const source = readFileSync(path.join(__dirname, '..', 'factory_management', 'www', 'qc-sw.js'), 'utf8');
const pageHead = readFileSync(path.join(__dirname, '..', 'factory_management', 'templates', 'includes', 'qc_head.html'), 'utf8');
const pageUrl = '/qc';
const clientMatch = pageHead.match(/<script src="([^"]*\/qc\.js\?v=([^"]+))"/);
assert.ok(clientMatch, 'QC page must reference a versioned client script');
const clientUrl = clientMatch[1];
const clientVersion = clientMatch[2];

class MockResponse {
    constructor(body, status = 200) {
        this.body = body;
        this.status = status;
        this.ok = status >= 200 && status < 300;
    }

    clone() { return new MockResponse(this.body, this.status); }
    async text() { return this.body; }
}

function createWorker({ clientStatus = 200, oldCache = null } = {}) {
    const listeners = {};
    const cacheStores = new Map();
    const requests = [];
    let skipWaitingCalls = 0;
    const makeCache = () => {
        const entries = new Map();
        return {
            entries,
            async put(key, response) { entries.set(String(key), response.clone()); },
            async match(key) { return entries.get(String(key)); }
        };
    };
    if (oldCache) cacheStores.set('factory-qc-v58', oldCache);
    const caches = {
        async open(name) {
            if (!cacheStores.has(name)) cacheStores.set(name, makeCache());
            return cacheStores.get(name);
        },
        async keys() { return [...cacheStores.keys()]; },
        async match(key) {
            for (const cache of cacheStores.values()) {
                const hit = await cache.match(key);
                if (hit) return hit;
            }
            return undefined;
        }
    };
    const page = `<html><script src="${clientUrl}" defer></script>` +
        '<link href="/assets/frappe/dist/desk.css" rel="stylesheet"></html>';
    const fetch = async input => {
        const url = String(input);
        requests.push(url);
        if (url === pageUrl) return new MockResponse(page);
        if (url === clientUrl) return new MockResponse(`qc-client-source-${clientVersion}`, clientStatus);
        return new MockResponse(`asset:${url}`);
    };
    const self = {
        location: { origin: 'https://qc.test' },
        addEventListener(type, handler) { listeners[type] = handler; },
        async skipWaiting() { skipWaitingCalls++; },
        clients: { async claim() {} }
    };
    vm.runInNewContext(source, { self, caches, fetch, URL, Response: MockResponse });
    return { listeners, cacheStores, requests, get skipWaitingCalls() { return skipWaitingCalls; } };
}

function install(worker) {
    let pending;
    worker.listeners.install({ waitUntil(promise) { pending = promise; } });
    return pending;
}

test('QC service worker caches the client script referenced by the current page', async () => {
    const worker = createWorker();
    await install(worker);
    const cache = worker.cacheStores.get('factory-qc-v59');
    assert.equal((await cache.match(clientUrl)).body, `qc-client-source-${clientVersion}`);
    assert.match((await cache.match(pageUrl)).body, new RegExp(`qc\\.js\\?v=${clientVersion}`));
    assert.equal(worker.skipWaitingCalls, 1);
});

test('QC service worker keeps the old cache active if the current client script cannot load', async () => {
    const oldStore = new Map([['/qc', new MockResponse('old-page')], [
        '/assets/factory_management/js/qc.js?v=56', new MockResponse('old-client-source')
    ]]);
    const oldCacheValue = {
        async put(key, response) { oldStore.set(String(key), response.clone()); },
        async match(key) { return oldStore.get(String(key)); }
    };
    const worker = createWorker({ clientStatus: 503, oldCache: oldCacheValue });
    await assert.rejects(install(worker), /QC client script unavailable/);
    assert.equal(worker.skipWaitingCalls, 0);
    assert.equal(await worker.cacheStores.get('factory-qc-v59').match('/qc'), undefined);
    assert.equal((await oldCacheValue.match('/qc')).body, 'old-page');
    assert.equal((await oldCacheValue.match('/assets/factory_management/js/qc.js?v=56')).body,
        'old-client-source');
});
