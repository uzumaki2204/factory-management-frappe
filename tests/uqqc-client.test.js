const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');
const { randomUUID } = require('node:crypto');

const clientSource = readFileSync(path.join(__dirname, '..', 'factory_management', 'public', 'uqqc', 'client.js'), 'utf8');
const prefix = 'fm-uqqc-client:v1:';
const dateKey = new Date().toISOString().slice(0, 10);
const scope = { lineId: 'line', productId: 'product', colorId: 'color', sizeId: 'size', marketId: 'market' };

// Exercise the production closures without starting polling, fullscreen or service-worker registration.
const testSource = clientSource.replace('    await window.UQQCI18nReady;', '').replace('    void start();', `
    globalThis.client = { state, elements, keys, detailScopeKey, hydrateDetailSnapshots, detailRows,
        renderDetail, openDetailPanel, openDefectPositionPicker, renderDefectPositionPicker,
        clearClientCache, syncQueue, saveDetailSnapshot, requestJson, loadCatalog,
        queuePass, queueDefect, activateDevice, syncServerDay };`);
assert.notEqual(testSource, clientSource);

class Storage {
    getItem(key) { return Object.hasOwn(this, key) ? this[key] : null; }
    setItem(key, value) { this[key] = String(value); }
    removeItem(key) { delete this[key]; }
}

class Element {
    constructor(tag = 'div') {
        this.tag = tag;
        this.children = [];
        this.className = '';
        this.textContent = '';
        this.dataset = {};
        this.attributes = {};
        this.handlers = {};
        this.style = { setProperty() {}, removeProperty() {} };
        this.classList = {
            contains: name => this.className.split(' ').includes(name),
            add: (...names) => names.forEach(name => this.classList.toggle(name, true)),
            remove: (...names) => names.forEach(name => this.classList.toggle(name, false)),
            toggle: (name, enabled = !this.classList.contains(name)) => {
                const names = new Set(this.className.split(' ').filter(Boolean));
                if (enabled) names.add(name); else names.delete(name);
                this.className = [...names].join(' ');
                return enabled;
            }
        };
    }
    setAttribute(key, value) { this.attributes[key] = String(value); }
    append(...elements) { elements.forEach(el => {
        if (el.tag === 'fragment') this.append(...el.children);
        else { el.parent = this; this.children.push(el); }
    }); }
    appendChild(el) { this.append(el); return el; }
    replaceChildren(...elements) { this.children = []; this.append(...elements); }
    addEventListener(type, handler) { (this.handlers[type] ||= []).push(handler); }
    click() { (this.handlers.click || []).forEach(handler => handler({ target: this, stopPropagation() {}, preventDefault() {} })); }
    focus() { this.focused = true; }
    closest(selector) {
        let node = this;
        while (node) {
            if (selector.startsWith('.') && selector.slice(1).split('.').every(name => node.classList.contains(name)))
                return node;
            node = node.parent;
        }
        return null;
    }
    pause() {}
    querySelectorAll(selector) {
        const matches = selector.split(',').map(value => value.trim());
        return this.children.flatMap(child => [
            ...(matches.some(value => value.startsWith('.') && value.slice(1).split('.').every(name => child.classList.contains(name))) ? [child] : []),
            ...child.querySelectorAll(selector)
        ]);
    }
    querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
}

function response(data) { return { ok: true, status: 200, json: async () => data }; }
function snapshot(scopes = []) { return { serverDateKey: dateKey, serverNowUtc: new Date().toISOString(), serverUtcOffsetMinutes: 0, scopes }; }
function deferred() { let resolve; const promise = new Promise(r => { resolve = r; }); return { promise, resolve }; }
async function flushRequests() { for (let index = 0; index < 6; index++) await Promise.resolve(); }

