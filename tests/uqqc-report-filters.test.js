const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const filterSource = readFileSync(
  path.join(__dirname, '..', 'factory_management', 'public', 'js', 'uqqc_report_filters.js'),
  'utf8'
);

class FakeElement {
  constructor(tag = 'div') {
    this.tag = tag;
    this.children = [];
    this.className = '';
    this.textContent = '';
    this.value = '';
    this.title = '';
    this.placeholder = '';
    this.type = '';
    this.hidden = false;
    this.disabled = false;
    this.checked = false;
    this.focused = false;
    this.dataset = {};
    this.attributes = {};
    this.handlers = {};
    this.parent = null;
    this.classList = {
      contains: (name) => this.className.split(' ').filter(Boolean).includes(name),
      add: (...names) => names.forEach((name) => this.classList.toggle(name, true)),
      remove: (...names) => names.forEach((name) => this.classList.toggle(name, false)),
      toggle: (name, enabled = !this.classList.contains(name)) => {
        const names = new Set(this.className.split(' ').filter(Boolean));
        if (enabled) names.add(name);
        else names.delete(name);
        this.className = [...names].join(' ');
        return enabled;
      },
    };
  }

  setAttribute(key, value) {
    this.attributes[key] = String(value);
  }

  append(...elements) {
    elements.forEach((el) => {
      el.parent = this;
      this.children.push(el);
    });
  }

  replaceChildren(...elements) {
    this.children = [];
    this.append(...elements);
  }

  addEventListener(type, handler) {
    (this.handlers[type] ||= []).push(handler);
  }

  dispatch(type, event = {}) {
    (this.handlers[type] || []).forEach((handler) => handler(event));
  }

  contains(target) {
    if (target === this) return true;
    return this.children.some((child) => child.contains(target));
  }

  getBoundingClientRect() {
    return { left: 20 };
  }

  focus() {
    this.focused = true;
  }

  querySelectorAll(selector) {
    const cls = selector.startsWith('.') ? selector.slice(1) : null;
    return this.children.flatMap((child) => [
      ...((cls ? child.classList.contains(cls) : child.tag === selector) ? [child] : []),
      ...child.querySelectorAll(selector),
    ]);
  }

  querySelector(selector) {
    return this.querySelectorAll(selector)[0] || null;
  }
}

function loadFilters({ finePointer = true } = {}) {
  const docHandlers = {};
  const document = {
    createElement: (tag) => new FakeElement(tag),
    addEventListener: (type, handler) => (docHandlers[type] ||= []).push(handler),
    dispatchEvent: (event) => (docHandlers[event.type] || []).forEach((fn) => fn(event)),
  };
  class CustomEvent {
    constructor(type, init = {}) {
      this.type = type;
      this.detail = init.detail;
    }
  }
  const window = {
    document,
    CustomEvent,
    innerWidth: 1280,
    matchMedia: () => ({ matches: finePointer }),
    __: (text, args) =>
      Array.isArray(args)
        ? text.replace(/\{(\d+)\}/g, (_, i) => (args[i] !== undefined ? args[i] : ''))
        : text,
  };
  const module = { exports: {} };
  const context = { window, globalThis: window, document, module, exports: module.exports };
  vm.runInNewContext(filterSource, context);
  return { filters: module.exports, document };
}

// Convert cross-realm vm objects to plain values for node:assert/strict comparison.
const plain = (value) => JSON.parse(JSON.stringify(value));

const sampleRows = [
  {
    qc: 'QC1',
    companyId: 'COMP-A',
    companyCode: 'A',
    companyName: 'Alpha Co',
    productId: 'P1',
    productCode: '317H019A',
    productName: 'Shirt',
    deviceId: 'D1',
    deviceName: '001QC1',
    marketId: 'JP',
    marketCode: 'JP',
    marketName: 'Japan',
    colorId: 'BLK',
    colorCode: 'BLK',
    colorName: 'Black',
    sizeId: 'M',
    sizeCode: 'M',
    sizeLabel: 'M',
  },
  {
    qc: 'QC1',
    companyId: 'COMP-B',
    companyCode: 'B',
    companyName: 'Beta Co',
    productId: 'P1',
    productCode: '317H019A',
    productName: 'Shirt',
    deviceId: 'D3',
    deviceName: '003QC1',
    marketId: 'JP',
    marketCode: 'JP',
    marketName: 'Japan',
    colorId: 'BLK',
    colorCode: 'BLK',
    colorName: 'Black',
    sizeId: 'M',
    sizeCode: 'M',
    sizeLabel: 'M',
  },
  {
    qc: 'QC2',
    companyId: 'COMP-B',
    companyCode: 'B',
    companyName: 'Beta Co',
    productId: 'P2',
    productCode: '317H020B',
    productName: '317H020B',
    deviceId: 'D2',
    deviceName: '002QC2',
    marketId: 'US',
    marketCode: 'US',
    marketName: 'United States',
    colorId: 'WHT',
    colorCode: 'WHT',
    colorName: 'White',
    sizeId: 'L',
    sizeCode: 'L',
    sizeLabel: 'L',
  },
];

