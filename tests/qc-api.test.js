const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const source = readFileSync(path.join(__dirname, '..', 'factory_management', 'public', 'js', 'qc.js'), 'utf8');

function productionFunction(name, async = false) {
    const start = source.indexOf(`${async ? 'async ' : ''}function ${name}(`);
    assert.notEqual(start, -1);
    let depth = 0;
    for (let index = source.indexOf(') {', start) + 2; index < source.length; index++) {
        if (source[index] === '{') depth++;
        if (source[index] === '}' && --depth === 0) return source.slice(start, index + 1);
    }
    throw new Error(`Unclosed function: ${name}`);
}

function createApi(fetch, generation = 'current') {
    const items = new Map([['factory.qc.v1.queue', '[{"local_event_id":"pending"}]']]);
    let reloads = 0;
    const context = {
        fetch, URLSearchParams, state: { device: { id: 'device' } },
        epochGeneration: generation, epochReloading: false, PREFIX: 'factory.qc.v1.',
        epochUrl: '/api/method/factory_management.api.data_epoch',
        urlRoot: '/api/method/factory_management.api.', navigator: { onLine: true },
        t: key => key, window: { location: { reload() { reloads++; } } },
        localStorage: { getItem: key => items.get(key), setItem: (key, value) => items.set(key, value),
            removeItem: key => items.delete(key) }
    };
    vm.runInNewContext([
        productionFunction('call', true), productionFunction('responseData'), productionFunction('ensureDataEpoch', true),
        'globalThis.api = { call };'
    ].join('\n'), context);
    return { ...context.api, items, get reloads() { return reloads; } };
}

function response(payload, status = 200) { return { ok: status === 200, status, json: async () => payload }; }

function createBootstrapLoader({ catalog = null, version = '', responses = [], online = true }) {
    const calls = [];
    const items = new Map();
    let renders = 0;
    const state = { pageUnlocked: true, device: { id: 'device' }, catalog, catalogVersion: version };
    const context = {
        state, navigator: { onLine: online }, statusReady: () => true, t: key => key,
        call: async (...args) => { calls.push(args); return responses.shift(); },
        save: (key, value) => items.set(key, JSON.stringify(value)),
        renderCatalog: () => { renders++; }, notice: () => {}
    };
    vm.runInNewContext([productionFunction('loadBootstrap', true), 'globalThis.load = loadBootstrap;'].join('\n'), context);
    return { load: context.load, state, calls, items, get renders() { return renders; } };
}

for (const legacy of [false, true]) {
    test(`QC reads ${legacy ? 'legacy message' : 'direct JSON'} payloads and sends the current generation`, async () => {
        const wrap = data => legacy ? { message: data } : data;
        const calls = [];
        const api = createApi(async (url, options) => {
            if (url.endsWith('data_epoch')) return response(wrap({ generation: 'current' }));
            calls.push({ url, options });
            return response(wrap({ accepted_local_event_ids: ['pending'] }));
        });
        const data = await api.call('sync_events', { id: 'device', events: [] });
        assert.deepEqual(data.accepted_local_event_ids, ['pending']);
        assert.equal(calls.length, 1);
        assert.equal(calls[0].options.headers['X-Factory-Data-Epoch'], 'current');
        assert.equal(JSON.parse(calls[0].options.body).id, 'device');
        assert.equal(api.reloads, 0);
    });
}

test('QC direct data epoch fences writes before an obsolete queue can reach the API', async () => {
    let writes = 0;
    const api = createApi(async url => {
        if (url.endsWith('data_epoch')) return response({ generation: 'new' });
        writes++;
        return response({});
    });
    await assert.rejects(api.call('sync_events', { id: 'device' }), /error.network/);
    assert.equal(writes, 0);
    assert.equal(api.reloads, 1);
    assert.equal(api.items.get('factory.qc.v1.data_epoch'), 'new');
});

test('QC bootstrap GET encodes the cached catalog version in its query', async () => {
    const calls = [];
    const api = createApi(async (url, options) => {
        if (url.endsWith('data_epoch')) return response({ generation: 'current' });
        calls.push({ url, options });
        return response({ unchanged: true });
    });
    await api.call('bootstrap', { id: 'device', catalog_version: 'version/one' }, 'GET');
    assert.equal(calls[0].url, '/api/method/factory_management.api.bootstrap?id=device&catalog_version=version%2Fone');
    assert.equal(calls[0].options.body, undefined);
});