function createClient(fetch = async () => { throw new Error('offline'); }, localStorage = new Storage(), generation = '', legacyEpoch = false) {
    const nodes = new Map();
    const document = {
        documentElement: new Element(),
        getElementById(id) {
            if (!nodes.has(id)) nodes.set(id, new Element());
            return nodes.get(id);
        },
        createElement: tag => new Element(tag),
        createDocumentFragment: () => new Element('fragment')
    };
    let reloads = 0;
    const window = {
        UQQCI18n: { t: key => key, apply() {} },
        setTimeout: () => 1, clearTimeout() {}, clearInterval() {}, requestAnimationFrame: () => 1, cancelAnimationFrame() {},
        confirm: () => true,
        location: { href: 'http://localhost/uqqc', reload() { reloads++; } }
    };
    const context = { document, window, localStorage, sessionStorage: new Storage(),
        navigator: { onLine: true }, fetch: (url, options) =>
            url === '/api/method/factory_management.api.data_epoch'
                ? Promise.resolve(response(legacyEpoch ? { message: { generation } } : { generation })) : fetch(url, options),
        crypto: { randomUUID, getRandomValues: array => require('node:crypto').randomFillSync(array) }, URL, console };
    vm.runInNewContext(testSource, context);
    const { client } = context;
    client.state.device = { id: 'device', status: 'Approved', isActive: true };
    client.state.catalog = {
        serverDateKey: dateKey, serverUtcOffsetMinutes: 0, products: [{ id: 'product', code: '317H019A', customerId: 'customer' }],
        lines: [{ id: 'line', code: '307' }], customers: [{ id: 'customer', code: 'UNIQLO' }], productVariants: [{ ...scope }],
        defects: [], defectPositions: [{ id: 'front', name: 'Thân trước', positionGroupId: 'body' }, { id: 'back', name: 'Thân sau', positionGroupId: 'body' }],
        defectPositionGroups: [{ id: 'body', name: 'Thân' }]
    };
    client.state.scope = { ...scope };
    client.state.detailSnapshots = { deviceId: 'device', serverDateKey: dateKey, scopes: {} };
    return { ...client, localStorage, navigator: context.navigator, get reloads() { return reloads; } };
}

function cacheScope(client, values = { pass: 185, rework: 0, defectNo: 1, defects: { defect: 1 } }, selection = scope) {
    client.saveDetailSnapshot(selection, { ...values, serverDateKey: dateKey });
}

test('legacy enveloped API and data epoch remain readable during upgrades', async () => {
    const storage = new Storage();
    storage.setItem(prefix + 'data-epoch', 'current');
    const client = createClient(async () => response({ message: { ready: true } }), storage, 'current', true);
    assert.equal((await client.requestJson('/api/method/uqqc-bootstrap', { method: 'GET' })).ready, true);
    assert.equal(client.reloads, 0);
});

test('a malformed success response cannot acknowledge the durable offline queue', async () => {
    const client = createClient(async () => response(null));
    client.state.queue = [{ localEventId: 'pending' }];
    await assert.rejects(client.requestJson('/api/method/uqqc-inspections-sync', { method: 'POST', body: '{}' }));
    assert.equal(client.state.queue.length, 1);
});

test('position star persists independently without choosing a position, closing popup or queuing an event', () => {
    const client = createClient();
    client.openDefectPositionPicker('defect');
    client.elements.positionGrid.querySelectorAll('.uqqc-position-favorite-button')
        .find(button => button.dataset.positionId === 'front').click();
    assert.equal(client.state.positionFavorites.has('front'), true);
    assert.equal(client.state.activeDefectId, 'defect');
    assert.equal(client.elements.positionPanel.classList.contains('open'), true);
    assert.equal(client.state.queue.length, 0);
    assert.equal(client.state.activePiece, null);
    assert.deepEqual(JSON.parse(client.localStorage.getItem(client.keys.positionFavorites)), ['front']);
    assert.equal(client.localStorage.getItem(client.keys.favorites), null);
    assert.equal(createClient(undefined, client.localStorage).state.positionFavorites.has('front'), true);
    const favoriteFilter = client.elements.positionFilters.children[1];
    assert.equal(favoriteFilter.textContent, 'positionFavorites (1)');
    favoriteFilter.click();
    assert.equal(client.elements.positionGrid.children.length, 1);
    client.elements.positionGrid.querySelector('.uqqc-position-favorite-button').click();
    assert.equal(client.state.positionFavorites.size, 0);
    assert.equal(client.elements.positionGrid.children[0].textContent, 'noFavoritePositions');
    assert.equal(client.elements.positionFilters.querySelector('.uqqc-is-active').focused, true);
    assert.equal(client.elements.positionPanel.classList.contains('open'), true);
    const reloaded = createClient(undefined, client.localStorage);
    assert.equal(reloaded.state.positionFavorites.size, 0);
});

