(() => {
  'use strict';
  const PREFIX = 'factory.qc.v1.';
  const PAGE_LOCK_CODE = '1234';
  const urlRoot = '/api/method/factory_management.api.';
  const epochUrl = '/api/method/factory_management.api.data_epoch';
  let epochGeneration = localStorage.getItem(PREFIX + 'data_epoch') || '';
  let epochReloading = false;
  const $ = id => document.getElementById(id);
  let initialUnlockResolver = null;
  let autoFullscreenActivated = false;
  let autoFullscreenPending = false;
  const read = (key, fallback) => {
    try {
      const value = localStorage.getItem(PREFIX + key);
      return value === null ? fallback : JSON.parse(value);
    } catch (_) { return fallback; }
  };
  const save = (key, value) => {
    localStorage.setItem(PREFIX + key, JSON.stringify(value));
  };
  const state = {
    language: null,
    device: read('device', null),
    token: read('token', null),
    catalog: read('catalog', null),
    queue: read('queue', []),
    favorites: read('favorites', []),
    favoritesDirty: read('favorites_dirty', false),
    snapshots: read('snapshots', {}),
    detail: read('detail', null),
    syncing: false,
    checking: false,
    pageUnlocked: false,
    pollingBlocked: false,
    camera: null,
    scanTimer: null,
    groupFilter: 'all',
    arrange: false,
    arrangeSourceId: null,
    horizontal: read('horizontal', false),
    defectOrder: read('defect_order', []),
    recentProducts: read('recent_products', []),
    recentLines: read('recent_lines', []),
    productCustomerFilter: '',
    productSeasonFilter: '',
    lineFactoryFilter: '',
    lastSync: read('last_sync', '')
  };

  function t(key) {
    return (state.language && (state.language.vi[key] || state.language.en[key] || state.language.vi['ui.no_data'])) || '';
  }
  let noticeTimer = null;
  function hideMessage() {
    clearTimeout(noticeTimer);
    noticeTimer = null;
    $('qc-toast').hidden = true;
    $('qc-toast').dataset.messageKey = '';
  }
  function showMessage(value, danger = false, key = '') {
    const node = $('qc-toast');
    const dialog = [...document.querySelectorAll('dialog[open]')].pop();
    (dialog || document.body).appendChild(node);
    const surface = $('qc-toast-surface');
    surface.className = 'toast show mx-auto ' + (danger ? 'border-danger text-danger' : 'border-info text-info');
    surface.setAttribute('role', danger ? 'alert' : 'status');
    surface.setAttribute('aria-live', danger ? 'assertive' : 'polite');
    $('qc-toast-body').textContent = value;
    node.dataset.messageKey = key;
    clearTimeout(noticeTimer);
    node.hidden = false;
    noticeTimer = setTimeout(hideMessage, danger ? 6000 : 4000);
  }
  function notice(key, danger = false) {
    showMessage(t(key), danger, key);
  }
  function showPageLock() {
    if (state.pageUnlocked) return;
    document.body.classList.add('qc-page-locked');
    if (document.visibilityState !== 'visible' || !document.hasFocus()) return;
    const dialog = $('page-lock-dialog');
    if (!dialog.open) dialog.showModal();
    $('page-lock-code').focus();
  }
  function lockPage() {
    const wasUnlocked = state.pageUnlocked;
    if (wasUnlocked) {
      state.pageUnlocked = false;
      document.body.classList.add('qc-page-locked');
      document.querySelectorAll('dialog[open]').forEach(dialog => {
        if (dialog.id !== 'page-lock-dialog') dialog.close();
      });
      stopCamera();
      hideMessage();
    }
    $('page-lock-code').value = '';
    $('page-lock-error').hidden = true;
    showPageLock();
  }
  function unlockPage(event) {
    event.preventDefault();
    const input = $('page-lock-code');
    if (input.value !== PAGE_LOCK_CODE) {
      $('page-lock-error').hidden = false;
      input.select();
      return;
    }
    state.pageUnlocked = true;
    document.body.classList.remove('qc-page-locked');
    $('page-lock-dialog').close();
    input.value = '';
    $('page-lock-error').hidden = true;
    if (initialUnlockResolver) {
      const resume = initialUnlockResolver;
      initialUnlockResolver = null;
      resume();
      return;
    }
    renderStatus();
    if (statusReady() && navigator.onLine) check();
    else if (!statusReady()) openDevice();
  }
  function openDevice() {
    const dialog = $('device-dialog');
    if (!dialog.open) dialog.showModal();
    (state.device?.device_id ? $('device-name') : $('device-id')).focus();
  }
  function closeDevice() {
    if ($('device-dialog').open) $('device-dialog').close();
  }
  async function loadLanguage() {
    try {
      const response = await fetch('/assets/factory_management/js/qc-i18n.json?v=44');
      if (response.ok) {
        state.language = await response.json();
        save('language', state.language);
      }
    } catch (_) {}
    state.language = state.language || read('language', {vi: {}, en: {}});
    document.title = t('ui.title');
    document.querySelectorAll('[data-i18n]').forEach(node => {
      node.textContent = t(node.dataset.i18n);
    });
    document.querySelectorAll('[data-i18n-aria]').forEach(node => {
      node.setAttribute('aria-label', t(node.dataset.i18nAria));
      node.title = t(node.dataset.i18nAria);
    });
  }
  function randomToken() {
    const bytes = crypto.getRandomValues(new Uint8Array(32));
    return Array.from(bytes, byte => byte.toString(16).padStart(2, '0')).join('');
  }
  function randomUuid() {
    const bytes = crypto.getRandomValues(new Uint8Array(16));
    bytes[6] = (bytes[6] & 15) | 64;
    bytes[8] = (bytes[8] & 63) | 128;
    const hex = Array.from(bytes, byte => byte.toString(16).padStart(2, '0')).join('');
    return [hex.slice(0, 8), hex.slice(8, 12), hex.slice(12, 16),
      hex.slice(16, 20), hex.slice(20)].join('-');
  }
  function oldDevice() {
    const id = (localStorage.getItem('qc_device_id') || '').trim();
    if (!id) return null;
    let metadata = {};
    try { metadata = JSON.parse(localStorage.getItem('fm.client.device') || '{}'); } catch (_) {}
    return {
      device_id: id,
      device_uid: metadata.deviceUid || id,
      device_name: metadata.deviceName || '',
      status: 'Pending',
      pairing_status: 'Unpaired',
      is_active: false
    };
  }
  function persistDevice() {
    save('device', state.device);
    save('token', state.token);
  }
  function deviceActivated() {
    return state.device?.status === 'Approved' &&
      state.device.pairing_status === 'Paired' && Boolean(state.device.is_active);
  }
  function statusReady() {
    return deviceActivated() && state.token;
  }
  function updateNetwork() {
    const node = $('network');
    const label = t(navigator.onLine ? 'ui.online' : 'ui.offline');
    node.setAttribute('aria-label', label);
    node.title = label;
    node.className = 'btn btn-sm p-1 ' + (navigator.onLine ? 'btn-success' : 'btn-danger');
  }
  function renderToolbar() {
    const scroll = $('scroll-direction');
    const scrollLabel = t(state.horizontal ? 'ui.scroll_vertical' : 'ui.scroll_horizontal');
    scroll.setAttribute('aria-label', scrollLabel);
    scroll.title = scrollLabel;
    scroll.setAttribute('aria-pressed', String(state.horizontal));
    scroll.className = 'btn btn-sm p-1 ' + (state.horizontal ? 'btn-primary' : 'btn-default');
    scroll.querySelector('path').setAttribute('d', state.horizontal ? 'M3 9h18M3 15h18' : 'M9 3v18M15 3v18');
    const full = $('fullscreen');
    const active = Boolean(document.fullscreenElement);
    const fullLabel = t(active ? 'ui.exit_fullscreen' : 'ui.enter_fullscreen');
    full.setAttribute('aria-label', fullLabel);
    full.title = fullLabel;
    full.setAttribute('aria-pressed', String(active));
    full.className = 'btn btn-sm p-1 ' + (active ? 'btn-primary' : 'btn-default');
    full.querySelector('path').setAttribute('d', active ? 'M9 3v6H3M15 21v-6h6M3 9l7-7M21 15l-7 7' : 'M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7');
    $('open-settings').title = t('ui.settings');
    const arrange = $('arrange-toggle');
    arrange.setAttribute('aria-pressed', String(state.arrange));
    arrange.className = 'btn btn-sm text-nowrap flex-shrink-0 ' + (state.arrange ? 'btn-primary' : 'btn-default');
    $('arrange-label').textContent = t(state.arrange ? 'ui.arrange_on' : 'ui.arrange_off');
  }
  async function toggleFullscreen() {
    autoFullscreenActivated = true;
    try {
      if (document.fullscreenElement) await document.exitFullscreen();
      else await document.documentElement.requestFullscreen();
    } catch (_) { notice('error.fullscreen', true); }
    renderToolbar();
  }
  function isFullscreenButtonEvent(event) {
    const button = $('fullscreen');
    if (!button || !event) return false;
    if (typeof event.composedPath === 'function') return event.composedPath().includes(button);
    return event.target instanceof Node && button.contains(event.target);
  }
  function autoEnterFullscreen(event) {
    if (!event?.isTrusted || isFullscreenButtonEvent(event) || document.hidden || autoFullscreenActivated || autoFullscreenPending) return;
    if (document.fullscreenElement) {
      autoFullscreenActivated = true;
      return;
    }
    const request = document.documentElement.requestFullscreen;
    if (typeof request !== 'function') return;
    autoFullscreenPending = true;
    try {
      Promise.resolve(request.call(document.documentElement)).then(() => {
        autoFullscreenActivated = true;
        autoFullscreenPending = false;
        renderToolbar();
      }).catch(() => { autoFullscreenPending = false; });
    } catch (_) {
      autoFullscreenPending = false;
    }
  }
  function renderStatus() {
    const name = String(state.device?.device_name || '').trim();
    const title = name || t('ui.title');
    $('page-title').textContent = title;
    document.title = title;
    $('device-id').value = state.device?.device_id || '';
    const registered = Boolean(state.device?.device_id);
    $('device-id').readOnly = registered;
    $('device-id').setAttribute('aria-readonly', String(registered));
    $('scan').disabled = registered;
    $('clear-device-cache-panel').hidden = !registered;
    $('device-name').value = state.device?.device_name || '';
    const nameLocked = deviceActivated();
    $('device-name').readOnly = nameLocked;
    $('device-name').setAttribute('aria-readonly', String(nameLocked));
    $('device-status').textContent = state.device?.status ? t('status.' + state.device.status) : t('ui.no_data');
    $('pairing-status').textContent = !state.device ? t('ui.register_prompt')
      : statusReady() ? t('ui.ready')
      : state.device.status === 'Approved' ? t('ui.waiting_pairing') : t('ui.waiting_approval');
    $('entry-panel').hidden = !statusReady();
    $('pending-total').textContent = String(state.queue.length);
    updateNetwork();
  }
  async function call(method, data = {}, verb = 'POST') {
    const requestEpoch = await ensureDataEpoch();
    if (epochReloading) throw new Error(t('error.network'));
    const params = new URLSearchParams();
    if (verb === 'GET') {
      Object.entries(data).forEach(([key, value]) => {
        if (value !== null && value !== undefined && value !== '') params.set(key, value);
      });
    }
    const endpoint = urlRoot + method + (verb === 'GET' ? '?' + params.toString() : '');
    let response;
    try {
      response = await fetch(endpoint, {
        method: verb,
        headers: {'Content-Type': 'application/json', 'X-QC-Token': state.token || '',
          'X-Factory-Data-Epoch': requestEpoch},
        credentials: 'omit',
        body: verb === 'GET' ? undefined : JSON.stringify(data)
      });
    } catch (_) {
      throw new Error(t('error.network'));
    }
    let result;
    try {
      result = await response.json();
    } catch (_) {
      throw new Error(t('error.network'));
    }
    if (!response.ok) {
      let serverMessage = '';
      try {
        serverMessage = JSON.parse(result._server_messages || '[]')
          .map(item => {
            try { return (typeof item === 'string' ? JSON.parse(item) : item).message; }
            catch (_) { return ''; }
          }).find(Boolean) || '';
      } catch (_) {}
      const error = new Error(serverMessage || (typeof result.message === 'string' ? result.message : '') ||
        t('error.network'));
      error.status = response.status;
      throw error;
    }
    return result.message;
  }
  async function ensureDataEpoch() {
    if (epochReloading) throw new Error(t('error.network'));
    if (!navigator.onLine) return epochGeneration;
    let response;
    try { response = await fetch(epochUrl, {cache: 'no-store', credentials: 'omit'}); }
    catch (_) { throw new Error(t('error.network')); }
    if (!response.ok) throw new Error(t('error.network'));
    const generation = String((await response.json()).message?.generation || '');
    if (epochReloading) throw new Error(t('error.network'));
    if (!generation || generation === epochGeneration) return epochGeneration;
    epochReloading = true;
    const deviceId = state.device?.device_id || localStorage.getItem('qc_device_id') || '';
    Object.keys(localStorage).filter(key => key.startsWith(PREFIX)).forEach(key => localStorage.removeItem(key));
    localStorage.removeItem('fm.client.device');
    if (deviceId) localStorage.setItem('qc_device_id', deviceId);
    localStorage.setItem(PREFIX + 'data_epoch', generation);
    epochGeneration = generation;
    if ('caches' in window) {
      try {
        const cacheKeys = await caches.keys();
        await Promise.all(cacheKeys.filter(key => key.startsWith('factory-qc-')).map(key => caches.delete(key)));
      } catch (_) { /* API writes remain fenced while the page reloads. */ }
    }
    window.location.reload();
    throw new Error(t('error.network'));
  }
  async function clearDeviceCache() {
    if (state.syncing) { notice('error.cache_busy', true); return; }
    if (!navigator.onLine) { notice('error.cache_offline', true); return; }
    if (state.queue.length || state.favoritesDirty) {
      await sync();
      if (state.queue.length || state.favoritesDirty) {
        showMessage(t('error.cache_pending').replace('{count}', String(state.queue.length)), true);
        return;
      }
    }
    try {
      if ('caches' in window) {
        for (const key of await caches.keys()) {
          if (key.startsWith('factory-qc-')) await caches.delete(key);
        }
      }
      if ('serviceWorker' in navigator) {
        const registration = await navigator.serviceWorker.getRegistration('/qc');
        if (registration?.active && new URL(registration.active.scriptURL).pathname === '/qc-sw.js')
          await registration.unregister();
      }
      for (const key of Object.keys(localStorage)) {
        if (key.startsWith(PREFIX)) localStorage.removeItem(key);
      }
      localStorage.removeItem('qc_device_id');
      localStorage.removeItem('fm.client.device');
      try { sessionStorage.setItem(PREFIX + 'cache_cleared', '1'); } catch (_) {}
      window.location.reload();
    } catch (_) { notice('error.storage', true); }
  }
  async function register() {
    const raw = $('device-id').value.trim();
    const registeredId = String(state.device?.device_id || '').trim();
    if (registeredId && raw && registeredId.toLowerCase() !== raw.toLowerCase()) {
      notice('error.device_id_locked', true); return;
    }
    const id = registeredId || raw || randomUuid();
    if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(id)) {
      notice('error.input', true); return;
    }
    const old = registeredId ? state.device : null;
    const uid = String(old?.device_uid || '').trim() || id;
    if (!old || typeof state.token !== 'string' || state.token.trim().length < 32) state.token = randomToken();
    try {
      const result = await call('register_device', {
        device_id: id, device_uid: uid, token: state.token,
        device_name: $('device-name').value.trim(),
        browser_name: navigator.userAgent.slice(0, 120),
        operating_system: navigator.platform || ''
      });
      state.device = result.device;
      state.pollingBlocked = false;
      persistDevice();
      renderStatus();
      notice(statusReady() ? 'ok.paired' : 'ok.register');
    } catch (error) {
      if (state.pageUnlocked) {
        openDevice();
        showMessage(error.message || t('error.network'), true);
      }
      return;
    }
    if (statusReady()) {
      closeDevice();
      try { await readyData(); } catch (_) { notice('error.network', true); }
    }
  }
  async function check(silent = false) {
    if (!state.pageUnlocked || state.checking || !state.device?.device_id || !state.token || !navigator.onLine) return;
    state.checking = true;
    if (!silent) state.pollingBlocked = false;
    try {
      state.device = await call('check_device', {device_id: state.device.device_id});
      state.pollingBlocked = false;
      persistDevice();
      renderStatus();
    } catch (error) {
      if (error.status === 403 || error.status === 404) state.pollingBlocked = true;
      if (!silent && state.pageUnlocked) {
        openDevice();
        showMessage(error.message || t('error.auth'), true);
      }
      return;
    } finally {
      state.checking = false;
    }
    if (!state.pageUnlocked) return;
    if (statusReady()) {
      closeDevice();
      try { await readyData(); } catch (_) { notice('error.network', true); }
    }
  }
  function makeOptions(id, rows, selected = '') {
    const node = $(id);
    const old = selected || node.value;
    node.replaceChildren();
    const choose = document.createElement('option');
    choose.value = '';
    choose.textContent = t('ui.choose');
    node.appendChild(choose);
    rows.forEach(row => {
      const option = document.createElement('option');
      option.value = row.id;
      option.textContent = row.code ? row.code + ' · ' + row.name : row.name;
      node.appendChild(option);
    });
    if (rows.some(row => row.id === old)) node.value = old;
  }
  function selectedProduct() { return $('product').value; }
  function scopeKey() {
    return [state.device?.device_id || '', selectedProduct(), $('line').value,
      $('color').value, $('size').value, localDate(new Date())].join('|');
  }
  function localDate(date) {
    return date.toLocaleDateString('sv-SE', {timeZone: 'Asia/Ho_Chi_Minh'});
  }
  function optionLabel(row) {
    return [row.code, row.name].filter(Boolean).join(' · ') || t('ui.no_data');
  }
  function lineLabel(row) {
    if (!row.code || !row.name || row.code === row.name)
      return row.code || row.name || t('ui.no_data');
    const template = t('ui.line_code_name');
    return template.includes('{code}') && template.includes('{name}')
      ? template.replace('{code}', row.code).replace('{name}', row.name)
      : optionLabel(row);
  }
  function labelFor(kind, id, fallback) {
    const row = (state.catalog?.[kind] || []).find(item => item.id === id);
    return row ? (kind === 'lines' ? lineLabel(row) : optionLabel(row)) : t(fallback);
  }
  function renderSelectionButtons() {
    const product = (state.catalog?.products || []).find(item => item.id === $('product').value);
    $('product-picker').textContent = product ? (product.code || product.name) : t('ui.choose_product');
    $('line-picker').textContent = labelFor('lines', $('line').value, 'ui.choose_line');
    if (product && $('line').value && $('qc-toast').dataset.messageKey === 'error.selection') hideMessage();
  }
  function renderCatalog() {
    const c = state.catalog;
    if (!c) return;
    makeOptions('product', c.products || []);
    const lines = (c.lines || []).filter(x => !state.device?.company || x.company_id === state.device.company);
    makeOptions('line', lines, $('line').value || state.device?.line || '');
    const variants = (c.product_variants || []).filter(x => x.product_id === selectedProduct());
    $('variant-details').hidden = !variants.length;
    const colors = variants.length ? (c.colors || []).filter(x => variants.some(v => v.color_id === x.id)) : (c.colors || []);
    const sizes = variants.length ? (c.sizes || []).filter(x => variants.some(v => v.size_id === x.id)) : (c.sizes || []);
    makeOptions('color', colors);
    makeOptions('size', sizes);
    renderSelectionButtons();
    renderPickers();
    renderDefects();
  }
  function filterLabel(row) {
    return row.name || row.code || t('ui.no_data');
  }
  function compareAlphabetically(left, right) {
    return String(left || '').localeCompare(String(right || ''), document.documentElement.lang || undefined,
      {numeric: true, sensitivity: 'base'});
  }
  function sortAlphabetically(rows, getLabel) {
    return [...rows].sort((a, b) =>
      compareAlphabetically(getLabel(a), getLabel(b)) ||
      compareAlphabetically(a.code, b.code) ||
      compareAlphabetically(a.name, b.name) ||
      compareAlphabetically(a.id, b.id));
  }
  function renderPickerFilters(target, options, selected, onSelect, labelKey) {
    const container = $(target);
    const previousScroll = container.scrollLeft;
    container.replaceChildren();
    container.setAttribute('aria-label', t(labelKey));
    const fragment = document.createDocumentFragment();
    const pinned = options.filter(option => option.id === '' || option.id === '__recent__');
    const alphabetic = sortAlphabetically(
      options.filter(option => option.id !== '' && option.id !== '__recent__'), option => option.label);
    [...pinned, ...alphabetic].forEach(option => {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'btn btn-sm py-2 px-2 mr-1 mb-1 text-nowrap flex-shrink-0 ' +
        (selected === option.id ? 'btn-primary' : 'btn-default');
      button.textContent = option.label;
      button.title = option.label;
      button.setAttribute('aria-pressed', String(selected === option.id));
      button.addEventListener('click', () => {
        onSelect(option.id);
        renderPickers();
      });
      fragment.appendChild(button);
    });
    container.appendChild(fragment);
    container.scrollLeft = previousScroll;
  }
  function renderPickers() {
    const c = state.catalog;
    if (!c) return;
    const allProducts = c.products || [];
    const customerIds = new Set(allProducts.map(row => row.customer_id).filter(Boolean));
    const seasonIds = new Set(allProducts.map(row => row.season_id).filter(Boolean));
    const customers = (c.customers || []).filter(row => !customerIds.size || customerIds.has(row.id));
    const seasons = (c.seasons || []).filter(row => !seasonIds.size || seasonIds.has(row.id));
    if (state.productCustomerFilter && !customers.some(row => row.id === state.productCustomerFilter))
      state.productCustomerFilter = '';
    if (state.productSeasonFilter && state.productSeasonFilter !== '__recent__' &&
        !seasons.some(row => row.id === state.productSeasonFilter))
      state.productSeasonFilter = '';
    renderPickerFilters('product-customers',
      [{id: '', label: t('ui.all_customers')}, ...customers.map(row => ({id: row.id, label: filterLabel(row)}))],
      state.productCustomerFilter, id => { state.productCustomerFilter = id; }, 'ui.customer');
    renderPickerFilters('product-seasons',
      [{id: '__recent__', label: t('ui.recent')}, {id: '', label: t('ui.all_seasons')},
        ...seasons.map(row => ({id: row.id, label: filterLabel(row)}))],
      state.productSeasonFilter, id => { state.productSeasonFilter = id; }, 'ui.season');
    const products = sortAlphabetically(allProducts.filter(row =>
      (!state.productCustomerFilter || row.customer_id === state.productCustomerFilter) &&
      (state.productSeasonFilter === '__recent__'
        ? state.recentProducts.includes(row.id)
        : !state.productSeasonFilter || row.season_id === state.productSeasonFilter)),
    row => row.code || row.name);
    renderPickerGrid('product-grid', products, 'product', 'ui.no_products');

    const allLines = (c.lines || []).filter(row =>
      !state.device?.company || row.company_id === state.device.company);
    const factoryIds = new Set(allLines.map(row => row.factory_id).filter(Boolean));
    const factories = (c.factories || []).filter(row =>
      (!state.device?.company || row.company_id === state.device.company) &&
      (!factoryIds.size || factoryIds.has(row.id)));
    if (state.lineFactoryFilter && state.lineFactoryFilter !== '__recent__' &&
        !factories.some(row => row.id === state.lineFactoryFilter))
      state.lineFactoryFilter = '';
    renderPickerFilters('line-factories',
      [{id: '__recent__', label: t('ui.recent')}, {id: '', label: t('ui.all_factories')},
        ...factories.map(row => ({id: row.id, label: filterLabel(row)}))],
      state.lineFactoryFilter, id => { state.lineFactoryFilter = id; }, 'ui.factory');
    const lines = sortAlphabetically(allLines.filter(row =>
      state.lineFactoryFilter === '__recent__'
        ? state.recentLines.includes(row.id)
        : !state.lineFactoryFilter || row.factory_id === state.lineFactoryFilter), lineLabel);
    renderPickerGrid('line-grid', lines, 'line', 'ui.no_lines');
  }
  function renderPickerGrid(target, rows, kind, emptyKey) {
    const grid = $(target);
    grid.replaceChildren();
    grid.className = 'row';
    if (!rows.length) {
      const empty = document.createElement('p');
      empty.className = 'text-muted p-3';
      empty.textContent = t(emptyKey);
      grid.appendChild(empty);
      return;
    }
    const fragment = document.createDocumentFragment();
    sortAlphabetically(rows, row => kind === 'line' ? lineLabel(row) : row.code || row.name).forEach(row => {
      const col = document.createElement('div');
      col.className = 'col-4 col-sm-3 col-md-2 px-1 mb-2 d-flex';
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'btn btn-sm w-100 py-2 px-1 text-nowrap ' +
        ($(kind).value === row.id ? 'btn-primary' : 'btn-default');
      button.textContent = kind === 'line' ? lineLabel(row) : row.code || row.name || t('ui.no_data');
      button.title = kind === 'line' ? lineLabel(row) : optionLabel(row);
      button.addEventListener('click', () => {
        const recentKey = kind === 'product' ? 'recentProducts' : 'recentLines';
        const storageKey = kind === 'product' ? 'recent_products' : 'recent_lines';
        state[recentKey] = [row.id, ...state[recentKey].filter(id => id !== row.id)].slice(0, 24);
        save(storageKey, state[recentKey]);
        $(kind).value = row.id;
        $(kind).dispatchEvent(new Event('change'));
        $(kind + '-dialog').close();
      });
      col.appendChild(button);
      fragment.appendChild(col);
    });
    grid.appendChild(fragment);
  }
  function sortedDefects(rows) {
    const positions = new Map(state.defectOrder.map((id, index) => [id, index]));
    return [...rows].sort((a, b) =>
      (positions.has(a.id) ? positions.get(a.id) : 999999) -
      (positions.has(b.id) ? positions.get(b.id) : 999999) ||
      compareAlphabetically(a.code, b.code) ||
      compareAlphabetically(a.name, b.name));
  }
  function renderDefectsKeepingPosition() {
    const scrollTop = window.scrollY;
    const grid = $('defect-grid');
    const gridScrollTop = grid.scrollTop;
    const scrollLeft = grid.scrollLeft;
    renderDefects();
    grid.scrollTop = gridScrollTop;
    grid.scrollLeft = scrollLeft;
    window.scrollTo(0, scrollTop);
  }
  function moveDefect(id, direction) {
    const all = sortedDefects(state.catalog?.defects || []).map(x => x.id);
    const index = all.indexOf(id);
    const next = index + direction;
    if (index < 0 || next < 0 || next >= all.length) return;
    [all[index], all[next]] = [all[next], all[index]];
    state.defectOrder = all;
    save('defect_order', all);
    renderDefectsKeepingPosition();
  }
  function reorderDefect(sourceId, targetId) {
    const all = sortedDefects(state.catalog?.defects || []).map(x => x.id);
    const source = all.indexOf(sourceId), target = all.indexOf(targetId);
    if (source < 0 || target < 0 || source === target) {
      state.arrangeSourceId = null;
      renderDefectsKeepingPosition();
      return;
    }
    all.splice(source, 1);
    const targetAfterRemoval = all.indexOf(targetId);
    all.splice(targetAfterRemoval + (source < target ? 1 : 0), 0, sourceId);
    state.defectOrder = all;
    state.arrangeSourceId = null;
    save('defect_order', all);
    renderDefectsKeepingPosition();
  }
  function pickArrange(id) {
    if (!state.arrangeSourceId) {
      state.arrangeSourceId = id;
      renderDefectsKeepingPosition();
    } else {
      reorderDefect(state.arrangeSourceId, id);
    }
  }
  function addFilter(key, label, active) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'btn btn-sm text-nowrap flex-shrink-0 ' + (active ? 'btn-primary' : 'btn-default');
    button.textContent = label;
    button.setAttribute('aria-pressed', String(active));
    button.addEventListener('click', () => { state.groupFilter = key; renderDefects(); });
    $('quick-filters').appendChild(button);
  }
  let touchArrange = null;
  let nativeArrangeDragActive = false;
  let horizontalSnapTimer = null;
  let suppressArrangeClickUntil = 0;
  function snapHorizontalGrid() {
    const grid = $('defect-grid');
    if (!state.horizontal || nativeArrangeDragActive || (touchArrange && touchArrange.active)) return;
    const pageWidth = grid.clientWidth;
    if (!pageWidth) return;
    const maxScroll = Math.max(0, grid.scrollWidth - pageWidth);
    const target = Math.max(0, Math.min(maxScroll, Math.round(grid.scrollLeft / pageWidth) * pageWidth));
    if (Math.abs(grid.scrollLeft - target) > 2) grid.scrollTo({left: target, behavior: 'smooth'});
  }
  function scheduleHorizontalGridSnap() {
    clearTimeout(horizontalSnapTimer);
    horizontalSnapTimer = setTimeout(snapHorizontalGrid, 160);
  }
  function touchCardAt(x, y) {
    const node = document.elementFromPoint(x, y);
    return node && node.closest('#defect-grid article[data-id]');
  }
  function clearTouchArrange() {
    if (!touchArrange) return;
    clearTimeout(touchArrange.timer);
    touchArrange.source.classList.remove('shadow-sm');
    touchArrange.source.removeAttribute('aria-grabbed');
    if (touchArrange.target) touchArrange.target.classList.remove('border-primary', 'bg-light');
    touchArrange = null;
    state.arrangeSourceId = null;
  }
  function touchArrangeStart(event) {
    if (event.touches.length !== 1 || event.target.closest('[data-card-action]')) return;
    const card = event.target.closest('#defect-grid article[data-id]');
    if (!card) return;
    clearTouchArrange();
    const finger = event.changedTouches[0];
    const drag = {
      identifier: finger.identifier, sourceId: card.dataset.id, source: card,
      startX: finger.clientX, startY: finger.clientY, target: null, active: false, timer: null
    };
    touchArrange = drag;
    drag.timer = setTimeout(() => {
      if (touchArrange !== drag) return;
      drag.active = true;
      state.arrangeSourceId = drag.sourceId;
      card.classList.add('border-primary', 'shadow-sm');
      card.setAttribute('aria-grabbed', 'true');
    }, 400);
  }
  function touchArrangeMove(event) {
    const drag = touchArrange;
    if (!drag) return;
    const finger = Array.from(event.touches).find(item => item.identifier === drag.identifier);
    if (!finger) return;
    if (!drag.active) {
      if (Math.hypot(finger.clientX - drag.startX, finger.clientY - drag.startY) > 10) clearTouchArrange();
      return;
    }
    event.preventDefault();
    if (drag.target) drag.target.classList.remove('border-primary', 'bg-light');
    const target = touchCardAt(finger.clientX, finger.clientY);
    drag.target = target && target.dataset.id !== drag.sourceId ? target : null;
    if (drag.target) drag.target.classList.add('border-primary', 'bg-light');
    const grid = $('defect-grid');
    if (state.horizontal) {
      const bounds = grid.getBoundingClientRect();
      if (finger.clientX > bounds.right - 48) grid.scrollLeft += 20;
      else if (finger.clientX < bounds.left + 48) grid.scrollLeft -= 20;
    } else {
      if (finger.clientY > window.innerHeight - 48) window.scrollBy(0, 20);
      else if (finger.clientY < 48) window.scrollBy(0, -20);
    }
  }
  function touchArrangeEnd(event) {
    const drag = touchArrange;
    if (!drag) return;
    const finger = Array.from(event.changedTouches).find(item => item.identifier === drag.identifier);
    if (!finger) return;
    const active = drag.active, sourceId = drag.sourceId;
    const targetId = active ? touchCardAt(finger.clientX, finger.clientY)?.dataset.id : null;
    if (active) event.preventDefault();
    clearTouchArrange();
    if (active) {
      suppressArrangeClickUntil = Date.now() + 500;
      if (targetId && targetId !== sourceId) reorderDefect(sourceId, targetId);
    }
    scheduleHorizontalGridSnap();
  }
  function touchArrangeCancel(event) {
    if (touchArrange) clearTouchArrange();
  }
  function renderDefects() {
    const c = state.catalog;
    if (!c) return;
    const all = c.defects || [];
    const groups = sortAlphabetically(
      [...new Map(all.map(x => [x.group_code || '', x.group_name || x.group_code || t('ui.other')]))]
        .map(([code, name]) => ({code, name})), group => group.name);
    if (state.groupFilter.startsWith('group:') && !groups.some(group => 'group:' + group.code === state.groupFilter)) state.groupFilter = 'all';
    $('quick-filters').replaceChildren();
    addFilter('all', t('ui.all_defects') + ' (' + all.length + ')', state.groupFilter === 'all');
    addFilter('favorite', t('ui.favorites') + ' (' + all.filter(x => state.favorites.includes(x.id)).length + ')', state.groupFilter === 'favorite');
    groups.forEach(({code, name}) =>
      addFilter('group:' + code, name + ' (' + all.filter(x => (x.group_code || '') === code).length + ')',
        state.groupFilter === 'group:' + code));
    const filtered = all.filter(item => state.groupFilter === 'all' ||
      (state.groupFilter === 'favorite' ? state.favorites.includes(item.id) :
        state.groupFilter === 'group:' + (item.group_code || '')));
    const rows = state.arrange
      ? sortedDefects(filtered)
      : sortAlphabetically(filtered, item => item.code || item.name);
    if (!state.arrange && state.groupFilter !== 'favorite') {
      const favoriteIds = new Set(state.favorites);
      rows.sort((a, b) => Number(favoriteIds.has(b.id)) - Number(favoriteIds.has(a.id)) ||
        compareAlphabetically(a.code || a.name, b.code || b.name));
    }
    const grid = $('defect-grid');
    grid.replaceChildren();
    grid.className = 'qc-defect-grid' + (state.horizontal ? ' qc-defect-grid-horizontal d-flex flex-nowrap overflow-auto' : '');
    if (!rows.length) {
      const empty = document.createElement('p');
      empty.className = 'text-muted p-2';
      empty.textContent = state.groupFilter === 'favorite' ? t('ui.no_favorites') : t('ui.no_defects');
      grid.appendChild(empty);
      return;
    }
    const workspaceWidth = grid.parentElement.clientWidth || window.innerWidth;
    const columns = Math.max(2, Math.min(10, Math.floor(workspaceWidth / 172)));
    const pageSize = columns * 5;
    const counts = currentTotals().defects;
    const fragment = document.createDocumentFragment();
    let page = null;
    let groupRow = null;
    rows.forEach((item, index) => {
      const pageOffset = state.horizontal ? index % pageSize : index;
      if (state.horizontal && pageOffset === 0) {
        page = document.createElement('div');
        page.className = 'qc-defect-page w-100 flex-shrink-0 px-3';
        fragment.appendChild(page);
      }
      if (pageOffset % columns === 0) {
        groupRow = document.createElement('div');
        groupRow.className = 'row qc-defect-row';
        if (state.horizontal) page.appendChild(groupRow);
        else fragment.appendChild(groupRow);
      }
      const col = document.createElement('div');
      col.className = 'col qc-defect-cell';
      const card = document.createElement('article');
      card.className = 'border rounded p-2 h-100 user-select-none' + (state.arrangeSourceId === item.id ? ' border-primary' : '');
      card.dataset.id = item.id;
      card.tabIndex = state.arrange ? 0 : -1;
      card.draggable = state.arrange && !window.matchMedia('(pointer: coarse)').matches;
      card.title = state.arrange ? t('ui.arrange_hint') : t('ui.defect_add');
      card.addEventListener('click', event => {
        if (event.target.closest('[data-card-action]')) return;
        if (state.arrange) pickArrange(item.id);
        else enqueue('defect', 1, item.id, 1);
      });
      card.addEventListener('keydown', event => {
        if (!state.arrange) return;
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          pickArrange(item.id);
        } else if (event.altKey && (event.key === 'ArrowLeft' || event.key === 'ArrowRight')) {
          event.preventDefault();
          moveDefect(item.id, event.key === 'ArrowLeft' ? -1 : 1);
        }
      });
      card.addEventListener('dragstart', event => {
        if (!state.arrange) { event.preventDefault(); return; }
        state.arrangeSourceId = item.id;
        nativeArrangeDragActive = true;
        event.dataTransfer.effectAllowed = 'move';
        event.dataTransfer.setData('text/plain', item.id);
      });
      card.addEventListener('dragover', event => {
        if (state.arrange) { event.preventDefault(); event.dataTransfer.dropEffect = 'move'; }
      });
      card.addEventListener('drop', event => {
        if (!state.arrange) return;
        event.preventDefault();
        reorderDefect(event.dataTransfer.getData('text/plain') || state.arrangeSourceId, item.id);
      });
      card.addEventListener('dragend', () => {
        nativeArrangeDragActive = false;
        if (state.arrangeSourceId) { state.arrangeSourceId = null; renderDefects(); }
        scheduleHorizontalGridSnap();
      });
      const top = document.createElement('div');
      top.className = 'd-flex justify-content-between align-items-center mb-1';
      const code = document.createElement('small');
      code.className = 'text-muted';
      code.textContent = (item.group_code ? item.group_code + ' - ' : '') + (item.code || '');
      const actions = document.createElement('div');
      actions.className = 'd-flex align-items-center gap-1';
      const count = document.createElement('strong');
      count.className = 'badge badge-light';
      count.dataset.defectCount = 'true';
      count.textContent = String(counts[item.id] || 0);
      const favorite = document.createElement('button');
      favorite.type = 'button';
      favorite.dataset.cardAction = 'favorite';
      favorite.className = 'btn btn-link p-0 ' + (state.favorites.includes(item.id) ? 'text-warning' : 'text-muted');
      favorite.textContent = state.favorites.includes(item.id) ? '\u2605' : '\u2606';
      favorite.setAttribute('aria-label', t('ui.favorite_toggle') + ': ' + (item.name || item.code));
      favorite.addEventListener('click', event => { event.stopPropagation(); toggleFavorite(item.id); });
      actions.append(count, favorite);
      top.append(code, actions);
      const name = document.createElement('button');
      name.type = 'button';
      name.className = 'btn p-0 w-100 text-left';
      name.setAttribute('aria-label', t(state.arrange ? 'ui.arrange_pick' : 'ui.defect_add') + ': ' + (item.name || item.code));
      const strong = document.createElement('strong');
      strong.textContent = (item.name || item.code || t('ui.no_data'))
        .toLocaleUpperCase(document.documentElement.lang || undefined);
      name.appendChild(strong);
      card.append(top, name);
      col.appendChild(card);
      groupRow.appendChild(col);
    });
    const remainder = rows.length % columns;
    if (remainder) {
      for (let i = remainder; i < columns; i++) {
        const filler = document.createElement('div');
        filler.className = 'col qc-defect-cell';
        filler.setAttribute('aria-hidden', 'true');
        groupRow.appendChild(filler);
      }
    }
    grid.appendChild(fragment);
  }
  function renderFavorites() { renderDefectsKeepingPosition(); }
  async function loadBootstrap() {
    if (!state.pageUnlocked || !navigator.onLine || !statusReady()) return;
    try {
      const result = await call('bootstrap', {device_id: state.device.device_id}, 'GET');
      state.catalog = result.catalog;
      save('catalog', state.catalog);
      renderCatalog();
    } catch (_) { if (!state.catalog) notice('error.network', true); }
  }
  async function loadFavorites() {
    if (!state.pageUnlocked || !navigator.onLine || !statusReady() || state.favoritesDirty) return;
    try {
      const result = await call('get_favorites', {device_id: state.device.device_id}, 'GET');
      state.favorites = result.defect_ids || [];
      save('favorites', state.favorites);
      renderFavorites();
    } catch (_) {}
  }
  function scopedPending() {
    const product = selectedProduct(), line = $('line').value;
    const color = $('color').value || null, size = $('size').value || null;
    return state.queue.filter(e => e.product === product && e.line === line &&
      (e.color || null) === color && (e.size || null) === size &&
      localDate(new Date(e.occurred_at)) === localDate(new Date()));
  }
  function currentTotals() {
    const snap = state.snapshots[scopeKey()] || {received: 0, defects: {}};
    let received = Number(snap.received || 0);
    const defects = {...(snap.defects || {})};
    scopedPending().forEach(event => {
      const qty = Number(event.quantity_delta || 0);
      if (event.defect) defects[event.defect] = Math.max(0, Number(defects[event.defect] || 0) + qty);
      else received = Math.max(0, received + qty);
    });
    const bad = Object.values(defects).reduce((sum, x) => sum + Number(x || 0), 0);
    return {received, defects, bad, pass: Math.max(0, received - bad)};
  }
  function updateDefectCounts(counts) {
    $('defect-grid').querySelectorAll('article[data-id]').forEach(card => {
      const badge = card.querySelector('[data-defect-count]');
      if (badge) badge.textContent = String(counts[card.dataset.id] || 0);
    });
  }
  function renderTotals() {
    const totals = currentTotals();
    $('received-total').textContent = String(totals.received);
    $('defect-total').textContent = String(totals.bad);
    $('pass-total').textContent = String(totals.pass);
    $('defect-rate').textContent = totals.received ? (100 * totals.bad / totals.received).toFixed(1) + '%' : '0.0%';
    $('pending-total').textContent = String(state.queue.length);
    $('last-sync').textContent = state.lastSync || t('ui.no_data');
    updateDefectCounts(totals.defects);
  }
  function detailRows() {
    const today = localDate(new Date());
    const cache = state.detail?.date === today ? state.detail : null;
    const received = new Map();
    const defects = new Map();
    (cache?.received || []).forEach(row => {
      received.set(JSON.stringify([row.product, row.line]), Math.max(0, Number(row.quantity || 0)));
    });
    (cache?.defects || []).forEach(row => {
      defects.set(JSON.stringify([row.product, row.line, row.defect]),
        Math.max(0, Number(row.quantity || 0)));
    });
    const synced = new Set(cache?.already_synced || []);
    state.queue.filter(event => !synced.has(event.local_event_id) &&
      localDate(new Date(event.occurred_at)) === today).sort((a, b) =>
        String(a.occurred_at).localeCompare(String(b.occurred_at))).forEach(event => {
      if (!event.product || !event.line) return;
      const quantity = Number(event.quantity_delta || 0);
      if (event.defect) {
        const key = JSON.stringify([event.product, event.line, event.defect]);
        defects.set(key, Math.max(0, Number(defects.get(key) || 0) + quantity));
      } else {
        const key = JSON.stringify([event.product, event.line]);
        received.set(key, Math.max(0, Number(received.get(key) || 0) + quantity));
      }
    });
    return [...defects].filter(([, quantity]) => quantity > 0).map(([key, quantity]) => {
      const [product, line, defect] = JSON.parse(key);
      return {product, line, defect, quantity,
        received: Number(received.get(JSON.stringify([product, line])) || 0)};
    });
  }
  function detailFilter(id, ids, label, placeholderKey) {
    const node = $(id);
    const selected = node.value;
    node.replaceChildren();
    const placeholder = document.createElement('option');
    placeholder.value = '';
    placeholder.textContent = t(placeholderKey);
    node.appendChild(placeholder);
    ids.forEach(value => {
      const option = document.createElement('option');
      option.value = value;
      option.textContent = label(value);
      node.appendChild(option);
    });
    if (ids.includes(selected)) node.value = selected;
  }
  function renderDetail() {
    const allRows = detailRows();
    const catalog = state.catalog || {};
    const products = new Map((catalog.products || []).map(row => [row.id, row]));
    const lines = new Map((catalog.lines || []).map(row => [row.id, row]));
    const defects = new Map((catalog.defects || []).map(row => [row.id, row]));
    const productLabel = id => products.get(id)?.code || products.get(id)?.name || id || t('ui.no_data');
    const lineFilterLabel = id => lines.has(id) ? lineLabel(lines.get(id)) : id || t('ui.no_data');
    const defectLabel = id => defects.has(id) ? lineLabel(defects.get(id)) : id || t('ui.no_data');
    const unique = (values, label) => [...new Set(values)].sort((a, b) =>
      label(a).localeCompare(label(b), 'vi', {numeric: true}));
    detailFilter('detail-product', unique(allRows.map(row => row.product), productLabel),
      productLabel, 'ui.choose_product');
    const product = $('detail-product').value;
    const productRows = allRows.filter(row => !product || row.product === product);
    detailFilter('detail-line', unique(productRows.map(row => row.line), lineFilterLabel),
      lineFilterLabel, 'ui.choose_line');
    const line = $('detail-line').value;
    const lineRows = productRows.filter(row => !line || row.line === line);
    detailFilter('detail-defect', unique(lineRows.map(row => row.defect), defectLabel),
      defectLabel, 'ui.choose_defect');
    const defect = $('detail-defect').value;
    const rows = lineRows.filter(row => !defect || row.defect === defect).sort((a, b) =>
      productLabel(a.product).localeCompare(productLabel(b.product), 'vi', {numeric: true}) ||
      lineFilterLabel(a.line).localeCompare(lineFilterLabel(b.line), 'vi', {numeric: true}) ||
      defectLabel(a.defect).localeCompare(defectLabel(b.defect), 'vi', {numeric: true}));
    const body = $('detail-body');
    const foot = $('detail-foot');
    body.replaceChildren();
    foot.replaceChildren();
    if (!rows.length) {
      const tr = document.createElement('tr'), td = document.createElement('td');
      td.colSpan = 7; td.textContent = t('ui.no_defects'); tr.appendChild(td); body.appendChild(tr);
      return;
    }
    const pairs = new Set();
    let receivedTotal = 0, defectTotal = 0;
    rows.forEach(row => {
      const defectRow = defects.get(row.defect);
      const lineRow = lines.get(row.line);
      const pair = JSON.stringify([row.product, row.line]);
      if (!pairs.has(pair)) { pairs.add(pair); receivedTotal += row.received; }
      defectTotal += row.quantity;
      const tr = document.createElement('tr');
      const values = [
        productLabel(row.product),
        lineRow?.name || lineRow?.code || row.line || t('ui.no_data'),
        defectRow?.group_code || t('ui.no_data'),
        defectLabel(row.defect),
        String(row.received),
        String(row.quantity),
        row.received ? (100 * row.quantity / row.received).toFixed(1) + '%' : '0.0%'
      ];
      values.forEach((value, index) => {
        const td = document.createElement('td');
        if (index >= 4) td.className = 'text-right';
        td.textContent = value;
        tr.appendChild(td);
      });
      body.appendChild(tr);
    });
    const total = document.createElement('tr');
    const title = document.createElement('th');
    title.colSpan = 4; title.textContent = t('ui.total'); total.appendChild(title);
    [String(receivedTotal), String(defectTotal),
      receivedTotal ? (100 * defectTotal / receivedTotal).toFixed(1) + '%' : '0.0%']
      .forEach(value => {
        const cell = document.createElement('th');
        cell.className = 'text-right';
        cell.textContent = value;
        total.appendChild(cell);
      });
    foot.appendChild(total);
  }
  async function loadDetail() {
    if (!state.pageUnlocked) return;
    if (navigator.onLine && statusReady()) {
      try {
        const today = localDate(new Date());
        const pendingIds = state.queue.filter(event =>
          localDate(new Date(event.occurred_at)) === today).map(event => event.local_event_id);
        const result = await call('detail_snapshot',
          {device_id: state.device.device_id, pending_ids: pendingIds});
        state.detail = {date: result.server_date_key, received: result.received || [],
          defects: result.defects || [], already_synced: result.already_synced || []};
        save('detail', state.detail);
      } catch (error) {
        if (state.pageUnlocked && (!state.detail || state.detail.date !== localDate(new Date())))
          showMessage(error.message || t('error.network'), true);
      }
    }
    renderDetail();
  }
  async function snapshot() {
    if (!state.pageUnlocked || !navigator.onLine || !statusReady() || !selectedProduct() || !$('line').value) {
      renderTotals(); return;
    }
    try {
      const key = scopeKey();
      const result = await call('snapshot', {
        device_id: state.device.device_id,
        product: selectedProduct(), line: $('line').value,
        color: $('color').value || null, size: $('size').value || null
      });
      state.snapshots[key] = result;
      save('snapshots', state.snapshots);
      renderTotals();
    } catch (_) { renderTotals(); }
  }
  function enqueue(kind, direction, defectId = null, overrideQty = null) {
    if (!state.pageUnlocked) return;
    if (!statusReady()) { notice('error.auth', true); return; }
    const product = selectedProduct(), line = $('line').value;
    const qty = overrideQty === null ? Number($('quantity').value) : Number(overrideQty);
    if (!product || !line) { notice('error.selection', true); return; }
    if (!Number.isInteger(qty) || qty <= 0) { notice('error.quantity', true); return; }
    const defect = kind === 'defect' ? defectId : null;
    if (kind === 'defect' && !defect) { notice('error.defect', true); return; }
    const event = {
      local_event_id: randomUuid(),
      event_type: kind === 'defect' ? (direction > 0 ? 'DefectAdd' : 'DefectSubtract')
        : (direction > 0 ? 'CumulativeAdd' : 'CumulativeSubtract'),
      product, line, color: $('color').value || null,
      size: $('size').value || null, defect,
      quantity_delta: direction * qty, occurred_at: new Date().toISOString()
    };
    try {
      state.queue.push(event);
      save('queue', state.queue);
      renderTotals();
      if (navigator.onLine) sync();
    } catch (_) {
      state.queue.pop();
      notice('error.storage', true);
    }
  }
  async function sync() {
    if (!state.pageUnlocked || state.syncing || !navigator.onLine || !statusReady()) return;
    state.syncing = true;
    try {
      while (state.pageUnlocked && state.queue.length) {
        const batch = state.queue.slice(0, 100);
        const result = await call('sync_events', {
          device_id: state.device.device_id, events: batch
        });
        const accepted = new Set(result.accepted_local_event_ids || []);
        if (!accepted.size) throw new Error(t('error.sync'));
        state.queue = state.queue.filter(e => !accepted.has(e.local_event_id));
        save('queue', state.queue);
      }
      if (state.pageUnlocked && state.favoritesDirty) {
        await call('replace_favorites', {
          device_id: state.device.device_id, defect_ids: state.favorites
        });
        state.favoritesDirty = false;
        save('favorites_dirty', false);
      }
      if (state.pageUnlocked) await snapshot();
      state.lastSync = new Date().toLocaleString('vi-VN');
      save('last_sync', state.lastSync);
      renderTotals();
      if ($('detail-dialog').open) await loadDetail();
    } catch (_) { if (state.pageUnlocked) notice('error.sync', true); }
    finally { state.syncing = false; }
  }
  async function toggleFavorite(id) {
    if (!state.pageUnlocked) return;
    if (!id) { notice('error.defect', true); return; }
    state.favorites = state.favorites.includes(id)
      ? state.favorites.filter(x => x !== id) : [...state.favorites, id];
    state.favoritesDirty = true;
    try {
      save('favorites', state.favorites);
      save('favorites_dirty', true);
      renderFavorites();
      if (navigator.onLine) await sync();
    } catch (_) { notice('error.storage', true); }
  }
  function qrDeviceId(raw) {
    const value = String(raw || '').trim();
    try {
      const obj = JSON.parse(value);
      if (obj.deviceId || obj.id) return String(obj.deviceId || obj.id);
    } catch (_) {}
    try {
      const link = new URL(value);
      return link.searchParams.get('deviceId') || link.searchParams.get('id') || value;
    } catch (_) { return value; }
  }
  function stopCamera() {
    if (state.scanTimer) clearInterval(state.scanTimer);
    state.scanTimer = null;
    if (state.camera) state.camera.getTracks().forEach(track => track.stop());
    state.camera = null;
    $('camera').pause();
    $('camera').srcObject = null;
    $('camera').hidden = true;
    $('scan').textContent = t('ui.scan');
  }
  async function scan() {
    if (state.device?.device_id) { notice('error.device_id_locked', true); return; }
    if (state.camera) { stopCamera(); return; }
    if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia ||
        !('BarcodeDetector' in window)) { notice('ui.camera_permission', true); return; }
    try {
      const detector = new BarcodeDetector({formats: ['qr_code']});
      const camera = await navigator.mediaDevices.getUserMedia({
        video: {facingMode: {ideal: 'environment'}}, audio: false
      });
      if (!state.pageUnlocked) {
        camera.getTracks().forEach(track => track.stop());
        return;
      }
      state.camera = camera;
      $('camera').srcObject = state.camera;
      $('camera').hidden = false;
      await $('camera').play();
      $('scan').textContent = t('ui.stop_scan');
      state.scanTimer = setInterval(async () => {
        if ($('camera').readyState < 2) return;
        try {
          const codes = await detector.detect($('camera'));
          if (!codes.length) return;
          const id = qrDeviceId(codes[0].rawValue);
          if (!/^[0-9a-f]{8}-[0-9a-f-]{27}$/i.test(id)) {
            notice('ui.invalid_qr', true); return;
          }
          $('device-id').value = id;
          stopCamera();
        } catch (_) {}
      }, 350);
    } catch (_) { stopCamera(); notice('error.camera', true); }
  }
  async function readyData() {
    if (!state.pageUnlocked) return;
    renderCatalog();
    await Promise.all([loadBootstrap(), loadFavorites()]);
    await snapshot();
    await sync();
  }
  function attach() {
    $('page-lock-form').addEventListener('submit', unlockPage);
    $('page-lock-code').addEventListener('input', () => { $('page-lock-error').hidden = true; });
    $('page-lock-dialog').addEventListener('cancel', event => event.preventDefault());
    window.addEventListener('blur', lockPage);
    window.addEventListener('focus', () => { if (!state.pageUnlocked) showPageLock(); });
    $('open-device').addEventListener('click', () => { $('settings-dialog').close(); openDevice(); });
    $('open-settings').addEventListener('click', () => $('settings-dialog').showModal());
    $('defect-grid').addEventListener('scroll', scheduleHorizontalGridSnap, {passive: true});
    $('scroll-direction').addEventListener('click', () => {
      state.horizontal = !state.horizontal;
      save('horizontal', state.horizontal);
      renderToolbar();
      renderDefects();
      renderPickers();
    });
    $('fullscreen').addEventListener('click', toggleFullscreen);
    document.addEventListener('pointerup', autoEnterFullscreen, {capture: true, passive: true});
    document.addEventListener('click', autoEnterFullscreen, {capture: true, passive: true});
    document.addEventListener('fullscreenchange', renderToolbar);
    document.querySelectorAll('[data-close]').forEach(button =>
      button.addEventListener('click', () => $(button.dataset.close).close()));
    $('close-device').addEventListener('click', closeDevice);
    $('device-dialog').addEventListener('close', stopCamera);
    $('register').addEventListener('click', register);
    $('clear-device-cache').addEventListener('click', clearDeviceCache);
    $('check').addEventListener('click', () => check());
    $('scan').addEventListener('click', scan);
    $('sync').addEventListener('click', sync);
    $('refresh').addEventListener('click', loadBootstrap);
    $('received-add').addEventListener('click', () => enqueue('received', 1));
    $('received-subtract').addEventListener('click', () => enqueue('received', -1));
    $('product-picker').addEventListener('click', () => { renderPickers(); $('product-dialog').showModal(); });
    $('line-picker').addEventListener('click', () => { renderPickers(); $('line-dialog').showModal(); });
    $('open-detail').addEventListener('click', () => {
      renderDetail();
      $('detail-dialog').showModal();
      loadDetail();
    });
    $('detail-product').addEventListener('change', () => {
      $('detail-line').value = '';
      $('detail-defect').value = '';
      renderDetail();
    });
    $('detail-line').addEventListener('change', () => {
      $('detail-defect').value = '';
      renderDetail();
    });
    $('detail-defect').addEventListener('change', renderDetail);
    $('defect-grid').addEventListener('touchstart', touchArrangeStart, {passive: true});
    document.addEventListener('touchmove', touchArrangeMove, {passive: false});
    document.addEventListener('touchend', touchArrangeEnd, {passive: false});
    document.addEventListener('touchcancel', touchArrangeCancel);
    $('defect-grid').addEventListener('contextmenu', event => {
      if (event.target.closest('article[data-id]') && !event.target.closest('[data-card-action]')) event.preventDefault();
    });
    $('defect-grid').addEventListener('click', event => {
      if (Date.now() < suppressArrangeClickUntil) { event.preventDefault(); event.stopImmediatePropagation(); }
    }, true);
    $('arrange-toggle').addEventListener('click', () => {
      clearTouchArrange();
      state.arrange = !state.arrange;
      state.arrangeSourceId = null;
      renderToolbar();
      renderDefects();
      if (state.arrange) notice('ui.arrange_hint');
    });
    [1, 2, 5, 10].forEach(value => {
      const button = document.createElement('button');
      button.type = 'button'; button.className = 'btn flex-fill px-2 py-2 btn-default';
      button.textContent = String(value);
      button.setAttribute('aria-pressed', 'false');
      button.addEventListener('click', () => {
        const current = Number.parseInt($('quantity').value, 10) || 0;
        $('quantity').value = String(Math.max(0, current) + value);
        renderQuantityPresets();
      });
      $('quantity-presets').appendChild(button);
    });
    $('quantity').addEventListener('input', renderQuantityPresets);
    renderQuantityPresets();
    $('product').addEventListener('change', () => { renderCatalog(); snapshot(); });
    $('line').addEventListener('change', () => { renderSelectionButtons(); snapshot(); });
    $('color').addEventListener('change', snapshot);
    $('size').addEventListener('change', snapshot);
    let resizeFrame = 0;
    window.addEventListener('resize', () => {
      cancelAnimationFrame(resizeFrame);
      resizeFrame = requestAnimationFrame(renderDefects);
    });
    window.setInterval(() => {
      if ($('device-dialog').open && !statusReady() && !state.pollingBlocked && state.device?.device_id && state.token && navigator.onLine) check(true);
    }, 5000);
    window.addEventListener('online', () => { updateNetwork(); check(); });
    window.addEventListener('offline', updateNetwork);
    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState !== 'visible') lockPage();
      else if (!state.pageUnlocked) showPageLock();
      else if (navigator.onLine) check();
    });
  }
  function renderQuantityPresets() {
    $('quantity-presets').querySelectorAll('button').forEach(button => {
      button.className = 'btn flex-fill px-2 py-2 btn-default';
      button.setAttribute('aria-pressed', 'false');
    });
  }
  async function init() {
    await loadLanguage();
    if (navigator.onLine) {
      try { await ensureDataEpoch(); } catch (_) { if (epochReloading) return; }
    }
    if (!state.device) state.device = oldDevice();
    if (state.device && !state.token) state.token = randomToken();
    persistDevice();
    attach();
    renderToolbar();
    renderStatus();
    renderCatalog();
    renderTotals();
    const initialUnlock = new Promise(resolve => { initialUnlockResolver = resolve; });
    showPageLock();
    await initialUnlock;
    if (!statusReady()) openDevice();
    try {
      if (sessionStorage.getItem(PREFIX + 'cache_cleared') === '1') {
        sessionStorage.removeItem(PREFIX + 'cache_cleared');
        notice('ui.cache_cleared');
      }
    } catch (_) {}
    if ('serviceWorker' in navigator && window.isSecureContext) {
      navigator.serviceWorker.register('/qc-sw.js', {scope: '/'}).catch(() => {});
    }
    if (navigator.onLine) {
      if (state.device?.device_id) await check();
    }
  }
  init();
})();
