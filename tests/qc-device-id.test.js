const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const source = readFileSync(path.join(__dirname, '..', 'factory_management', 'public', 'js', 'qc.js'), 'utf8');
const start = source.indexOf('function migrateStoredDeviceId() {');
assert.notEqual(start, -1);
let depth = 0;
let end = start;
for (let index = source.indexOf('{', start); index < source.length; index++) {
    if (source[index] === '{') depth++;
    if (source[index] === '}' && --depth === 0) { end = index + 1; break; }
}
const migration = source.slice(start, end);

function runMigration(profile, legacyId, queue) {
    const items = new Map([
        ['factory.qc.v1.device', JSON.stringify(profile)],
        ['factory.qc.v1.queue', JSON.stringify(queue)],
        ['factory.qc.v1.token', 'old-token'],
        ['qc_device_id', legacyId],
    ]);
    const localStorage = {
        getItem: key => items.get(key) ?? null,
        setItem: (key, value) => items.set(key, value),
        removeItem: key => items.delete(key),
    };
    const state = { device: profile, queue, identityConflict: false };
    const save = (key, value) => localStorage.setItem('factory.qc.v1.' + key, JSON.stringify(value));
    vm.runInNewContext(`${migration}; migrateStoredDeviceId();`,
        { state, localStorage, save, oldDevice: () => legacyId ? { id: legacyId } : null,
            PREFIX: 'factory.qc.v1.' });
    return { state, items };
}

test('saved QC device ID moves to id while pending events stay intact', () => {
    const queue = [{ local_event_id: 'pending' }];
    const { state, items } = runMigration({ device_id: 'same', device_uid: 'old' }, 'same', queue);
    assert.equal(state.device.id, 'same');
    assert.equal(state.device.device_uid, undefined);
    assert.deepEqual(JSON.parse(items.get('factory.qc.v1.queue')), queue);
    assert.equal(items.has('factory.qc.v1.token'), false);
    assert.equal(items.has('qc_device_id'), false);
});

test('legacy QC standalone device ID becomes the canonical cached profile ID', () => {
    const { state, items } = runMigration(null, 'standalone', [{ local_event_id: 'pending' }]);
    assert.equal(state.device.id, 'standalone');
    assert.equal(JSON.parse(items.get('factory.qc.v1.device')).id, 'standalone');
    assert.equal(items.has('qc_device_id'), false);
});

test('conflicting QC IDs stop migration without touching the offline queue', () => {
    const queue = [{ local_event_id: 'pending' }];
    const { state, items } = runMigration({ id: 'first', device_id: 'second' }, 'first', queue);
    assert.equal(state.identityConflict, true);
    assert.deepEqual(JSON.parse(items.get('factory.qc.v1.queue')), queue);
    assert.equal(items.has('factory.qc.v1.token'), false);
});