test('position content button chooses the position and queues exactly one defect', async () => {
    const client = createClient();
    client.navigator.onLine = false;
    client.openDefectPositionPicker('defect');
    client.elements.positionGrid.querySelectorAll('.uqqc-position-card')
        .find(card => card.querySelector('.uqqc-position-favorite-button').dataset.positionId === 'front')
        .querySelector('.uqqc-defect-name').click();
    assert.equal(client.elements.positionPanel.classList.contains('open'), false);
    assert.equal(client.state.queue.length, 1);
    assert.equal(client.state.queue[0].defectPositionId, 'front');
    assert.equal(client.state.queue[0].defectId, 'defect');
    assert.equal(client.state.positionFavorites.size, 0);
    await client.syncQueue();
});

test('fresh browser restores all five-dimensional scopes and groups product/line as 186 inspected', async () => {
    const requests = [];
    const client = createClient(async (url, options) => {
        requests.push({ url, body: JSON.parse(options.body) });
        return response(snapshot([
            { ...scope, pass: 50, rework: 0, defectNo: 1, defects: { defect: 1 } },
            { ...scope, colorId: 'color2', sizeId: 'size2', marketId: 'market2', pass: 135, rework: 2, defectNo: 0, defects: {} }
        ]));
    });
    await client.hydrateDetailSnapshots();
    assert.deepEqual(requests, [{ url: '/api/method/uqqc-inspections-detail-snapshot', body: { id: 'device' } }]);
    assert.equal(Object.keys(client.state.detailSnapshots.scopes).length, 2);
    assert.equal(client.detailRows().length, 1);
    assert.equal(client.detailRows()[0].inspected, 186);
    assert.equal(client.detailRows()[0].pass, 185);
    assert.equal(client.detailRows()[0].rework, 2);
    assert.equal(client.state.detailHydrated, true);
    assert.equal(JSON.parse(client.localStorage.getItem(client.keys.detailSnapshots)).deviceId, 'device');
});

test('detail popup includes products with pass or rework and omits products with no activity', async () => {
    const client = createClient(async () => response(snapshot([
        { ...scope, pass: 5, rework: 0, defectNo: 1, defects: { defect: 1 } },
        { ...scope, productId: 'pass-rework-product', pass: 3, rework: 2, defectNo: 0, defects: {} },
        { ...scope, productId: 'pass-only-product', pass: 4, rework: 0, defectNo: 0, defects: {} },
        { ...scope, productId: 'rework-only-product', pass: 0, rework: 2, defectNo: 0, defects: {} },
        { ...scope, productId: 'empty-product', pass: 0, rework: 0, defectNo: 0, defects: {} }
    ])));
    client.state.catalog.products.push(
        { id: 'pass-rework-product', code: '317H020A' },
        { id: 'pass-only-product', code: '317H021A' },
        { id: 'rework-only-product', code: '317H022A' },
        { id: 'empty-product', code: '317H023A' }
    );

    await client.hydrateDetailSnapshots();
    client.renderDetail();

    const rows = client.detailRows();
    assert.equal(rows.length, 4);
    assert.equal(rows.some(row => row.productId === 'empty-product'), false);
    assert.equal(client.elements.detailBody.children.length, 4);

    const passAndRework = client.elements.detailBody.children.find(row => row.children[0].textContent === '317H020A');
    assert.deepEqual(passAndRework.children.slice(2, 6).map(cell => cell.textContent), ['3', '3', '2', '0']);
    const totals = client.elements.detailFoot.children[0].children;
    assert.deepEqual(totals.slice(1).map(cell => cell.textContent), ['13', '12', '4', '1', '7.7%']);
});

test('offline restore retains local detail, while no-cache failure displays localized error and retry', async () => {
    const cached = createClient();
    cacheScope(cached);
    assert.equal(await cached.hydrateDetailSnapshots(), null);
    cached.renderDetail();
    assert.equal(cached.detailRows()[0].inspected, 186);
    assert.equal(cached.elements.detailStatus.textContent, 'detailRestoreFailed');
    assert.equal(cached.elements.detailRetry.hidden, false);
    const empty = createClient();
    await empty.hydrateDetailSnapshots();
    empty.renderDetail();
    assert.equal(empty.elements.detailBody.children[0].children[0].textContent, 'detailRestoreUnavailable');
    assert.equal(empty.elements.detailFoot.hidden, true);
});