test('fieldsForTab splits summary and device controls', () => {
  const { filters } = loadFilters();
  assert.deepEqual(
    plain(filters.fieldsForTab('summary').map((s) => s.fieldname)),
    ['qc', 'company', 'product']
  );
  assert.deepEqual(
    plain(filters.fieldsForTab('device').map((s) => s.fieldname)),
    ['qc', 'company', 'product', 'device', 'market', 'color', 'size']
  );
});

test('getOptions formats primary/code labels cleanly without duplicating equal strings', () => {
  const { filters } = loadFilters();
  const productSpec = filters.FIELD_SPECS.find((s) => s.fieldname === 'product');
  const opts = plain(filters.getOptions(sampleRows, productSpec));
  assert.deepEqual(opts, [
    { value: 'P1', label: '317H019A (Shirt)' },
    { value: 'P2', label: '317H020B' },
  ]);
});

test('computeCascadingOptions preserves priorityField selection while dropping incompatible sibling choices', () => {
  const { filters } = loadFilters();
  // User switched QC to QC2 while COMP-B (compatible) and P1 (incompatible) were still selected.
  const result = plain(filters.computeCascadingOptions(
    sampleRows,
    'summary',
    { qc: ['QC2'], company: ['COMP-B'], product: ['P1'] },
    'qc'
  ));
  assert.deepEqual(result.selections.qc, ['QC2']);
  assert.deepEqual(result.selections.company, ['COMP-B']);
  assert.deepEqual(result.selections.product, []);
  assert.deepEqual(result.optionsByField.product.map((o) => o.value), ['P2']);
});

test('makeMultiControl updates trigger label, handles search threshold, and avoids focus on tablet', () => {
  const desktop = loadFilters({ finePointer: true });
  let changes = 0;
  const ctrl = desktop.filters.makeMultiControl('Product', 'product', () => {
    changes++;
  });
  const manyOptions = Array.from({ length: 6 }, (_, i) => ({ value: `P${i}`, label: `Prod ${i}` }));
  ctrl.setOptions(manyOptions);

  const trigger = ctrl.wrapper.querySelector('.uqqc-rpt-multiselect-trigger');
  const valueSpan = ctrl.wrapper.querySelector('.uqqc-rpt-multiselect-value');
  const search = ctrl.wrapper.querySelector('.uqqc-rpt-multiselect-search');
  assert.equal(valueSpan.textContent, 'All');
  assert.equal(search.hidden, false);

  trigger.dispatch('click');
  assert.equal(ctrl.wrapper.classList.contains('is-open'), true);
  assert.equal(search.focused, true);

  // Select two checkboxes
  const checks = ctrl.wrapper.querySelectorAll('input').filter((el) => el.type === 'checkbox');
  checks[0].checked = true;
  checks[0].dispatch('change');
  assert.equal(valueSpan.textContent, 'Prod 0');
  checks[1].checked = true;
  checks[1].dispatch('change');
  assert.equal(valueSpan.textContent, '2 selected');
  assert.deepEqual(plain(ctrl.getValues()), ['P0', 'P1']);

  // Closing resets search text
  search.value = 'Prod 3';
  search.dispatch('input');
  trigger.dispatch('click');
  assert.equal(search.value, '');

  // Clear button resets selection
  ctrl.wrapper.querySelector('.uqqc-rpt-multiselect-clear').dispatch('click');
  assert.deepEqual(plain(ctrl.getValues()), []);
  assert.equal(valueSpan.textContent, 'All');
  assert.equal(changes, 3);

  // Tablet mode must not auto-focus search input
  const tablet = loadFilters({ finePointer: false });
  const tabCtrl = tablet.filters.makeMultiControl('Company', 'company', () => {});
  tabCtrl.setOptions(manyOptions);
  tabCtrl.wrapper.querySelector('.uqqc-rpt-multiselect-trigger').dispatch('click');
  assert.equal(tabCtrl.wrapper.querySelector('.uqqc-rpt-multiselect-search').focused, false);
});

test('opening one dropdown closes other open dropdowns via uqqc-filter-open event', () => {
  const { filters } = loadFilters();
  const c1 = filters.makeMultiControl('QC', 'qc', () => {});
  const c2 = filters.makeMultiControl('Company', 'company', () => {});
  c1.setOptions([{ value: 'QC1', label: 'QC1' }]);
  c2.setOptions([{ value: 'COMP-A', label: 'Alpha Co' }]);

  c1.wrapper.querySelector('.uqqc-rpt-multiselect-trigger').dispatch('click');
  assert.equal(c1.wrapper.classList.contains('is-open'), true);

  c2.wrapper.querySelector('.uqqc-rpt-multiselect-trigger').dispatch('click');
  assert.equal(c1.wrapper.classList.contains('is-open'), false);
  assert.equal(c2.wrapper.classList.contains('is-open'), true);
});
