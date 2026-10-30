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

test('QC preserves localized authorization errors after the success contract change', async () => {
    const api = createApi(async url => url.endsWith('data_epoch') ? response({ generation: 'current' }) : response({
        _server_messages: JSON.stringify([JSON.stringify({ message: 'Thiết bị chưa được duyệt' })])
    }, 403));
    await assert.rejects(api.call('check_device', { id: 'device' }), error =>
        error.status === 403 && error.message === 'Thiết bị chưa được duyệt');
    assert.equal(api.items.has('factory.qc.v1.queue'), true);
});