test('day rollover discards previous-day local detail and retains server-day metadata', async () => {
    const nextDate = '2099-01-02';
    const client = createClient(async () => response({ ...snapshot(), serverDateKey: nextDate }));
    cacheScope(client);
    await client.hydrateDetailSnapshots();
    assert.equal(client.state.catalog.serverDateKey, nextDate);
    assert.equal(client.state.detailSnapshots.serverDateKey, nextDate);
    assert.equal(Object.keys(client.state.detailSnapshots.scopes).length, 0);
});

test('a scope refresh completed during hydration is not overwritten by the older response', async () => {
    const gate = deferred();
    const client = createClient(async () => { await gate.promise; return response(snapshot([{ ...scope, pass: 1, defectNo: 1 }])); });
    const restoring = client.hydrateDetailSnapshots();
    cacheScope(client);
    gate.resolve();
    await restoring;
    assert.equal(client.detailRows()[0].inspected, 186);
});

test('restore response for a replaced device cannot pollute its local cache', async () => {
    const gate = deferred();
    const client = createClient(async () => { await gate.promise; return response(snapshot([{ ...scope, pass: 185, defectNo: 1 }])); });
    const restoring = client.hydrateDetailSnapshots();
    client.state.device = { ...client.state.device, id: 'other-device' };
    gate.resolve();
    assert.equal(await restoring, null);
    assert.equal(client.state.detailHydrated, false);
    assert.equal(Object.keys(client.state.detailSnapshots.scopes).length, 0);
});

test('clear cache refuses offline pending events and leaves local data intact', async () => {
    const client = createClient();
    client.state.queue = [{ ...scope, localEventId: 'pending', serverDateKey: dateKey, eventKind: 'pass' }];
    client.localStorage.setItem(client.keys.queue, JSON.stringify(client.state.queue));
    client.navigator.onLine = false;
    await client.clearClientCache();
    assert.equal(client.reloads, 0);
    assert.equal(client.state.queue.length, 1);
    assert.notEqual(client.localStorage.getItem(client.keys.queue), null);
    assert.equal(client.elements.toast.textContent, 'clearCachePending');
    assert.equal(client.state.clearingCache, false);
});

test('clear cache refuses an offline active piece even after its first defect was accepted', async () => {
    const client = createClient();
    cacheScope(client);
    client.state.activePiece = { scope, serverDateKey: dateKey, defectPieceId: 'piece', decisionPending: true };
    client.navigator.onLine = false;
    await client.clearClientCache();
    assert.equal(client.reloads, 0);
    assert.equal(client.state.activePiece.defectPieceId, 'piece');
    assert.equal(client.detailRows()[0].inspected, 186);
    assert.equal(client.elements.toast.textContent, 'clearCachePending');
});

test('clear cache refuses when online sync fails or makes no progress', async () => {
    const client = createClient(async () => response({ acceptedLocalEventIds: [] }));
    client.state.queue = [{ ...scope, localEventId: 'pending', serverDateKey: dateKey, eventKind: 'pass' }];
    await client.clearClientCache();
    assert.equal(client.reloads, 0);
    assert.equal(client.state.queue.length, 1);
    assert.equal(client.elements.toast.textContent, 'clearCachePending');
});

test('clear cache refuses unavailable or insufficient server detail rather than trusting an HTTP success', async () => {
    for (const fetch of [undefined, async () => response(snapshot([{ ...scope, pass: 184, defectNo: 1, defects: { defect: 1 } }]))]) {
        const client = createClient(fetch);
        cacheScope(client);
        await client.clearClientCache();
        assert.equal(client.reloads, 0);
        assert.notEqual(client.localStorage.getItem(client.keys.detailSnapshots), null);
        assert.equal(client.elements.toast.textContent, 'clearCacheUnverified');
    }
});

test('clear cache verifies the original local detail even when an in-flight restore returns less data', async () => {
    const gate = deferred();
    const client = createClient(async () => { await gate.promise; return response(snapshot()); });
    cacheScope(client);
    const restoring = client.hydrateDetailSnapshots();
    const clearing = client.clearClientCache();
    gate.resolve();
    await Promise.all([restoring, clearing]);
    assert.equal(client.reloads, 0);
    assert.equal(client.elements.toast.textContent, 'clearCacheUnverified');
    assert.equal(client.detailRows()[0].inspected, 186);
    assert.equal(JSON.parse(client.localStorage.getItem(client.keys.detailSnapshots)).scopes[client.detailScopeKey(scope)].snapshot.pass, 185);
});