test('QC bootstrap saves a full catalog and its version for offline use', async () => {
    const catalog = { products: [{ id: 'product-1' }], product_variants: [{ product_id: 'product-1' }] };
    const loader = createBootstrapLoader({ responses: [{ catalog, catalog_version: 'version-1' }] });
    await loader.load();
    assert.equal(loader.calls.length, 1);
    assert.equal(loader.calls[0][0], 'bootstrap');
    assert.equal(loader.calls[0][1].id, 'device');
    assert.equal(Object.keys(loader.calls[0][1]).length, 1);
    assert.equal(loader.state.catalog, catalog);
    assert.equal(loader.state.catalogVersion, 'version-1');
    assert.equal(loader.items.get('catalog'), JSON.stringify(catalog));
    assert.equal(loader.items.get('catalog_version'), JSON.stringify('version-1'));
    assert.equal(loader.renders, 1);
});

test('QC bootstrap keeps its cached catalog when the server reports it unchanged', async () => {
    const catalog = { products: [{ id: 'product-1' }] };
    const loader = createBootstrapLoader({ catalog, version: 'version-1', responses: [
        { unchanged: true, catalog_version: 'version-1' }
    ] });
    await loader.load();
    assert.equal(loader.calls.length, 1);
    assert.equal(loader.calls[0][1].id, 'device');
    assert.equal(loader.calls[0][1].catalog_version, 'version-1');
    assert.equal(Object.keys(loader.calls[0][1]).length, 2);
    assert.equal(loader.state.catalog, catalog);
    assert.equal(loader.renders, 0);
    assert.equal(loader.items.size, 0);
});

test('QC bootstrap replaces a stale catalog and version', async () => {
    const oldCatalog = { products: [{ id: 'old' }] };
    const newCatalog = { products: [{ id: 'new' }] };
    const loader = createBootstrapLoader({ catalog: oldCatalog, version: 'version-1', responses: [
        { catalog: newCatalog, catalog_version: 'version-2' }
    ] });
    await loader.load();
    assert.equal(loader.calls[0][1].id, 'device');
    assert.equal(loader.calls[0][1].catalog_version, 'version-1');
    assert.equal(loader.state.catalog, newCatalog);
    assert.equal(loader.state.catalogVersion, 'version-2');
    assert.equal(loader.items.get('catalog'), JSON.stringify(newCatalog));
    assert.equal(loader.items.get('catalog_version'), JSON.stringify('version-2'));
    assert.equal(loader.renders, 1);
});

test('QC bootstrap retries without a version if an unchanged response has no local catalog', async () => {
    const catalog = { products: [{ id: 'product-1' }] };
    const loader = createBootstrapLoader({ responses: [
        { unchanged: true, catalog_version: 'version-1' },
        { catalog, catalog_version: 'version-1' }
    ] });
    await loader.load();
    assert.equal(loader.calls.length, 2);
    assert.equal(loader.calls[0][1].id, 'device');
    assert.equal(loader.calls[1][1].id, 'device');
    assert.equal(Object.keys(loader.calls[0][1]).length, 1);
    assert.equal(Object.keys(loader.calls[1][1]).length, 1);
    assert.equal(loader.state.catalog, catalog);
    assert.equal(loader.renders, 1);
});

test('QC keeps the cached catalog without making a request while offline', async () => {
    const catalog = { products: [{ id: 'product-1' }] };
    const loader = createBootstrapLoader({ catalog, version: 'version-1', online: false });
    await loader.load();
    assert.equal(loader.calls.length, 0);
    assert.equal(loader.state.catalog, catalog);
    assert.equal(loader.state.catalogVersion, 'version-1');
    assert.equal(loader.renders, 0);
});

test('QC checks for a service worker update on secure online startup', async () => {
    const registrations = [];
    let updates = 0;
    const context = {
        navigator: {
            onLine: true,
            serviceWorker: { register: async (...args) => {
                registrations.push(args);
                return { update: async () => { updates++; } };
            } }
        },
        window: { isSecureContext: true }
    };
    vm.runInNewContext([
        productionFunction('updateQcServiceWorker'),
        'globalThis.update = updateQcServiceWorker;'
    ].join('\n'), context);
    await context.update();
    assert.equal(registrations[0][0], '/qc-sw.js');
    assert.equal(registrations[0][1].scope, '/');
    assert.equal(registrations[0][1].updateViaCache, 'none');
    assert.equal(updates, 1);
    assert.doesNotMatch(productionFunction('updateQcServiceWorker'), /location\.reload/);
});

test('QC preserves localized authorization errors after the success contract change', async () => {
    const api = createApi(async url => url.endsWith('data_epoch') ? response({ generation: 'current' }) : response({
        _server_messages: JSON.stringify([JSON.stringify({ message: 'Thiết bị chưa được duyệt' })])
    }, 403));
    await assert.rejects(api.call('check_device', { id: 'device' }), error =>
        error.status === 403 && error.message === 'Thiết bị chưa được duyệt');
    assert.equal(api.items.has('factory.qc.v1.queue'), true);
});