test('successful sync and server verification allow clearing only UQQC keys before reload', async () => {
    const requests = [];
    const data = { ...scope, pass: 1, rework: 0, defectNo: 1, defects: { defect: 1 } };
    const client = createClient(async url => {
        requests.push(url);
        if (url.endsWith('-sync')) return response({ acceptedLocalEventIds: ['pending'] });
        if (url.endsWith('uqqc-inspections-snapshot')) return response({ ...data, serverDateKey: dateKey });
        return response(snapshot([data]));
    });
    cacheScope(client, { pass: 0, rework: 0, defectNo: 1, defects: { defect: 1 } });
    client.state.queue = [{ ...scope, localEventId: 'pending', serverDateKey: dateKey, eventKind: 'pass' }];
    client.localStorage.setItem('another-app:data', 'keep');
    client.localStorage.setItem(client.keys.positionFavorites, '["front"]');
    await client.clearClientCache();
    assert.equal(client.reloads, 1);
    assert.equal(client.state.queue.length, 0);
    assert.equal(client.localStorage.getItem('another-app:data'), 'keep');
    assert.equal(Object.keys(client.localStorage).some(key => key.startsWith(prefix)), false);
    assert.equal(requests[0], '/api/method/uqqc-inspections-sync');
    assert.equal(requests.at(-1), '/api/method/uqqc-inspections-detail-snapshot');
});

test('clear cache drains every 200-event batch before verification instead of discarding the remainder', async () => {
    const batches = [];
    let accepted = 0;
    const client = createClient(async (url, options) => {
        const data = { ...scope, pass: accepted, rework: 0, defectNo: 1, defects: { defect: 1 }, serverDateKey: dateKey };
        if (url.endsWith('-sync')) {
            const events = JSON.parse(options.body).passEvents;
            batches.push(events.length);
            accepted += events.length;
            return response({ acceptedLocalEventIds: events.map(event => event.localEventId) });
        }
        return response(url.endsWith('uqqc-inspections-snapshot') ? data : snapshot([data]));
    });
    cacheScope(client, { pass: 0, rework: 0, defectNo: 1, defects: { defect: 1 } });
    client.state.queue = Array.from({ length: 201 }, (_, index) => ({
        ...scope, localEventId: `pending-${index}`, serverDateKey: dateKey, eventKind: 'pass'
    }));
    await client.clearClientCache();
    assert.deepEqual(batches, [200, 1]);
    assert.equal(accepted, 201);
    assert.equal(client.state.queue.length, 0);
    assert.equal(client.reloads, 1);
});

test('hydration waits for in-flight sync and concurrent sync callers share one batch', async () => {
    const gate = deferred();
    const requests = [];
    const client = createClient(async url => {
        requests.push(url);
        if (url.endsWith('-sync')) { await gate.promise; return response({ acceptedLocalEventIds: ['pending'] }); }
        if (url.endsWith('uqqc-inspections-snapshot')) return response({ ...scope, pass: 185, defectNo: 1, serverDateKey: dateKey });
        return response(snapshot([{ ...scope, pass: 185, defectNo: 1 }]));
    });
    client.state.queue = [{ ...scope, localEventId: 'pending', serverDateKey: dateKey, eventKind: 'pass' }];
    const syncing = client.syncQueue();
    const secondSync = client.syncQueue();
    const restoring = client.hydrateDetailSnapshots();
    await flushRequests();
    assert.deepEqual(requests, ['/api/method/uqqc-inspections-sync']);
    gate.resolve();
    await Promise.all([syncing, secondSync, restoring]);
    assert.equal(client.state.queue.length, 0);
    assert.equal(client.detailRows()[0].inspected, 186);
    assert.equal(requests.filter(url => url.endsWith('-sync')).length, 1);
});

test('sync started during restore waits and cannot double count pending events in the restored snapshot', async () => {
    const gate = deferred();
    const requests = [];
    const client = createClient(async url => {
        requests.push(url);
        if (url.endsWith('-detail-snapshot')) { await gate.promise; return response(snapshot([{ ...scope, pass: 184, defectNo: 1 }])); }
        if (url.endsWith('-sync')) return response({ acceptedLocalEventIds: ['pending'] });
        return response({ ...scope, pass: 185, defectNo: 1, serverDateKey: dateKey });
    });
    const restoring = client.hydrateDetailSnapshots();
    client.state.queue = [{ ...scope, localEventId: 'pending', serverDateKey: dateKey, eventKind: 'pass' }];
    const syncing = client.syncQueue();
    await flushRequests();
    assert.deepEqual(requests, ['/api/method/uqqc-inspections-detail-snapshot']);
    gate.resolve();
    await Promise.all([restoring, syncing]);
    assert.equal(client.state.queue.length, 0);
    assert.equal(client.detailRows()[0].inspected, 186);
});


test('Frappe requests use the device record ID without a token and read direct JSON', async () => {
    const calls = [];
    const client = createClient(async (url, options) => { calls.push({ url, options }); return response({ ready: true }); });
    assert.equal((await client.requestJson('/api/method/uqqc-bootstrap', { method: 'GET' })).ready, true);
    await client.requestJson('/api/method/uqqc-device-check', { method: 'POST', body: '{}' });
    assert.equal(calls[0].options.headers['X-UQQC-Token'], undefined);
    assert.equal(calls[1].options.headers['X-UQQC-Token'], undefined);
    assert.equal(calls[0].url, '/api/method/uqqc-bootstrap?id=device');
});

test('unchanged bootstrap keeps the complete catalog and sends its version on refresh', async () => {
    const calls = [];
    const client = createClient(async url => {
        calls.push(url);
        return response({ catalogVersion: 'version-1', unchanged: true,
            serverDateKey: dateKey, serverNowUtc: new Date().toISOString(), serverUtcOffsetMinutes: 0 });
    });
    client.state.catalog.catalogVersion = 'version-1';
    const originalProducts = client.state.catalog.products;
    await client.loadCatalog(true);
    assert.deepEqual(calls, ['/api/method/uqqc-bootstrap?catalogVersion=version-1&id=device']);
    assert.equal(client.state.catalog.products, originalProducts);
    assert.equal(client.state.catalog.catalogVersion, 'version-1');
    assert.equal(JSON.parse(client.localStorage.getItem(client.keys.catalog)).products.length, 1);
});

test('unchanged bootstrap advances the server day without discarding catalog options', async () => {
    const tomorrow = new Date(Date.now() + 86400000);
    tomorrow.setUTCHours(12, 0, 0, 0);
    const nextDateKey = tomorrow.toISOString().slice(0, 10);
    const client = createClient(async () => response({ catalogVersion: 'version-1', unchanged: true,
        serverDateKey: nextDateKey, serverNowUtc: tomorrow.toISOString(), serverUtcOffsetMinutes: 0 }));
    client.state.catalog.catalogVersion = 'version-1';
    await client.loadCatalog(true);
    assert.equal(client.state.catalog.serverDateKey, nextDateKey);
    assert.equal(client.state.catalog.products.length, 1);
    assert.equal(client.state.detailSnapshots.serverDateKey, nextDateKey);
});

test('new data generation clears stale UQQC queue and migrates the saved ID', async () => {
    const storage = new Storage();
    storage.setItem(prefix + 'device-id', 'device');
    storage.setItem(prefix + 'offline-queue', JSON.stringify([{ localEventId: 'old' }]));
    storage.setItem(prefix + 'device-token:device', 'old-token');
    let writes = 0;
    const client = createClient(async () => { writes++; return response({}); }, storage, 'new');
    await assert.rejects(client.requestJson('/api/method/uqqc-inspections-sync',
        { method: 'POST', body: '{}' }));
    assert.equal(writes, 0);
    assert.equal(storage.getItem(prefix + 'offline-queue'), null);
    assert.equal(storage.getItem(prefix + 'device-token:device'), null);
    assert.equal(storage.getItem(prefix + 'id'), 'device');
    assert.equal(storage.getItem(prefix + 'device-id'), null);
    assert.equal(storage.getItem(prefix + 'data-epoch'), 'new');
    assert.equal(client.reloads, 1);
});

test('concurrent requests cannot send an old UQQC queue after a generation change', async () => {
    let writes = 0;
    const storage = new Storage();
    storage.setItem(prefix + 'device-id', 'device');
    storage.setItem(prefix + 'offline-queue', JSON.stringify([{ localEventId: 'old' }]));
    const client = createClient(async () => { writes++; return response({}); }, storage, 'new');
    const requests = await Promise.allSettled([
        client.requestJson('/api/method/uqqc-inspections-sync', { method: 'POST', body: '{}' }),
        client.requestJson('/api/method/uqqc-inspections-sync', { method: 'POST', body: '{}' })
    ]);
    assert.equal(requests.every(result => result.status === 'rejected'), true);
    assert.equal(writes, 0);
    assert.equal(storage.getItem(prefix + 'offline-queue'), null);
});

test('storage failure cannot queue a pass or leave an unfinished defective piece', () => {
    const client = createClient();
    client.localStorage.setItem = () => { throw new Error('quota'); };
    client.queuePass();
    assert.equal(client.state.queue.length, 0);
    client.queueDefect('defect', 'front');
    assert.equal(client.state.queue.length, 0);
    assert.equal(client.state.activePiece, null);
    assert.equal(client.elements.toast.textContent, 'storageUnavailable');
});

test('device switch preserves pending events and never registers another device', async () => {
    let requests = 0;
    const client = createClient(async () => { requests++; return response({}); });
    client.state.queue = [{ localEventId: 'pending' }];
    client.elements.manualDeviceId.value = randomUUID();
    await client.activateDevice();
    assert.equal(requests, 0);
    assert.equal(client.state.queue.length, 1);
    assert.equal(client.elements.deviceMessage.textContent, 'deviceSwitchPending');
});

test('the day watchdog is safe before device activation and catalog loading', () => {
    const client = createClient();
    client.state.device = null;
    client.state.catalog = { lines: [] };
    assert.equal(client.syncServerDay(), false);
});

test('conflicting saved IDs preserve the offline queue and block API writes', async () => {
    const storage = new Storage();
    storage.setItem(prefix + 'id', 'first');
    storage.setItem(prefix + 'device-id', 'second');
    storage.setItem(prefix + 'offline-queue', JSON.stringify([{ localEventId: 'pending' }]));
    let requests = 0;
    const client = createClient(async () => { requests++; return response({}); }, storage);
    await assert.rejects(client.requestJson('/api/method/uqqc-inspections-sync',
        { method: 'POST', body: JSON.stringify({ id: 'first' }) }), /deviceIdentityConflict/);
    assert.equal(requests, 0);
    assert.equal(client.state.queue.length, 1);
    assert.equal(storage.getItem(prefix + 'id'), 'first');
    assert.equal(storage.getItem(prefix + 'device-id'), 'second');
});

test('an authorization failure disables new input while retaining pending events', async () => {
    const client = createClient(async () => ({ ok: false, status: 403, json: async () => ({}) }));
    client.state.queue = [{ localEventId: 'pending' }];
    await assert.rejects(client.requestJson('/api/method/uqqc-inspections-sync', { method: 'POST', body: '{}' }));
    assert.equal(client.state.device.isActive, false);
    assert.equal(client.state.queue.length, 1);
    assert.equal(client.elements.devicePanel.classList.contains('open'), true);
});

test('a database conflict retains the durable queue and retry acknowledges it without sync warnings', async () => {
    let attempts = 0;
    const client = createClient(async url => {
        if (url.endsWith('-sync')) {
            if (++attempts === 1) return { ok: false, status: 409, json: async () => ({ exc_type: 'UQQCSyncRetryError' }) };
            return response({ acceptedLocalEventIds: ['pending'] });
        }
        return response({ ...scope, pass: 1, defects: {}, serverDateKey: dateKey });
    });
    client.state.queue = [{ ...scope, localEventId: 'pending', serverDateKey: dateKey, eventKind: 'pass' }];
    client.localStorage.setItem(client.keys.queue, JSON.stringify(client.state.queue));
    await client.syncQueue();
    assert.equal(client.state.queue.length, 1);
    assert.equal(JSON.parse(client.localStorage.getItem(client.keys.queue)).length, 1);
    assert.equal(client.state.syncErrors.length, 0);
    assert.equal(client.state.apiReachable, true);
    await client.syncQueue();
    assert.equal(client.state.queue.length, 0);
    assert.equal(attempts, 2);
});
