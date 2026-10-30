(async function () {
    await window.UQQCI18nReady;
    'use strict';

    const { t, apply } = window.UQQCI18n;
    const PREFIX = 'fm-uqqc-client:v1:';
    const epochKey = PREFIX + 'data-epoch';
    let epochGeneration = localStorage.getItem(epochKey) || '';
    let epochReloading = false;
    async function ensureDataEpoch() {
        if (epochReloading) throw new Error(t('apiFailed'));
        if (!navigator.onLine) return epochGeneration;
        const response = await fetch('/api/method/factory_management.api.data_epoch',
            { credentials: 'same-origin', cache: 'no-store' });
        if (!response.ok) throw new Error(t('apiFailed'));
        const generation = String(responseData(await response.json())?.generation || '');
        if (epochReloading) throw new Error(t('apiFailed'));
        if (!generation || generation === epochGeneration) return epochGeneration;
        epochReloading = true;
        const deviceId = localStorage.getItem(PREFIX + 'id') || localStorage.getItem(PREFIX + 'device-id');
        Object.keys(localStorage).filter(key => key.startsWith(PREFIX)).forEach(key => localStorage.removeItem(key));
        if (deviceId) localStorage.setItem(PREFIX + 'id', deviceId);
        localStorage.setItem(epochKey, generation);
        epochGeneration = generation;
        if ('caches' in window) {
            try {
                const names = await caches.keys();
                await Promise.all(names.filter(name => name.startsWith('fm-uqqc-')).map(name => caches.delete(name)));
            } catch { /* API writes remain fenced while the page reloads. */ }
        }
        window.location.reload();
        throw new Error(t('apiFailed'));
    }
    const ALL_GROUPS = 'all';
    const FAVORITES_FILTER = 'favorite';
    const ALL_SEASONS = 'all';
    const RECENT_PRODUCTS = 'recent';
    const MAX_RECENT_PRODUCTS = 12;
    const uqqcCollator = new Intl.Collator('vi', { numeric: true, sensitivity: 'base' });
    const UNIQLO_CUSTOMER = 'UNIQLO';
    const GUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
    const keys = {
        deviceId: PREFIX + 'id',
        deviceProfile: PREFIX + 'device-profile',
        catalog: PREFIX + 'catalog',
        queue: PREFIX + 'offline-queue',
        favorites: PREFIX + 'favorite-defects',
        positionFavorites: PREFIX + 'favorite-defect-positions',
        order: PREFIX + 'defect-order',
        groupFilter: PREFIX + 'defect-group',
        arrangeMode: PREFIX + 'uqqc-arrange-mode',
        scrollDirection: PREFIX + 'scroll-direction',
        activePiece: PREFIX + 'active-piece',
        recentProducts: PREFIX + 'recent-products',
        syncErrors: PREFIX + 'uqqc-sync-errors',
        lastSync: PREFIX + 'last-sync',
        detailSnapshots: PREFIX + 'detail-snapshots'
    };
    const cachedProfile = (() => {
        try { return JSON.parse(localStorage.getItem(keys.deviceProfile) || '{}') || {}; }
        catch { return {}; }
    })();
    const storedIds = [localStorage.getItem(keys.deviceId), localStorage.getItem(PREFIX + 'device-id'),
        cachedProfile.id, cachedProfile.deviceId, cachedProfile.device_id]
        .filter(Boolean).map(value => String(value).trim());
    let identityConflict = new Set(storedIds.map(value => value.toLowerCase())).size > 1;
    if (!identityConflict && storedIds.length) {
        localStorage.setItem(keys.deviceId, storedIds[0]);
        localStorage.removeItem(PREFIX + 'device-id');
        if (cachedProfile.id || cachedProfile.deviceId || cachedProfile.device_id) {
            cachedProfile.id = storedIds[0];
            delete cachedProfile.deviceId;
            delete cachedProfile.device_id;
            delete cachedProfile.deviceUid;
            localStorage.setItem(keys.deviceProfile, JSON.stringify(cachedProfile));
        }
    }
    Object.keys(localStorage).filter(key => key.startsWith(PREFIX + 'device-token'))
        .forEach(key => localStorage.removeItem(key));
    const serverConfig = (() => {
        try {
            const el = document.getElementById('uqqc-clientConfig');
            return el ? JSON.parse(el.textContent) : {};
        } catch {
            return {};
        }
    })();
    const config = {
        liveBootstrapEnabled: serverConfig.liveBootstrapEnabled !== false,
        pollingSeconds: Math.max(3, Number(serverConfig.liveBootstrapPollingSeconds || 10)),
        syncWatchdogSeconds: Math.max(3, Number(serverConfig.syncWatchdogSeconds || 5))
    };
    const byId = id => document.getElementById('uqqc-' + id);
    const elements = {
        app: byId('app'), inspection: byId('inspectionPanel'), network: byId('networkStatus'),
        headerTitle: byId('clientHeaderTitle'), detailMachineName: byId('detailMachineName'),
        pending: byId('pendingCount'), fullscreen: byId('fullscreenButton'), scrollDirection: byId('scrollDirectionButton'),
        settings: byId('deviceSettingsButton'), quickFilters: byId('quickFilters'),
        arrangeToggle: byId('defectArrangeToggle'), arrangeToggleLabel: byId('defectArrangeToggleLabel'),
        line: byId('lineSelect'), product: byId('productSelect'), color: byId('colorSelect'),
        size: byId('sizeSelect'), market: byId('marketSelect'), pass: byId('passTotal'),
        rework: byId('reworkTotal'), inspectionTotal: byId('inspectionTotal'), passRate: byId('passRate'),
        defectPcs: byId('defectPcs'), defectNo: byId('defectNo'),
        detailOpen: byId('openDetailButton'), detailPanel: byId('detailPanel'), detailClose: byId('detailCloseButton'),
        detailProduct: byId('detailProductFilter'), detailLine: byId('detailLineFilter'),
        detailBody: byId('detailTableBody'), detailFoot: byId('detailTableFoot'),
        detailStatus: byId('detailStatus'), detailRetry: byId('detailRetryButton'),
        confirmPass: byId('confirmPassButton'), confirmRework: byId('confirmReworkButton'),
        scopePickerPanel: byId('scopePickerPanel'), scopePickerTitle: byId('scopePickerTitle'),
        scopePickerFilters: byId('scopePickerFilters'), scopePickerDivider: byId('scopePickerDivider'), scopePickerGrid: byId('scopePickerGrid'), scopePickerClose: byId('scopePickerCloseButton'),
        scopeHint: byId('scopeHint'), defectGrid: byId('defectGrid'), toast: byId('toast'),
        positionPanel: byId('defectPositionPanel'), positionFilters: byId('defectPositionFilters'),
        positionGrid: byId('defectPositionGrid'), positionClose: byId('defectPositionCloseButton'),
        moreDefectPanel: byId('moreDefectPanel'), moreDefectYes: byId('moreDefectYesButton'), moreDefectNo: byId('moreDefectNoButton'),
        settingsPanel: byId('settingsPanel'), settingsClose: byId('settingsCloseButton'),
        syncNowButton: byId('syncNowButton'), openDeviceSettingsButton: byId('openDeviceSettingsButton'),
        lastSyncTime: byId('lastSyncTime'), settingsDeviceBadge: byId('settingsDeviceBadge'),
        settingsDeviceCompany: byId('settingsDeviceCompany'), syncErrors: byId('syncErrors'),
        devicePanel: byId('devicePanel'), deviceClose: byId('deviceCloseButton'),
        deviceName: byId('deviceNameInput'), manualDeviceId: byId('manualDeviceIdInput'),
        deviceMessage: byId('deviceMessage'), scanQr: byId('scanQrButton'), activateDevice: byId('activateDeviceButton'),
        clearCache: byId('clearClientCacheButton'), qrVideo: byId('qrScannerVideo'), qrStatus: byId('qrScannerStatus')
    };
    const state = {
        device: readJson(keys.deviceProfile, null),
        catalog: null,
        scope: emptyScope(),
        serverSnapshot: emptySnapshot(),
        detailSnapshots: readJson(keys.detailSnapshots, null),
        detailFilters: { productId: '', lineId: '' },
        detailHydrated: false,
        detailHydrationPromise: null,
        detailError: '',
        serverClockDeltaMs: 0,
        queue: normalizeArray(readJson(keys.queue, [])).filter(event => event?.eventKind !== 'quantity'),
        favorites: new Set(normalizeArray(readJson(keys.favorites, []))),
        positionFavorites: new Set(normalizeArray(readJson(keys.positionFavorites, []))),
        order: normalizeArray(readJson(keys.order, [])),
        groupFilter: localStorage.getItem(keys.groupFilter) || ALL_GROUPS,
        defectArrangeMode: localStorage.getItem(keys.arrangeMode) === 'true',
        scopeOptions: { line: [], product: [], market: [], color: [], size: [] },
        scopePickerFilters: { line: '', product: ALL_SEASONS },
        activePicker: '',
        activeDefectId: '',
        positionGroupFilter: ALL_GROUPS,
        activePiece: null,
        syncing: false,
        syncPromise: null,
        clearingCache: false,
        activating: false,
        apiReachable: serverConfig.apiReachable !== false,
        syncErrors: normalizeArray(readJson(keys.syncErrors, [])),
        lastSync: localStorage.getItem(keys.lastSync) || '',
        toastTimer: 0
    };
    let qrStream = null;
    let qrTimer = 0;
    let qrDetector = null;

    function normalizeArray(value) { return Array.isArray(value) ? value : []; }
    function emptyScope() { return { lineId: '', productId: '', colorId: '', sizeId: '', marketId: '' }; }
    function emptySnapshot() {
        return { pass: 0, rework: 0, total: 0, passRate: 0, defectPcs: 0, defectNo: 0, defectPieceIds: [], totalDefects: 0, defects: {} };
    }

    function readJson(key, fallback) {
        try {
            const raw = localStorage.getItem(key);
            return raw ? JSON.parse(raw) : fallback;
        } catch {
            return fallback;
        }
    }

    function writeJson(key, value) {
        try { localStorage.setItem(key, JSON.stringify(value)); return true; }
        catch { return false; }
    }

    function renderHeaderTitle() {
        const deviceName = String(state.device?.deviceName || '').trim() || t('appName');
        elements.headerTitle.textContent = deviceName;
        elements.detailMachineName.textContent = deviceName;
    }

    function updateServerClock(serverNowUtc) {
        const serverTime = Date.parse(serverNowUtc || '');
        if (Number.isFinite(serverTime)) state.serverClockDeltaMs = serverTime - Date.now();
    }

    function currentServerDateKey(catalog = state.catalog) {
        if (!catalog) return '';
        const offsetMinutes = Number(catalog.serverUtcOffsetMinutes);
        const offset = Number.isFinite(offsetMinutes) ? offsetMinutes : -new Date().getTimezoneOffset();
        return new Date(Date.now() + state.serverClockDeltaMs + offset * 60000).toISOString().slice(0, 10);
    }

    function pruneDetailSnapshots() {
        const deviceId = String(state.device?.id || '').toLowerCase();
        const serverDateKey = state.catalog?.serverDateKey || '';
        const saved = state.detailSnapshots;
        if (saved?.deviceId === deviceId && saved.serverDateKey === serverDateKey &&
            saved.scopes && typeof saved.scopes === 'object' && !Array.isArray(saved.scopes)) return;
        state.detailSnapshots = { deviceId, serverDateKey, scopes: {} };
        state.detailHydrated = false;
        state.detailError = '';
        writeJson(keys.detailSnapshots, state.detailSnapshots);
    }

    function detailScopeKey(scope) {
        return [scope.lineId, scope.productId, scope.colorId, scope.sizeId, scope.marketId]
            .map(value => String(value || '').toLowerCase()).join(':');
    }

    function hasDetailCache() {
        return Object.values(state.detailSnapshots?.scopes || {}).some(entry => {
            const snapshot = entry?.snapshot || {};
            return Number(snapshot.pass || 0) > 0 || Number(snapshot.rework || 0) > 0 || Number(snapshot.defectNo || 0) > 0;
        });
    }

    function detailSnapshotCoversLocal(data, saved) {
        if (!data) return false;
        const serverScopes = new Map(normalizeArray(data.scopes).map(item => [detailScopeKey(item), item]));
        return Object.values(saved?.scopes || {}).every(entry => {
            if (!entry?.scope || !entry.snapshot) return true;
            if (saved.serverDateKey !== data.serverDateKey) return false;
            const snapshot = entry.snapshot;
            const server = serverScopes.get(detailScopeKey(entry.scope));
            if (!server) return ![snapshot.pass, snapshot.rework, snapshot.defectNo, ...Object.values(snapshot.defects || {})]
                .some(value => Number(value || 0) > 0);
            return Number(server.pass || 0) >= Number(snapshot.pass || 0) &&
                Number(server.rework || 0) >= Number(snapshot.rework || 0) &&
                Number(server.defectNo || 0) >= Number(snapshot.defectNo || 0) &&
                Object.entries(snapshot.defects || {}).every(([id, count]) => Number(server.defects?.[id] || 0) >= Number(count || 0));
        });
    }

    function hydrateDetailSnapshots() {
        if (state.detailHydrationPromise) return state.detailHydrationPromise;
        if (!isApproved() || !state.catalog) return Promise.resolve(null);
        const deviceId = state.device.id;
        state.detailError = '';
        const operation = (async () => {
            try {
                // Serialize with queue sync so accepted events cannot be counted again as pending events.
                if (state.syncPromise) await state.syncPromise;
                pruneDetailSnapshots();
                const previousScopes = { ...state.detailSnapshots.scopes };
                const requestedDateKey = state.catalog.serverDateKey;
                const data = await requestJson('/api/method/uqqc-inspections-detail-snapshot', {
                    method: 'POST', body: JSON.stringify({ id: deviceId })
                });
                if (state.device?.id !== deviceId || !state.catalog) return null;
                // A successful but incomplete response must not erase acknowledged local data.
                if (data.serverDateKey === requestedDateKey && !detailSnapshotCoversLocal(data, {
                    serverDateKey: requestedDateKey, scopes: previousScopes
                })) {
                    state.detailError = t('detailRestoreFailed');
                    return null;
                }
                updateServerClock(data.serverNowUtc);
                if (state.catalog.serverDateKey !== data.serverDateKey) {
                    state.catalog.serverDateKey = data.serverDateKey;
                    state.serverSnapshot = emptySnapshot();
                    pruneDetailSnapshots();
                    restoreActivePiece();
                }
                state.catalog.serverUtcOffsetMinutes = data.serverUtcOffsetMinutes;
                const scopes = {};
                normalizeArray(data.scopes).forEach(item => {
                    const scope = {
                        lineId: item.lineId, productId: item.productId, colorId: item.colorId,
                        sizeId: item.sizeId, marketId: item.marketId
                    };
                    const key = detailScopeKey(scope);
                    scopes[key] = { scope, snapshot: {
                        pass: Math.max(0, Number(item.pass || 0)), rework: Math.max(0, Number(item.rework || 0)),
                        defectNo: Math.max(0, Number(item.defectNo || 0)), defects: { ...(item.defects || {}) }
                    } };
                });
                // Keep a single-scope refresh completed while the full snapshot was being loaded.
                Object.entries(state.detailSnapshots.scopes).forEach(([key, entry]) => {
                    if (requestedDateKey === data.serverDateKey && previousScopes[key] !== entry) scopes[key] = entry;
                });
                state.detailSnapshots = { deviceId: String(deviceId).toLowerCase(), serverDateKey: data.serverDateKey, scopes };
                state.detailHydrated = true;
                writeJson(keys.detailSnapshots, state.detailSnapshots);
                return data;
            } catch {
                if (state.device?.id === deviceId) state.detailError = t('detailRestoreFailed');
                return null;
            }
        })();
        state.detailHydrationPromise = operation;
        renderDetailIfOpen();
        return operation.finally(() => {
            if (state.detailHydrationPromise === operation) state.detailHydrationPromise = null;
            renderDetailIfOpen();
        });
    }

    function saveDetailSnapshot(scope, snapshot) {
        if (!state.device?.id || !state.catalog || snapshot?.serverDateKey !== state.catalog.serverDateKey) return;
        pruneDetailSnapshots();
        state.detailSnapshots.scopes[detailScopeKey(scope)] = {
            scope: { ...scope },
            snapshot: {
                pass: Math.max(0, Number(snapshot.pass || 0)),
                rework: Math.max(0, Number(snapshot.rework || 0)),
                defectNo: Math.max(0, Number(snapshot.defectNo || 0)),
                defects: { ...(snapshot.defects || {}) }
            }
        };
        writeJson(keys.detailSnapshots, state.detailSnapshots);
        renderDetailIfOpen();
    }

    function addAcceptedEventsToDetailSnapshot(scope, events) {
        if (!state.device?.id || !state.catalog) return;
        pruneDetailSnapshots();
        const key = detailScopeKey(scope);
        const saved = state.detailSnapshots.scopes[key]?.snapshot || emptySnapshot();
        const snapshot = { ...saved, defects: { ...(saved.defects || {}) }, serverDateKey: state.catalog.serverDateKey };
        events.forEach(event => {
            if (event.eventKind === 'pass') snapshot.pass = Number(snapshot.pass || 0) + 1;
            else if (event.eventKind === 'rework') snapshot.rework = Number(snapshot.rework || 0) + 1;
            else if (event.eventKind === 'defect' && event.defectId) {
                snapshot.defects[event.defectId] = Number(snapshot.defects[event.defectId] || 0) + 1;
                snapshot.defectNo = Number(snapshot.defectNo || 0) + 1;
            }
        });
        saveDetailSnapshot(scope, snapshot);
        if (detailScopeKey(state.scope) === key) {
            const pieceIds = new Set(normalizeArray(state.serverSnapshot.defectPieceIds).map(value => String(value).toLowerCase()));
            events.filter(event => event.eventKind === 'defect' && event.defectPieceId)
                .forEach(event => pieceIds.add(String(event.defectPieceId).toLowerCase()));
            const legacyPieces = Math.max(0, Number(state.serverSnapshot.defectPcs || 0) -
                normalizeArray(state.serverSnapshot.defectPieceIds).length);
            state.serverSnapshot = {
                ...state.serverSnapshot,
                ...snapshot,
                defectPieceIds: [...pieceIds],
                defectPcs: legacyPieces + pieceIds.size
            };
        }
    }

    function syncServerDay() {
        if (!state.device?.id || !state.catalog?.serverDateKey) return false;
        const dateKey = currentServerDateKey();
        if (!dateKey || dateKey === state.catalog.serverDateKey) return false;
        state.catalog.serverDateKey = dateKey;
        state.serverSnapshot = emptySnapshot();
        pruneDetailSnapshots();
        restoreScope();
        restoreActivePiece();
        renderScopeControls();
        renderDetailIfOpen();
        return true;
    }

    function createId() {
        if (crypto.randomUUID) return crypto.randomUUID();
        return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, character => {
            const random = Math.random() * 16 | 0;
            const value = character === 'x' ? random : (random & 3 | 8);
            return value.toString(16);
        });
    }

    function canReachApi() {
        return navigator.onLine && state.apiReachable !== false;
    }

    function setApiReachable(value) {
        state.apiReachable = Boolean(value);
        updateNetwork();
        renderSettingsState();
    }

    function markApiUnavailable() {
        state.apiReachable = false;
        updateNetwork();
        renderSettingsState();
    }

    async function requestJson(url, options) {
        if (identityConflict) throw new Error(t('deviceIdentityConflict'));
        const requestEpoch = await ensureDataEpoch();
        if (epochReloading) throw new Error(t('apiFailed'));
        if (options?.method === 'GET') url += '?id=' + encodeURIComponent(storedDeviceId());
        let response;
        try {
            response = await fetch(url, {
                credentials: 'same-origin',
                headers: { 'Content-Type': 'application/json', Accept: 'application/json', 'X-Factory-Data-Epoch': requestEpoch, 'Accept-Language': document.documentElement.lang, ...(window.frappe?.csrf_token ? { 'X-Frappe-CSRF-Token': frappe.csrf_token } : {}) },
                ...options
            });
        } catch (networkError) {
            markApiUnavailable();
            throw networkError;
        }

        if (response.status >= 500) {
            markApiUnavailable();
        } else {
            setApiReachable(true);
        }

        let payload = null;
        try { payload = await response.json(); } catch { /* handled by the generic localized error below */ }
        if (!response.ok || !payload || typeof payload !== 'object') {
            let message = '';
            try {
                const notices = JSON.parse(payload?._server_messages || '[]');
                message = notices.length ? JSON.parse(notices[0]).message : '';
            } catch { /* Use the localized fallback for malformed error envelopes. */ }
            if (response.status === 403 && state.device && !url.includes('uqqc-device-register')) {
                state.device = { ...state.device, isActive: false };
                writeJson(keys.deviceProfile, state.device);
                renderInactiveScope();
                openDevicePanel(message || t('apiFailed'), true);
            }
            const error = new Error(message || t('apiFailed'));
            error.retryable = response.status === 409 && payload?.exc_type === 'UQQCSyncRetryError';
            throw error;
        }
        return responseData(payload);
    }

    function responseData(payload) {
        return payload && Object.prototype.hasOwnProperty.call(payload, 'message') ? payload.message : payload;
    }

    function setMessage(element, value, isError) {
        if (!element) return;
        element.textContent = value || '';
        element.classList.toggle('text-danger', Boolean(isError));
        element.classList.toggle('text-muted', !isError);
    }

    function showToast(message, isError) {
        window.clearTimeout(state.toastTimer);
        elements.toast.textContent = message;
        if (window.frappe?.show_alert) {
            elements.toast.hidden = true;
            const content = document.createElement('span');
            content.textContent = message;
            window.frappe.show_alert({ message: content.outerHTML, indicator: isError ? 'red' : 'green' }, 3);
            return;
        }
        elements.toast.classList.toggle('alert-danger', Boolean(isError));
        elements.toast.classList.toggle('alert-success', !isError);
        elements.toast.hidden = false;
        state.toastTimer = window.setTimeout(() => { elements.toast.hidden = true; }, 3200);
    }

    function browserName() {
        const userAgent = navigator.userAgent;
        if (userAgent.includes('Edg/')) return 'Edge';
        if (userAgent.includes('Chrome/')) return 'Chrome';
        if (userAgent.includes('Firefox/')) return 'Firefox';
        if (userAgent.includes('Safari/')) return 'Safari';
        return t('unknownBrowser');
    }

    function browserVersion() {
        const match = navigator.userAgent.match(/(?:Edg|Chrome|Firefox|Version)\/([\d.]+)/);
        return match?.[1] || navigator.appVersion || '';
    }

    function operatingSystem() {
        return navigator.userAgentData?.platform || navigator.platform || '';
    }

    function storedDeviceId() {
        return String(localStorage.getItem(keys.deviceId) || state.device?.id || '').trim();
    }

    function saveDevice(device) {
        delete device.deviceId;
        delete device.device_id;
        delete device.deviceUid;
        const previousId = String(state.device?.id || localStorage.getItem(keys.deviceId) || '').toLowerCase();
        if (previousId && device?.id && previousId !== String(device.id).toLowerCase()) {
            resetDeviceWorkState();
        }
        state.device = device;
        if (device?.id) localStorage.setItem(keys.deviceId, device.id);
        writeJson(keys.deviceProfile, device);
        renderHeaderTitle();
    }

    function isApproved() {
        return !identityConflict && state.device && String(state.device.status).toLowerCase() === 'approved' && state.device.isActive;
    }

    function updateNetwork() {
        const browserOnline = navigator.onLine;
        const apiOnline = browserOnline && state.apiReachable !== false;
        const color = !browserOnline ? 'btn-danger' : !apiOnline ? 'btn-warning' : 'btn-success';
        const label = t(!browserOnline ? 'offline' : !apiOnline ? 'apiDisconnected' : 'online');
        elements.network.className = `btn btn-sm p-1 mr-2 ${color}`;
        elements.network.querySelector('.uqqc-network-online')?.classList.toggle('d-none', !apiOnline);
        elements.network.querySelector('.uqqc-network-offline')?.classList.toggle('d-none', apiOnline);
        elements.network.setAttribute('aria-label', label);
        elements.network.title = label;
    }

    function panels() {
        return [elements.devicePanel, elements.settingsPanel, elements.detailPanel,
            elements.scopePickerPanel, elements.positionPanel, elements.moreDefectPanel];
    }

    function setPanelVisibility(panel, visible) {
        const modal = window.jQuery?.fn?.modal;
        if (visible) {
            panels().filter(other => other !== panel && other.classList.contains('open'))
                .forEach(other => setPanelVisibility(other, false));
        }
        panel.classList.toggle('open', visible);
        panel.setAttribute('aria-hidden', String(!visible));
        if (modal) {
            const required = panel === elements.moreDefectPanel;
            window.jQuery(panel).modal(visible
                ? { show: true, backdrop: required ? 'static' : true, keyboard: !required, focus: !required }
                : 'hide');
        } else {
            panel.hidden = !visible;
        }
    }

    function updatePending() { elements.pending.textContent = String(state.queue.length); }

    function renderDevice() {
        const id = storedDeviceId();
        elements.deviceName.value = state.device?.deviceName || '';
        renderHeaderTitle();
        if (!elements.manualDeviceId.value) elements.manualDeviceId.value = id;
        elements.manualDeviceId.disabled = isApproved();
        renderSettingsState();
    }

    function openDevicePanel(message, isError) {
        renderDevice();
        if (message !== undefined) setMessage(elements.deviceMessage, message, isError);
        setPanelVisibility(elements.devicePanel, true);
    }

    function closeDevicePanel() {
        stopQrScanner();
        setPanelVisibility(elements.devicePanel, false);
    }

    function appendSyncError(message) {
        if (!message) return;
        const entry = { at: new Date().toISOString(), message: String(message) };
        state.syncErrors.push(entry);
        if (state.syncErrors.length > 5) {
            state.syncErrors = state.syncErrors.slice(-5);
        }
        writeJson(keys.syncErrors, state.syncErrors);
    }

    function renderSettingsState() {
        if (elements.pending) elements.pending.textContent = String(state.queue.length);
        if (elements.lastSyncTime) elements.lastSyncTime.textContent = state.lastSync || '--:--';

        if (elements.settingsDeviceBadge) {
            const approved = isApproved();
            elements.settingsDeviceBadge.className = `indicator-pill ${approved ? 'green' : 'gray'}`;
            const deviceName = state.device?.deviceName || '';
            const status = String(state.device?.status || '').toLowerCase();
            if (approved) {
                elements.settingsDeviceBadge.textContent = deviceName || t('deviceReady');
                elements.settingsDeviceBadge.classList.add('approved');
            } else if (status === 'pendingapproval') {
                elements.settingsDeviceBadge.textContent = t('pendingApproval');
                elements.settingsDeviceBadge.classList.remove('approved');
            } else if (status === 'rejected' || status === 'deactivated') {
                elements.settingsDeviceBadge.textContent = t('rejected');
                elements.settingsDeviceBadge.classList.remove('approved');
            } else {
                elements.settingsDeviceBadge.textContent = t('unregistered');
                elements.settingsDeviceBadge.classList.remove('approved');
            }
        }

        if (elements.settingsDeviceCompany) {
            elements.settingsDeviceCompany.textContent = state.device?.companyName
                ? `${state.device.companyName}`
                : '';
        }

        if (elements.syncErrors) {
            if (!state.syncErrors.length) {
                elements.syncErrors.textContent = t('noSyncErrors');
            } else {
                elements.syncErrors.textContent = state.syncErrors
                    .map(item => `${new Date(item.at).toLocaleTimeString()} - ${item.message}`)
                    .join('\n');
            }
        }
    }

    function openSettingsPanel() {
        renderSettingsState();
        setPanelVisibility(elements.settingsPanel, true);
    }

    function closeSettingsPanel() {
        setPanelVisibility(elements.settingsPanel, false);
    }

    function resetDeviceWorkState() {
        state.scope = emptyScope();
        state.serverSnapshot = emptySnapshot();
        state.queue = [];
        state.favorites = new Set();
        state.positionFavorites = new Set();
        state.order = [];
        state.activePiece = null;
        state.detailSnapshots = null;
        state.detailHydrated = false;
        state.detailError = '';
        [keys.queue, keys.favorites, keys.positionFavorites, keys.order, keys.detailSnapshots].forEach(key => localStorage.removeItem(key));
        if (state.device?.id) localStorage.removeItem(activePieceStorageKey());
        updatePending();
    }

    async function activateDevice() {
        if (identityConflict) {
            setMessage(elements.deviceMessage, t('deviceIdentityConflict'), true);
            return;
        }
        if (state.activating) return;
        const deviceId = String(elements.manualDeviceId.value || storedDeviceId()).trim();
        if (!deviceId) {
            setMessage(elements.deviceMessage, t('DeviceIdRequired'), true);
            return;
        }
        if (!GUID_PATTERN.test(deviceId)) {
            setMessage(elements.deviceMessage, t('deviceIdInvalid'), true);
            return;
        }

        if (storedDeviceId() && storedDeviceId().toLowerCase() !== deviceId.toLowerCase() && (state.queue.length || state.activePiece)) {
            setMessage(elements.deviceMessage, t('deviceSwitchPending'), true);
            return;
        }
        state.activating = true;
        elements.activateDevice.disabled = true;
        setMessage(elements.deviceMessage, t('activating'));
        try {
            const device = await requestJson('/api/method/uqqc-device-register', {
                method: 'POST',
                body: JSON.stringify({
                    id: deviceId
                })
            });
            saveDevice(device);
            elements.manualDeviceId.value = '';
            renderDevice();
            if (!isApproved()) {
                setMessage(elements.deviceMessage, t('pendingApproval'), true);
                return;
            }

            setMessage(elements.deviceMessage, t('deviceReady'));
            await activateDeviceState();
            window.setTimeout(closeDevicePanel, 350);
        } catch (error) {
            setMessage(elements.deviceMessage, error.message || t('registrationFailed'), true);
        } finally {
            state.activating = false;
            elements.activateDevice.disabled = false;
        }
    }

    async function checkDevice() {
        if (identityConflict) {
            renderInactiveScope();
            openDevicePanel(t('deviceIdentityConflict'), true);
            return;
        }
        const id = storedDeviceId();
        if (!id) {
            renderInactiveScope();
            openDevicePanel('', false);
            return;
        }

        try {
            const device = await requestJson('/api/method/uqqc-device-check', {
                method: 'POST',
                body: JSON.stringify({ id })
            });
            saveDevice(device);
        } catch (error) {
            const cached = readJson(keys.deviceProfile, null);
            if (cached && !navigator.onLine) {
                state.device = cached;
            } else {
                state.device = cached ? { ...cached, isActive: false } : null;
                renderInactiveScope();
                openDevicePanel(error.message || t('checkFailed'), true);
                return;
            }
        }
        await activateDeviceState();
    }

    async function activateDeviceState() {
        renderDevice();
        if (!isApproved()) {
            renderInactiveScope();
            const rejected = ['rejected', 'deactivated'].includes(String(state.device?.status || '').toLowerCase());
            openDevicePanel(t(rejected ? 'rejected' : 'pendingApproval'), true);
            return;
        }

        closeDevicePanel();
        await loadCatalog();
        await hydrateDetailSnapshots();
        void syncQueue();
    }

    function renderInactiveScope() {
        state.catalog ??= {
            lines: [], products: [], seasons: [], colors: [], sizes: [], markets: [], productVariants: [], defects: [],
            defectPositionGroups: [], defectPositions: []
        };
        state.serverSnapshot = emptySnapshot();
        fillSelect(elements.line, [], 'selectLine', '', false, 'line');
        fillSelect(elements.product, [], 'selectProduct', '', false, 'product');
        fillSelect(elements.market, [], 'selectMarket', '', false, 'market');
        fillSelect(elements.color, [], 'selectColor', '', false, 'color');
        fillSelect(elements.size, [], 'selectSize', '', false, 'size');
        updateScopePickerButtons();
        renderQuickFilters();
        renderDefects();
    }

    let catalogLoadInFlight = false;
    async function loadCatalog(silent) {
        if (state.clearingCache || catalogLoadInFlight) return;
        catalogLoadInFlight = true;
        if (!silent) elements.scopeHint.textContent = t('loading');
        try {
            const catalog = await requestJson('/api/method/uqqc-bootstrap', { method: 'GET' });
            if (state.clearingCache) return;
            updateServerClock(catalog.serverNowUtc);
            const serverDateKey = currentServerDateKey(catalog) || catalog.serverDateKey;
            const hasSameCatalog = Boolean(state.catalog?.catalogVersion &&
                state.catalog.catalogVersion === catalog.catalogVersion &&
                state.catalog.serverDateKey === serverDateKey);
            if (hasSameCatalog) {
                state.catalog.serverNowUtc = catalog.serverNowUtc;
                state.catalog.serverUtcOffsetMinutes = catalog.serverUtcOffsetMinutes;
                writeJson(keys.catalog, state.catalog);
                return;
            }

            const gridScrollTop = elements.defectGrid.scrollTop;
            const gridScrollLeft = elements.defectGrid.scrollLeft;
            state.catalog = catalog;
            state.catalog.serverDateKey = serverDateKey;
            writeJson(keys.catalog, catalog);
            pruneDetailSnapshots();
            restoreScope();
            restoreActivePiece();
            renderScopeControls();
            elements.defectGrid.scrollTop = gridScrollTop;
            elements.defectGrid.scrollLeft = gridScrollLeft;
        } catch (error) {
            if (state.clearingCache) return;
            // Keep the current catalog and rendered grid when a silent refresh fails.
            if (state.catalog && silent) return;
            const cached = readJson(keys.catalog, null);
            if (!cached) {
                elements.scopeHint.textContent = error.message || t('bootstrapFailed');
                showToast(t('bootstrapFailed'), true);
                return;
            }
            state.catalog = cached;
            state.serverClockDeltaMs = 0;
            state.catalog.serverDateKey = currentServerDateKey() || cached.serverDateKey;
            pruneDetailSnapshots();
            restoreScope();
            restoreActivePiece();
            renderScopeControls();
            if (!silent) showToast(t('cachedCatalog'));
        } finally {
            catalogLoadInFlight = false;
            elements.app.setAttribute('aria-busy', 'false');
        }
    }

    function scopeStorageKey() { return `${PREFIX}scope:${state.device.id}`; }
    function lineStorageKey() { return `${PREFIX}line:${state.device.id}`; }
    function activePieceStorageKey() { return `${keys.activePiece}:${state.device.id}`; }
    function recentProductsStorageKey() { return `${keys.recentProducts}:${state.device.id}`; }

    function restoreScope() {
        const saved = readJson(scopeStorageKey(), null);
        const rememberedLine = localStorage.getItem(lineStorageKey()) || '';
        const dateKey = state.catalog.serverDateKey || '';
        state.scope = saved && saved.serverDateKey === dateKey
            ? {
                lineId: saved.lineId || rememberedLine,
                productId: saved.productId || '',
                colorId: saved.colorId || '',
                sizeId: saved.sizeId || '',
                marketId: saved.marketId || ''
            }
            : { ...emptyScope(), lineId: rememberedLine };
        persistScope();
    }

    function persistScope() {
        if (!state.device?.id || !state.catalog) return;
        writeJson(scopeStorageKey(), { ...state.scope, serverDateKey: state.catalog.serverDateKey || '' });
        if (state.scope.lineId) localStorage.setItem(lineStorageKey(), state.scope.lineId);
    }

    function recentProductIds() {
        if (!state.device?.id) return [];
        const allowed = new Set(state.scopeOptions.product.map(item => item.id));
        return [...new Set(normalizeArray(readJson(recentProductsStorageKey(), [])))]
            .filter(id => allowed.has(id))
            .slice(0, MAX_RECENT_PRODUCTS);
    }

    function rememberRecentProduct(productId) {
        if (!state.device?.id || !productId) return;
        const allowed = new Set(state.scopeOptions.product.map(item => item.id));
        const recent = [productId, ...normalizeArray(readJson(recentProductsStorageKey(), []))]
            .filter((id, index, values) => allowed.has(id) && values.indexOf(id) === index)
            .slice(0, MAX_RECENT_PRODUCTS);
        writeJson(recentProductsStorageKey(), recent);
    }

    function activePieceMatchesScope(piece) {
        return Boolean(piece) && piece.serverDateKey === state.catalog?.serverDateKey &&
            ['lineId', 'productId', 'colorId', 'sizeId', 'marketId'].every(key => piece.scope?.[key] === state.scope[key]);
    }

    function restoreActivePiece() {
        if (!state.device?.id || !state.catalog) {
            state.activePiece = null;
            return;
        }
        const saved = readJson(activePieceStorageKey(), null);
        state.activePiece = activePieceMatchesScope(saved) ? saved : null;
        if (!state.activePiece) {
            localStorage.removeItem(activePieceStorageKey());
            closeMoreDefectDialog();
        }
        if (state.activePiece?.decisionPending) window.setTimeout(openMoreDefectDialog, 0);
    }

    function persistActivePiece() {
        if (!state.device?.id) return;
        if (state.activePiece) writeJson(activePieceStorageKey(), state.activePiece);
        else localStorage.removeItem(activePieceStorageKey());
    }

    function endActivePiece(showScopeMessage) {
        if (!state.activePiece) return;
        state.activePiece = null;
        persistActivePiece();
        closeMoreDefectDialog();
        if (showScopeMessage) showToast(t('activePieceScopeChanged'));
    }

    function validVariants() {
        const uniqloCustomerIds = new Set(normalizeArray(state.catalog?.customers)
            .filter(customer => [customer.code, customer.name]
                .some(value => String(value || '').trim().toUpperCase() === UNIQLO_CUSTOMER))
            .map(customer => customer.id));
        const uniqloProductIds = new Set(normalizeArray(state.catalog?.products)
            .filter(product => uniqloCustomerIds.has(product.customerId))
            .map(product => product.id));
        return normalizeArray(state.catalog?.productVariants)
            .filter(variant => variant.marketId && uniqloProductIds.has(variant.productId));
    }

    function distinctOptions(ids, source) {
        const allowed = new Set(ids);
        return normalizeArray(source).filter(item => allowed.has(item.id));
    }

    function optionText(item) { return item.code && item.name ? `${item.code} - ${item.name}` : (item.code || item.name || t('notAvailable')); }

    function seasonCodeText(item) { return item.code || t('notAvailable'); }

    function scopeOptionText(kind, item) {
        return kind === 'product' ? (item.code || t('notAvailable')) : optionText(item);
    }

    function fillSelect(select, options, placeholderKey, selectedValue, enabled, kind) {
        const fragment = document.createDocumentFragment();
        const placeholder = document.createElement('option');
        placeholder.value = '';
        placeholder.textContent = t(placeholderKey);
        fragment.appendChild(placeholder);
        options.forEach(item => {
            const option = document.createElement('option');
            option.value = item.id;
            option.textContent = scopeOptionText(kind, item);
            fragment.appendChild(option);
        });
        select.replaceChildren(fragment);
        select.disabled = !enabled;
        select.value = options.some(item => item.id === selectedValue) ? selectedValue : '';
        return select.value;
    }

    const pickerDefinitions = {
        line: { select: elements.line, button: byId('linePickerButton'), placeholder: 'selectLine', title: 'chooseLineTitle' },
        product: { select: elements.product, button: byId('productPickerButton'), placeholder: 'selectProduct', title: 'chooseProductTitle' },
        market: { select: elements.market, button: byId('marketPickerButton'), placeholder: 'selectMarket', title: 'chooseMarketTitle' },
        color: { select: elements.color, button: byId('colorPickerButton'), placeholder: 'selectColor', title: 'chooseColorTitle' },
        size: { select: elements.size, button: byId('sizePickerButton'), placeholder: 'selectSize', title: 'chooseSizeTitle' }
    };
    const SCOPE_FLOW = ['line', 'product', 'market', 'color', 'size'];

    function updateScopePickerButtons() {
        Object.entries(pickerDefinitions).forEach(([kind, definition]) => {
            const selected = state.scopeOptions[kind].find(item => item.id === definition.select.value);
            const selectedLabel = kind === 'color'
                ? (selected?.code || t('notAvailable'))
                : kind === 'size'
                    ? (selected?.name || t('notAvailable'))
                    : (selected ? scopeOptionText(kind, selected) : '');
            definition.button.textContent = selected ? selectedLabel : t(definition.placeholder);
            definition.button.disabled = definition.select.disabled;
        });
    }

    function renderScopePicker() {
        const kind = state.activePicker;
        const definition = pickerDefinitions[kind];
        if (!definition) return;
        elements.scopePickerTitle.textContent = t(definition.title);
        elements.scopePickerDivider.hidden = kind !== 'line' && kind !== 'product';
        renderScopePickerFilters(kind);
        let options = state.scopeOptions[kind].slice();
        if (kind === 'line' && state.scopePickerFilters.line) {
            options = options.filter(item => item.factoryId === state.scopePickerFilters.line);
        }
        if (kind === 'product') {
            const productFilter = state.scopePickerFilters.product;
            if (productFilter === RECENT_PRODUCTS) {
                const optionById = new Map(options.map(item => [item.id, item]));
                options = recentProductIds().map(id => optionById.get(id)).filter(Boolean);
            } else if (productFilter !== ALL_SEASONS) {
                options = options.filter(item => item.seasonId === productFilter);
            }
        }
        options.sort((left, right) =>
            uqqcCollator.compare(scopeOptionText(kind, left), scopeOptionText(kind, right)) ||
            uqqcCollator.compare(String(left.id || ''), String(right.id || '')));
        if (!options.length) {
            const empty = document.createElement('p');
            empty.className = 'col-12 text-muted';
            empty.textContent = kind === 'product' && state.scopePickerFilters.product === RECENT_PRODUCTS
                ? t('noRecentProducts')
                : t('noScopeOptions');
            elements.scopePickerGrid.replaceChildren(empty);
            return;
        }

        const fragment = document.createDocumentFragment();
        options.forEach(item => {
            const button = document.createElement('button');
            button.type = 'button';
            button.className = `uqqc-scope-picker-option btn btn-default btn-block h-100 text-center text-wrap py-3 px-2${definition.select.value === item.id ? ' uqqc-is-selected active' : ''}`;
            button.textContent = scopeOptionText(kind, item);
            button.addEventListener('click', event => {
                ensureFullscreen();
                definition.select.value = item.id;
                handleScopeChange(kind);
                advanceScopePicker(kind, event.detail > 0);
            });
            const column = document.createElement('div');
            column.className = 'col-6 col-sm-4 col-lg-3 col-xl-2 px-1 mb-2';
            column.appendChild(button);
            fragment.appendChild(column);
        });
        elements.scopePickerGrid.replaceChildren(fragment);
    }

    function renderScopePickerFilters(kind) {
        if (kind !== 'line' && kind !== 'product') {
            elements.scopePickerFilters.hidden = true;
            elements.scopePickerFilters.replaceChildren();
            return;
        }

        const fragment = document.createDocumentFragment();
        const appendFilter = (value, label) => {
            const button = document.createElement('button');
            button.type = 'button';
            const active = state.scopePickerFilters[kind] === value;
            button.className = `uqqc-scope-picker-filter btn btn-default btn-sm mr-2 mb-2${active ? ' uqqc-is-active active' : ''}`;
            button.textContent = label;
            button.setAttribute('aria-pressed', String(active));
            button.addEventListener('click', () => {
                ensureFullscreen();
                state.scopePickerFilters[kind] = value;
                renderScopePicker();
            });
            fragment.appendChild(button);
        };

        if (kind === 'line') {
            const source = normalizeArray(state.catalog?.factories);
            const allowed = new Set(state.scopeOptions.line.map(item => item.factoryId).filter(Boolean));
            const groups = source.filter(item => allowed.has(item.id)).sort((left, right) =>
                uqqcCollator.compare(left.name || left.code || '', right.name || right.code || ''));
            if (state.scopePickerFilters.line && !groups.some(item => item.id === state.scopePickerFilters.line)) {
                state.scopePickerFilters.line = '';
            }
            appendFilter('', t('allFactories'));
            groups.forEach(item => appendFilter(item.id, item.name || item.code || t('notAvailable')));
        } else {
            const allowedSeasonIds = new Set(state.scopeOptions.product.map(item => item.seasonId).filter(Boolean));
            const seasons = normalizeArray(state.catalog?.seasons)
                .filter(item => allowedSeasonIds.has(item.id))
                .sort((left, right) => uqqcCollator.compare(seasonCodeText(left), seasonCodeText(right)) ||
                    uqqcCollator.compare(String(left.id || ''), String(right.id || '')));
            const validFilters = new Set([ALL_SEASONS, RECENT_PRODUCTS, ...seasons.map(item => item.id)]);
            if (!validFilters.has(state.scopePickerFilters.product)) state.scopePickerFilters.product = ALL_SEASONS;
            appendFilter(RECENT_PRODUCTS, t('recentProducts'));
            appendFilter(ALL_SEASONS, t('allSeasons'));
            seasons.forEach(item => appendFilter(item.id, seasonCodeText(item)));
        }
        elements.scopePickerFilters.replaceChildren(fragment);
        elements.scopePickerFilters.hidden = false;
    }

    function openScopePicker(kind) {
        ensureFullscreen();
        const definition = pickerDefinitions[kind];
        if (!definition || definition.button.disabled) return;
        state.activePicker = kind;
        renderScopePicker();
        setPanelVisibility(elements.scopePickerPanel, true);
        window.setTimeout(() => {
            const selectedOption = elements.scopePickerGrid.querySelector('.uqqc-is-selected');
            const initialOption = selectedOption || elements.scopePickerGrid.querySelector('.uqqc-scope-picker-option');
            initialOption?.focus();
        }, 0);
    }

    function closeScopePicker(restoreFocus = true) {
        const definition = pickerDefinitions[state.activePicker];
        setPanelVisibility(elements.scopePickerPanel, false);
        state.activePicker = '';
        if (restoreFocus) definition?.button.focus();
    }

    function advanceScopePicker(kind, blurAfterSelection = false) {
        const nextKind = SCOPE_FLOW[SCOPE_FLOW.indexOf(kind) + 1] || '';
        closeScopePicker(!nextKind);
        if (nextKind) {
            window.setTimeout(() => openScopePicker(nextKind), 0);
        } else if (blurAfterSelection) {
            pickerDefinitions[kind]?.button.blur();
        }
    }

    function renderDefectPositionFilters() {
        const positions = normalizeArray(state.catalog?.defectPositions);
        const allowedGroupIds = new Set(positions.map(item => item.positionGroupId));
        const groups = normalizeArray(state.catalog?.defectPositionGroups)
            .filter(item => allowedGroupIds.has(item.id))
            .sort((left, right) => uqqcCollator.compare(optionText(left), optionText(right)));
        if (![ALL_GROUPS, FAVORITES_FILTER].includes(state.positionGroupFilter) && !allowedGroupIds.has(state.positionGroupFilter)) {
            state.positionGroupFilter = ALL_GROUPS;
        }

        const fragment = document.createDocumentFragment();
        const appendFilter = (value, label) => {
            const button = document.createElement('button');
            button.type = 'button';
            button.className = `uqqc-scope-picker-filter btn btn-default btn-sm flex-shrink-0 mr-2${state.positionGroupFilter === value ? ' uqqc-is-active active' : ''}`;
            button.textContent = label;
            button.setAttribute('aria-pressed', String(state.positionGroupFilter === value));
            button.addEventListener('click', () => {
                ensureFullscreen();
                state.positionGroupFilter = value;
                renderDefectPositionPicker();
            });
            fragment.appendChild(button);
        };
        appendFilter(ALL_GROUPS, t('allPositionGroups'));
        appendFilter(FAVORITES_FILTER, `${t('positionFavorites')} (${positions.filter(item => state.positionFavorites.has(item.id)).length})`);
        groups.forEach(group => appendFilter(group.id, optionText(group)));
        elements.positionFilters.replaceChildren(fragment);
    }

    function renderDefectPositionPicker() {
        renderDefectPositionFilters();
        const positions = normalizeArray(state.catalog?.defectPositions)
            .filter(item => state.positionGroupFilter === ALL_GROUPS ||
                (state.positionGroupFilter === FAVORITES_FILTER ? state.positionFavorites.has(item.id) : item.positionGroupId === state.positionGroupFilter))
            .sort((left, right) => Number(state.positionFavorites.has(right.id)) - Number(state.positionFavorites.has(left.id)) ||
                uqqcCollator.compare(optionText(left), optionText(right)) ||
                uqqcCollator.compare(String(left.id || ''), String(right.id || '')));
        if (!positions.length) {
            const empty = document.createElement('p');
            empty.className = 'col-12 text-muted';
            empty.textContent = t(state.positionGroupFilter === FAVORITES_FILTER ? 'noFavoritePositions' : 'noDefectPositions');
            elements.positionGrid.replaceChildren(empty);
            return;
        }

        const fragment = document.createDocumentFragment();
        positions.forEach(position => {
            const favorite = state.positionFavorites.has(position.id);
            const card = document.createElement('article');
            card.className = `uqqc-position-card${favorite ? ' uqqc-is-favorite' : ''}`;
            const content = document.createElement('div');
            content.className = 'frappe-card h-100 p-2 d-flex flex-column';
            const meta = document.createElement('div');
            meta.className = 'uqqc-position-card-tools d-flex align-items-center justify-content-end';
            const star = document.createElement('button');
            star.type = 'button';
            star.className = `uqqc-position-favorite-button btn btn-default btn-xs${favorite ? ' active text-warning' : ''}`;
            star.dataset.positionId = String(position.id);
            star.textContent = favorite ? '\u2605' : '\u2606';
            star.setAttribute('aria-pressed', String(favorite));
            star.setAttribute('aria-label', `${t(favorite ? 'unfavoritePosition' : 'favoritePosition')}: ${optionText(position)}`);
            star.title = t(favorite ? 'unfavoritePosition' : 'favoritePosition');
            star.addEventListener('click', event => {
                event.stopPropagation();
                if (favorite) state.positionFavorites.delete(position.id); else state.positionFavorites.add(position.id);
                writeJson(keys.positionFavorites, [...state.positionFavorites]);
                renderDefectPositionPicker();
                const stars = elements.positionGrid.querySelectorAll('.uqqc-position-favorite-button');
                const sameStar = [...stars].find(button => button.dataset.positionId === String(position.id));
                (sameStar || elements.positionFilters.querySelector('.uqqc-is-active') || elements.positionFilters.querySelector('button'))?.focus();
            });
            meta.append(star);
            const nameButton = document.createElement('button');
            nameButton.type = 'button';
            nameButton.className = 'uqqc-defect-name btn btn-default btn-block text-center text-wrap d-flex align-items-center justify-content-center flex-grow-1';
            const positionCode = position.code || t('notAvailable');
            const positionName = position.name ? String(position.name).toLocaleUpperCase('vi') : '';
            nameButton.textContent = positionName ? `${positionCode} - ${positionName}` : positionCode;
            nameButton.addEventListener('click', () => selectDefectPosition(position.id));
            content.append(meta, nameButton);
            card.appendChild(content);
            fragment.appendChild(card);
        });
        elements.positionGrid.replaceChildren(fragment);
    }

    function openDefectPositionPicker(defectId) {
        if (!scopeComplete()) return;
        state.activeDefectId = defectId;
        state.positionGroupFilter = ALL_GROUPS;
        renderDefectPositionPicker();
        setPanelVisibility(elements.positionPanel, true);
        window.setTimeout(() => elements.positionGrid.querySelector('.uqqc-scope-picker-option')?.focus(), 0);
    }

    function closeDefectPositionPicker() {
        const defectId = state.activeDefectId;
        setPanelVisibility(elements.positionPanel, false);
        state.activeDefectId = '';
        elements.defectGrid.querySelector(`[data-defect-id="${defectId}"]`)?.focus();
    }

    function selectDefectPosition(defectPositionId) {
        const defectId = state.activeDefectId;
        closeDefectPositionPicker();
        queueDefect(defectId, defectPositionId);
    }

    function renderScopeControls() {
        if (!state.catalog || !state.device) return;
        const approved = isApproved();
        const variants = validVariants();
        const lines = normalizeArray(state.catalog.lines).filter(line => line.companyId === state.device.companyId);
        state.scopeOptions.line = lines;
        state.scope.lineId = fillSelect(elements.line, lines, 'selectLine', state.scope.lineId, approved, 'line');

        const products = distinctOptions(variants.map(item => item.productId), state.catalog.products);
        state.scopeOptions.product = products;
        state.scope.productId = fillSelect(elements.product, products, 'selectProduct', state.scope.productId, approved && Boolean(state.scope.lineId), 'product');

        const markets = distinctOptions(
            variants.filter(item => item.productId === state.scope.productId).map(item => item.marketId),
            state.catalog.markets);
        state.scopeOptions.market = markets;
        state.scope.marketId = fillSelect(elements.market, markets, 'selectMarket', state.scope.marketId, approved && Boolean(state.scope.productId), 'market');

        const colors = distinctOptions(
            variants.filter(item => item.productId === state.scope.productId && item.marketId === state.scope.marketId).map(item => item.colorId),
            state.catalog.colors);
        state.scopeOptions.color = colors;
        state.scope.colorId = fillSelect(elements.color, colors, 'selectColor', state.scope.colorId, approved && Boolean(state.scope.marketId), 'color');

        const sizes = distinctOptions(
            variants.filter(item => item.productId === state.scope.productId && item.marketId === state.scope.marketId && item.colorId === state.scope.colorId).map(item => item.sizeId),
            state.catalog.sizes);
        state.scopeOptions.size = sizes;
        state.scope.sizeId = fillSelect(elements.size, sizes, 'selectSize', state.scope.sizeId, approved && Boolean(state.scope.colorId), 'size');

        persistScope();
        updateScopePickerButtons();
        renderQuickFilters();
        renderDefects();
        if (scopeComplete()) void refreshSnapshot();
    }

    function scopeComplete() {
        if (!isApproved()) return false;
        const scope = state.scope;
        if (!scope.lineId || !scope.productId || !scope.colorId || !scope.sizeId || !scope.marketId) return false;
        return validVariants().some(variant => variant.productId === scope.productId && variant.colorId === scope.colorId &&
            variant.sizeId === scope.sizeId && variant.marketId === scope.marketId);
    }

    function queueMatchesScope(event) {
        const scope = state.scope;
        return event.serverDateKey === state.catalog?.serverDateKey && event.lineId === scope.lineId &&
            event.productId === scope.productId && event.colorId === scope.colorId &&
            event.sizeId === scope.sizeId && event.marketId === scope.marketId;
    }

    function effectiveDefects() {
        const values = { ...(state.serverSnapshot.defects || {}) };
        state.queue.filter(event => event.eventKind === 'defect' && queueMatchesScope(event))
            .forEach(event => { values[event.defectId] = (values[event.defectId] || 0) + 1; });
        return values;
    }

    function effectivePass() {
        const pendingPass = state.queue.filter(event => event.eventKind === 'pass' && queueMatchesScope(event)).length;
        return Math.max(0, Number(state.serverSnapshot.pass || 0) + pendingPass);
    }

    function effectiveRework() {
        const pendingRework = state.queue.filter(event => event.eventKind === 'rework' && queueMatchesScope(event)).length;
        return Math.max(0, Number(state.serverSnapshot.rework || 0) + pendingRework);
    }

    function effectiveMetrics() {
        const defects = effectiveDefects();
        const defectNo = Object.values(defects).reduce((sum, value) => sum + Number(value || 0), 0);
        const serverPieceIds = new Set(normalizeArray(state.serverSnapshot.defectPieceIds).map(value => String(value).toLowerCase()));
        const serverDefectPcs = Math.max(0, Number(state.serverSnapshot.defectPcs ?? state.serverSnapshot.totalDefects ?? 0));
        const legacyPieceCount = Math.max(0, serverDefectPcs - serverPieceIds.size);
        state.queue.filter(event => event.eventKind === 'defect' && queueMatchesScope(event)).forEach(event => {
            serverPieceIds.add(event.defectPieceId ? String(event.defectPieceId).toLowerCase() : `event:${event.localEventId}`);
        });
        const passed = effectivePass();
        const rework = effectiveRework();
        const total = passed + rework;
        const defectPcs = legacyPieceCount + serverPieceIds.size;
        const rftTotal = passed + defectPcs;
        return {
            defects,
            passed,
            rework,
            total,
            passRate: rftTotal <= 0 ? 0 : (passed * 100) / rftTotal,
            defectPcs,
            defectNo
        };
    }

    function detailRows() {
        if (!isApproved() || !state.catalog) return [];
        pruneDetailSnapshots();
        const totalsByProductLine = new Map();
        Object.values(state.detailSnapshots.scopes).forEach(entry => {
            const scope = entry?.scope;
            if (!scope?.lineId || !scope?.productId || !scope?.colorId || !scope?.sizeId || !scope?.marketId) return;
            const snapshot = entry.snapshot || {};
            const key = `${scope.productId}|${scope.lineId}`;
            const totals = totalsByProductLine.get(key) || { productId: scope.productId, lineId: scope.lineId, pass: 0, rework: 0, defectNo: 0 };
            totals.pass += Math.max(0, Number(snapshot.pass || 0));
            totals.rework += Math.max(0, Number(snapshot.rework || 0));
            totals.defectNo += Math.max(0, Number(snapshot.defectNo || 0));
            totalsByProductLine.set(key, totals);
        });
        state.queue.filter(event => event.serverDateKey === state.catalog.serverDateKey).forEach(event => {
            if (!event.productId || !event.lineId) return;
            const key = `${event.productId}|${event.lineId}`;
            const totals = totalsByProductLine.get(key) || { productId: event.productId, lineId: event.lineId, pass: 0, rework: 0, defectNo: 0 };
            if (event.eventKind === 'pass') totals.pass += 1;
            else if (event.eventKind === 'rework') totals.rework += 1;
            else if (event.eventKind === 'defect') totals.defectNo += Math.max(0, Number(event.quantityDelta || 1));
            totalsByProductLine.set(key, totals);
        });

        const products = new Map(normalizeArray(state.catalog.products).map(item => [item.id, item]));
        const lines = new Map(normalizeArray(state.catalog.lines).map(item => [item.id, item]));
        return [...totalsByProductLine.values()].filter(totals =>
            totals.pass > 0 || totals.rework > 0 || totals.defectNo > 0).map(totals => {
            const product = products.get(totals.productId);
            const line = lines.get(totals.lineId);
            const inspected = totals.pass + totals.defectNo;
            return {
                ...totals, inspected,
                productLabel: product?.code || product?.name || t('notAvailable'),
                lineLabel: line?.code || line?.name || t('notAvailable')
            };
        }).sort((a, b) => a.productLabel.localeCompare(b.productLabel) ||
            a.lineLabel.localeCompare(b.lineLabel));
    }

    function fillDetailFilter(select, options, allLabel, selected) {
        const fragment = document.createDocumentFragment();
        const all = document.createElement('option');
        all.value = '';
        all.textContent = t(allLabel);
        fragment.appendChild(all);
        [...options.entries()].sort((a, b) => a[1].localeCompare(b[1])).forEach(([id, label]) => {
            const option = document.createElement('option');
            option.value = id;
            option.textContent = label;
            fragment.appendChild(option);
        });
        select.replaceChildren(fragment);
        select.value = options.has(selected) ? selected : '';
        return select.value;
    }

    function renderDetail() {
        const rows = detailRows();
        const loading = Boolean(state.detailHydrationPromise);
        elements.detailStatus.textContent = loading ? t('detailRestoring') : state.detailError;
        elements.detailStatus.hidden = !loading && !state.detailError;
        elements.detailRetry.hidden = !state.detailError;
        elements.detailRetry.disabled = loading;
        elements.detailFoot.hidden = !rows.length && (loading || Boolean(state.detailError));
        const filters = state.detailFilters;
        filters.productId = fillDetailFilter(elements.detailProduct,
            new Map(rows.map(row => [row.productId, row.productLabel])),
            'detailAllProducts', filters.productId);
        filters.lineId = fillDetailFilter(elements.detailLine,
            new Map(rows.map(row => [row.lineId, row.lineLabel])),
            'detailAllLines', filters.lineId);
        const visible = rows.filter(row => (!filters.productId || row.productId === filters.productId) &&
            (!filters.lineId || row.lineId === filters.lineId));
        const body = document.createDocumentFragment();
        if (!visible.length) {
            const row = document.createElement('tr');
            const cell = document.createElement('td');
            cell.colSpan = 7;
            cell.className = 'text-muted text-center';
            cell.textContent = loading ? t('detailRestoring') :
                (state.detailError && !hasDetailCache() ? t('detailRestoreUnavailable') : t('detailEmpty'));
            row.appendChild(cell);
            body.appendChild(row);
        } else {
            visible.forEach(item => {
                const row = document.createElement('tr');
                const rate = item.inspected > 0 ? (item.defectNo * 100 / item.inspected).toFixed(1) : '0.0';
                [item.productLabel, item.lineLabel, String(item.inspected), String(item.pass), String(item.rework),
                    String(item.defectNo), `${rate}%`].forEach(value => {
                    const cell = document.createElement('td');
                    cell.textContent = value;
                    row.appendChild(cell);
                });
                body.appendChild(row);
            });
        }
        elements.detailBody.replaceChildren(body);

        const inspected = visible.reduce((sum, item) => sum + item.inspected, 0);
        const pass = visible.reduce((sum, item) => sum + item.pass, 0);
        const rework = visible.reduce((sum, item) => sum + item.rework, 0);
        const defectNo = visible.reduce((sum, item) => sum + item.defectNo, 0);
        const rate = inspected > 0 ? (defectNo * 100 / inspected).toFixed(1) : '0.0';
        const totalRow = document.createElement('tr');
        const totalLabel = document.createElement('th');
        totalLabel.colSpan = 2;
        totalLabel.scope = 'row';
        totalLabel.textContent = t('detailTotal');
        totalRow.appendChild(totalLabel);
        [String(inspected), String(pass), String(rework), String(defectNo), `${rate}%`].forEach(value => {
            const cell = document.createElement('td');
            cell.textContent = value;
            totalRow.appendChild(cell);
        });
        elements.detailFoot.replaceChildren(totalRow);
    }

    function renderDetailIfOpen() {
        if (elements.detailPanel.classList.contains('open')) renderDetail();
    }

    function openDetailPanel() {
        syncServerDay();
        renderDetail();
        setPanelVisibility(elements.detailPanel, true);
        elements.detailClose.focus();
        if (!state.detailHydrated || state.detailError) void hydrateDetailSnapshots();
    }

    function closeDetailPanel() {
        setPanelVisibility(elements.detailPanel, false);
        elements.detailOpen.focus();
    }

    function renderTotals(metrics, enabled) {
        const activePiece = Boolean(state.activePiece);
        elements.pass.closest('.row.no-gutters')?.classList.add('uqqc-metrics-grid');
        elements.pass.textContent = String(metrics.passed);
        elements.rework.textContent = String(metrics.rework);
        elements.inspectionTotal.textContent = String(metrics.total);
        elements.passRate.textContent = `${metrics.passRate.toFixed(1)}%`;
        elements.defectPcs.textContent = String(metrics.defectPcs);
        elements.defectNo.textContent = String(metrics.defectNo);
        elements.confirmPass.disabled = !enabled || activePiece || state.clearingCache;
        elements.confirmRework.disabled = !enabled || activePiece || state.clearingCache;
    }

    let suppressNextDefectClick = false;
    let pointerDefectDrag = null;
    let defectPointerDocListenersActive = false;

    function syncDefectArrangeChrome() {
        const on = Boolean(state.defectArrangeMode);
        elements.defectGrid.classList.toggle('uqqc-arrange-mode', on);
        if (elements.arrangeToggle) {
            elements.arrangeToggle.setAttribute('aria-pressed', on ? 'true' : 'false');
            elements.arrangeToggle.classList.toggle('active', on);
        }
        if (elements.arrangeToggleLabel) {
            elements.arrangeToggleLabel.textContent = on
                ? t('arrangeModeOn')
                : t('arrangeModeOff');
        }
    }

    function isNarrowDefectReorderViewport() {
        return typeof window !== 'undefined' &&
            window.matchMedia?.('(max-width: 980px), (pointer: coarse)')?.matches;
    }

    function defectCardsUseHtmlDrag() {
        return !isNarrowDefectReorderViewport();
    }

    function reorderVisibleDefects(sourceId, targetId) {
        if (!sourceId || !targetId || sourceId === targetId) return false;
        const visibleIds = [...elements.defectGrid.querySelectorAll('.uqqc-defect-card')]
            .map(card => card.dataset.defectId)
            .filter(Boolean);
        const fromIndex = visibleIds.indexOf(sourceId);
        const toIndex = visibleIds.indexOf(targetId);
        if (fromIndex < 0 || toIndex < 0) return false;

        visibleIds.splice(fromIndex, 1);
        visibleIds.splice(toIndex, 0, sourceId);
        const visibleSet = new Set(visibleIds);
        const hiddenIds = state.order.filter(id => !visibleSet.has(id));
        state.order = [...visibleIds, ...hiddenIds];
        writeJson(keys.order, state.order);
        return true;
    }

    function shiftVisibleDefectOneStep(defectId, direction) {
        if (!defectId || (direction !== 1 && direction !== -1)) return false;
        const visibleIds = [...elements.defectGrid.querySelectorAll('.uqqc-defect-card')]
            .map(card => card.dataset.defectId)
            .filter(Boolean);
        const fromIndex = visibleIds.indexOf(defectId);
        if (fromIndex < 0) return false;
        const neighborIndex = fromIndex + direction;
        if (neighborIndex < 0 || neighborIndex >= visibleIds.length) return false;
        return reorderVisibleDefects(defectId, visibleIds[neighborIndex]);
    }

    function cleanupDefectDragClasses() {
        elements.defectGrid.classList.remove('uqqc-drag-active');
        elements.defectGrid.querySelectorAll('.uqqc-defect-card.dragging, .uqqc-defect-card.uqqc-drag-over').forEach(card => {
            card.classList.remove('dragging', 'uqqc-drag-over');
        });
    }

    function handleDefectDragStart(event) {
        if (!state.defectArrangeMode) {
            event.preventDefault();
            return;
        }
        const card = event.target.closest('.uqqc-defect-card');
        if (!card || event.target.closest('.uqqc-favorite-button') || event.target.closest('.uqqc-defect-shift-btn')) {
            event.preventDefault();
            return;
        }
        event.dataTransfer.effectAllowed = 'move';
        event.dataTransfer.setData('text/plain', card.dataset.defectId || '');
        card.classList.add('dragging');
        elements.defectGrid.classList.add('uqqc-drag-active');
    }

    function handleDefectDragOver(event) {
        if (!state.defectArrangeMode) return;
        const target = event.target.closest('.uqqc-defect-card');
        if (!target || target.classList.contains('dragging')) return;
        event.preventDefault();
        event.dataTransfer.dropEffect = 'move';
        elements.defectGrid.querySelectorAll('.uqqc-defect-card.uqqc-drag-over').forEach(card => card.classList.remove('uqqc-drag-over'));
        target.classList.add('uqqc-drag-over');
    }

    function handleDefectDragLeave(event) {
        const target = event.target.closest('.uqqc-defect-card');
        if (target && !target.contains(event.relatedTarget)) {
            target.classList.remove('uqqc-drag-over');
        }
    }

    function handleDefectDrop(event) {
        if (!state.defectArrangeMode) return;
        const target = event.target.closest('.uqqc-defect-card');
        const sourceId = event.dataTransfer.getData('text/plain');
        const targetId = target?.dataset.defectId;
        if (!sourceId || !targetId) return;
        event.preventDefault();
        if (reorderVisibleDefects(sourceId, targetId)) {
            suppressNextDefectClick = true;
            renderDefects();
        }
    }

    function handleDefectDragEnd() {
        cleanupDefectDragClasses();
    }

    function detachDefectPointerDocumentListeners() {
        if (!defectPointerDocListenersActive) return;
        document.removeEventListener('pointermove', onDefectReorderPointerMove, { capture: true });
        document.removeEventListener('pointerup', onDefectReorderPointerUp, { capture: true });
        document.removeEventListener('pointercancel', onDefectReorderPointerUp, { capture: true });
        defectPointerDocListenersActive = false;
    }

    function attachDefectPointerDocumentListeners() {
        detachDefectPointerDocumentListeners();
        document.addEventListener('pointermove', onDefectReorderPointerMove, { passive: false, capture: true });
        document.addEventListener('pointerup', onDefectReorderPointerUp, { capture: true });
        document.addEventListener('pointercancel', onDefectReorderPointerUp, { capture: true });
        defectPointerDocListenersActive = true;
    }

    function onDefectReorderPointerMove(event) {
        if (!pointerDefectDrag || pointerDefectDrag.pointerId !== event.pointerId) return;
        const distance = Math.hypot(event.clientX - pointerDefectDrag.startX, event.clientY - pointerDefectDrag.startY);
        if (!pointerDefectDrag.dragging && Date.now() < pointerDefectDrag.readyAt && distance < 18) return;
        if (!pointerDefectDrag.dragging && distance < 10) return;

        event.preventDefault();
        if (!pointerDefectDrag.dragging) {
            pointerDefectDrag.dragging = true;
            suppressNextDefectClick = true;
            pointerDefectDrag.card.classList.add('dragging');
            elements.defectGrid.classList.add('uqqc-drag-active');
        }

        const target = document.elementFromPoint(event.clientX, event.clientY)?.closest('.uqqc-defect-card');
        elements.defectGrid.querySelectorAll('.uqqc-defect-card.uqqc-drag-over').forEach(c => c.classList.remove('uqqc-drag-over'));
        if (target && target.dataset.defectId !== pointerDefectDrag.id) {
            target.classList.add('uqqc-drag-over');
        }
    }

    function onDefectReorderPointerUp(event) {
        if (!pointerDefectDrag || pointerDefectDrag.pointerId !== event.pointerId) return;
        const target = document.elementFromPoint(event.clientX, event.clientY)?.closest('.uqqc-defect-card');
        const draggedCard = pointerDefectDrag.card;
        const didReorder = pointerDefectDrag.dragging && reorderVisibleDefects(pointerDefectDrag.id, target?.dataset.defectId);

        detachDefectPointerDocumentListeners();
        try { draggedCard.releasePointerCapture?.(event.pointerId); } catch (_) { /* noop */ }
        pointerDefectDrag = null;
        cleanupDefectDragClasses();

        if (didReorder) {
            renderDefects();
        }
    }

    function handleDefectPointerDown(event) {
        if (event.button !== 0 || event.target.closest('.uqqc-favorite-button') || !state.defectArrangeMode || event.target.closest('.uqqc-defect-shift-btn')) return;
        if (defectCardsUseHtmlDrag()) return;
        const card = event.target.closest('.uqqc-defect-card');
        if (!card) return;

        pointerDefectDrag = {
            id: card.dataset.defectId,
            pointerId: event.pointerId,
            startX: event.clientX,
            startY: event.clientY,
            card,
            readyAt: Date.now() + 180,
            dragging: false
        };
        attachDefectPointerDocumentListeners();
        try { card.setPointerCapture?.(event.pointerId); } catch (_) { /* noop */ }
    }

    function handleDefectPointerCancel(event) {
        if (!pointerDefectDrag || pointerDefectDrag.pointerId !== event.pointerId) return;
        try { pointerDefectDrag.card.releasePointerCapture?.(event.pointerId); } catch (_) { /* noop */ }
        pointerDefectDrag = null;
        detachDefectPointerDocumentListeners();
        cleanupDefectDragClasses();
    }

    function toggleArrangeMode() {
        state.defectArrangeMode = !state.defectArrangeMode;
        localStorage.setItem(keys.arrangeMode, state.defectArrangeMode ? 'true' : 'false');
        if (!state.defectArrangeMode) {
            pointerDefectDrag = null;
            detachDefectPointerDocumentListeners();
            cleanupDefectDragClasses();
        }
        renderDefects();
        syncDefectArrangeChrome();
    }

    function defectGroups() {
        const groups = new Map();
        normalizeArray(state.catalog?.defects).forEach(defect => {
            const code = String(defect.groupCode || '').trim();
            if (code && !groups.has(code)) groups.set(code, defect.groupName || code);
        });
        return groups;
    }

    function renderQuickFilters() {
        const allDefects = normalizeArray(state.catalog?.defects);
        const groups = defectGroups();
        const validFilterKeys = new Set([ALL_GROUPS, FAVORITES_FILTER, ...groups.keys()]);
        if (!validFilterKeys.has(state.groupFilter)) {
            state.groupFilter = ALL_GROUPS;
            localStorage.setItem(keys.groupFilter, ALL_GROUPS);
        }

        const fragment = document.createDocumentFragment();
        const allDefectsLabel = t('tabAllDefects') || 'Tất cả lỗi';
        const favoritesLabel = t('tabFavorites') || 'Yêu thích';

        const filterItems = [
            { code: ALL_GROUPS, label: `${allDefectsLabel} (${allDefects.length})` },
            { code: FAVORITES_FILTER, label: `${favoritesLabel} (${allDefects.filter(d => state.favorites.has(d.id)).length})` },
            ...Array.from(groups.entries())
                .sort(([leftCode, leftName], [rightCode, rightName]) =>
                    uqqcCollator.compare(leftCode, rightCode) || uqqcCollator.compare(leftName, rightName))
                .map(([code, groupName]) => {
                const count = allDefects.filter(d => d.groupCode === code).length;
                return {
                    code,
                    label: `${groupName || t('notAvailable')} (${count})`
                };
            })
        ];

        filterItems.forEach(item => {
            const button = document.createElement('button');
            button.type = 'button';
            button.className = `uqqc-filter-chip btn btn-default btn-sm mr-2 mb-1${state.groupFilter === item.code ? ' active' : ''}`;
            button.textContent = item.label;
            button.addEventListener('click', () => {
                ensureFullscreen();
                state.groupFilter = item.code;
                localStorage.setItem(keys.groupFilter, item.code);
                renderQuickFilters();
                renderDefects();
            });
            fragment.appendChild(button);
        });
        elements.quickFilters.replaceChildren(fragment);
    }

    function orderedDefects() {
        const allDefects = normalizeArray(state.catalog?.defects);
        const defects = allDefects.filter(defect => {
            if (state.groupFilter === ALL_GROUPS) return true;
            if (state.groupFilter === FAVORITES_FILTER) return state.favorites.has(defect.id);
            return defect.groupCode === state.groupFilter;
        });

        const alphabetical = (a, b) => uqqcCollator.compare(a.groupCode || '', b.groupCode || '') ||
            uqqcCollator.compare(a.code || '', b.code || '') ||
            uqqcCollator.compare(a.name || '', b.name || '');
        if (!state.order.length) {
            state.order = allDefects.slice().sort(alphabetical).map(item => item.id);
            writeJson(keys.order, state.order);
        }
        const orderMap = new Map(state.order.map((id, index) => [id, index]));
        return defects.sort((a, b) => {
            const favoriteOrder = Number(state.favorites.has(b.id)) - Number(state.favorites.has(a.id));
            if (favoriteOrder) return favoriteOrder;
            if (state.defectArrangeMode) {
                const indexA = orderMap.has(a.id) ? orderMap.get(a.id) : Number.MAX_SAFE_INTEGER;
                const indexB = orderMap.has(b.id) ? orderMap.get(b.id) : Number.MAX_SAFE_INTEGER;
                if (indexA !== indexB) return indexA - indexB;
            }
            return alphabetical(a, b);
        });
    }

    function renderDefects() {
        const enabled = scopeComplete();
        elements.scopeHint.textContent = enabled ? '' : t('selectScope');
        const metrics = effectiveMetrics();
        const counts = metrics.defects;
        renderTotals(metrics, enabled);
        const defects = orderedDefects();
        if (!defects.length) {
            const empty = document.createElement('p');
            empty.className = 'col-12 text-muted';
            empty.textContent = t('noDefects');
            elements.defectGrid.replaceChildren(empty);
            syncDefectArrangeChrome();
            renderDetailIfOpen();
            return;
        }

        const fragment = document.createDocumentFragment();
        const arrange = Boolean(state.defectArrangeMode);

        defects.forEach((defect, idx) => {
            const card = document.createElement('article');
            const favorite = state.favorites.has(defect.id);
            const isFirst = idx === 0;
            const isLast = idx === defects.length - 1;

            card.className = `uqqc-defect-card col-6 col-sm-4 col-md-3 col-lg-3 col-xl-2 col-2xl-2 px-1 mb-2${favorite ? ' uqqc-is-favorite' : ''}${enabled ? '' : ' uqqc-is-disabled'}${arrange ? ' uqqc-defect-card--arrange' : ''}`;
            card.dataset.defectId = defect.id;
            card.draggable = Boolean(arrange && defectCardsUseHtmlDrag());

            const meta = document.createElement('div');
            meta.className = 'd-flex align-items-center';

            const codeSpan = document.createElement('span');
            codeSpan.className = 'uqqc-defect-code';
            codeSpan.textContent = `${defect.groupCode || '-'} - `;
            const code = document.createElement('strong');
            code.textContent = defect.code;
            codeSpan.appendChild(code);

            const countSpan = document.createElement('span');
            countSpan.className = 'badge badge-secondary ml-2';
            countSpan.textContent = String(counts[defect.id] || 0);

            const favoriteBtn = document.createElement('button');
            favoriteBtn.type = 'button';
            favoriteBtn.className = `uqqc-favorite-button btn btn-default btn-xs ml-auto${favorite ? ' active text-warning' : ''}`;
            favoriteBtn.dataset.defectId = defect.id;
            favoriteBtn.innerHTML = favorite ? '&#9733;' : '&#9734;';
            favoriteBtn.setAttribute('aria-label', t(favorite ? 'unfavorite' : 'favorite'));
            favoriteBtn.title = t(favorite ? 'unfavorite' : 'favorite');

            meta.append(codeSpan, countSpan, favoriteBtn);

            const nameDiv = document.createElement('button');
            nameDiv.type = 'button';
            nameDiv.disabled = !enabled;
            nameDiv.className = 'uqqc-defect-name btn btn-default btn-block text-center text-wrap mt-2 flex-grow-1';
            nameDiv.textContent = String(defect.name || '').toLocaleUpperCase('vi');

            const content = document.createElement('div');
            content.className = 'frappe-card h-100 p-2 d-flex flex-column';
            content.append(meta, nameDiv);
            card.appendChild(content);

            if (arrange) {
                const shiftRow = document.createElement('div');
                shiftRow.className = 'btn-group btn-group-sm d-flex mt-2';
                shiftRow.setAttribute('role', 'group');
                shiftRow.setAttribute('aria-label', t('reorderActions'));

                const prevBtn = document.createElement('button');
                prevBtn.type = 'button';
                prevBtn.className = 'uqqc-defect-shift-btn btn btn-default flex-fill';
                prevBtn.dataset.shift = '-1';
                prevBtn.disabled = isFirst;
                prevBtn.innerHTML = '&#8249;';
                prevBtn.setAttribute('aria-label', t('movePrevious'));

                const nextBtn = document.createElement('button');
                nextBtn.type = 'button';
                nextBtn.className = 'uqqc-defect-shift-btn btn btn-default flex-fill';
                nextBtn.dataset.shift = '1';
                nextBtn.disabled = isLast;
                nextBtn.innerHTML = '&#8250;';
                nextBtn.setAttribute('aria-label', t('moveNext'));

                shiftRow.append(prevBtn, nextBtn);
                content.append(shiftRow);
            }

            fragment.appendChild(card);
        });
        elements.defectGrid.replaceChildren(fragment);
        syncDefectArrangeChrome();
        renderDetailIfOpen();
    }

    function toggleFavorite(defectId) {
        if (!defectId) return;
        if (state.favorites.has(defectId)) state.favorites.delete(defectId); else state.favorites.add(defectId);
        writeJson(keys.favorites, [...state.favorites]);
        renderQuickFilters();
        renderDefects();
    }

    function queueDefect(defectId, defectPositionId) {
        if (state.clearingCache) return;
        syncServerDay();
        if (!scopeComplete() || !defectId || !defectPositionId) return;
        const previousPiece = state.activePiece ? { ...state.activePiece } : null;
        if (!activePieceMatchesScope(state.activePiece)) {
            state.activePiece = {
                serverDateKey: state.catalog.serverDateKey,
                scope: { ...state.scope },
                defectPieceId: createId(),
                decisionPending: true
            };
        } else {
            state.activePiece.decisionPending = true;
        }
        state.queue.push({
            localEventId: createId(),
            ...state.scope,
            eventKind: 'defect',
            schemaVersion: 2,
            defectId,
            defectPositionId,
            defectPieceId: state.activePiece.defectPieceId,
            quantityDelta: 1,
            occurredAt: new Date().toISOString(),
            serverDateKey: state.catalog.serverDateKey
        });
        if (!writeJson(keys.queue, state.queue)) {
            state.queue.pop();
            state.activePiece = previousPiece;
            showToast(t('storageUnavailable'), true);
            return;
        }
        persistActivePiece();
        updatePending();
        renderDefects();
        openMoreDefectDialog();
        void syncQueue();
    }

    function openMoreDefectDialog() {
        if (!state.activePiece?.decisionPending) return;
        setPanelVisibility(elements.moreDefectPanel, true);
    }

    function closeMoreDefectDialog() {
        setPanelVisibility(elements.moreDefectPanel, false);
    }

    function answerMoreDefect(continuePiece) {
        if (!state.activePiece) {
            closeMoreDefectDialog();
            return;
        }
        if (continuePiece) {
            state.activePiece.decisionPending = false;
            persistActivePiece();
        } else {
            state.activePiece = null;
            persistActivePiece();
        }
        closeMoreDefectDialog();
        renderDefects();
    }

    function queueQuantity(eventKind) {
        if (state.clearingCache) return;
        syncServerDay();
        if (!scopeComplete() || state.activePiece) return;
        state.queue.push({
            localEventId: createId(),
            ...state.scope,
            eventKind,
            occurredAt: new Date().toISOString(),
            serverDateKey: state.catalog.serverDateKey
        });
        if (!writeJson(keys.queue, state.queue)) {
            state.queue.pop();
            showToast(t('storageUnavailable'), true);
            return;
        }
        updatePending();
        renderDefects();
        void syncQueue();
    }

    function queuePass() { queueQuantity('pass'); }

    function queueRework() { queueQuantity('rework'); }

    function syncQueue() {
        if (state.syncPromise) return state.syncPromise;
        if (state.detailHydrationPromise) return state.detailHydrationPromise.then(() => syncQueue());
        const operation = syncQueuedBatch();
        state.syncPromise = operation;
        return operation.finally(() => {
            if (state.syncPromise === operation) state.syncPromise = null;
        });
    }

    async function syncQueuedBatch() {
        if (state.syncing || !canReachApi() || !isApproved() || !state.queue.length) return;
        state.syncing = true;
        try {
            const batch = state.queue.slice(0, 200);
            const defectEvents = batch
                .filter(event => event.eventKind === 'defect')
                .map(({ serverDateKey, eventKind, ...event }) => event);
            const passEvents = batch
                .filter(event => event.eventKind === 'pass')
                .map(event => ({
                    localEventId: event.localEventId,
                    lineId: event.lineId,
                    productId: event.productId,
                    colorId: event.colorId,
                    sizeId: event.sizeId,
                    marketId: event.marketId,
                    occurredAt: event.occurredAt
                }));
            const reworkEvents = batch
                .filter(event => event.eventKind === 'rework')
                .map(event => ({
                    localEventId: event.localEventId,
                    lineId: event.lineId,
                    productId: event.productId,
                    colorId: event.colorId,
                    sizeId: event.sizeId,
                    marketId: event.marketId,
                    occurredAt: event.occurredAt
                }));
            const data = await requestJson('/api/method/uqqc-inspections-sync', {
                method: 'POST',
                body: JSON.stringify({
                    id: state.device.id,
                    events: defectEvents,
                    passEvents,
                    reworkEvents
                })
            });
            const accepted = new Set(data.acceptedLocalEventIds || []);
            const acceptedEvents = batch.filter(event => accepted.has(event.localEventId));
            state.queue = state.queue.filter(event => !accepted.has(event.localEventId));
            writeJson(keys.queue, state.queue);
            state.lastSync = new Date().toLocaleTimeString();
            localStorage.setItem(keys.lastSync, state.lastSync);
            updatePending();
            renderSettingsState();
            const acceptedScopes = new Map();
            acceptedEvents.filter(event => event.serverDateKey === state.catalog?.serverDateKey).forEach(event => {
                const key = detailScopeKey(event);
                if (!acceptedScopes.has(key)) {
                    acceptedScopes.set(key, {
                        scope: {
                            lineId: event.lineId, productId: event.productId, colorId: event.colorId,
                            sizeId: event.sizeId, marketId: event.marketId
                        },
                        events: []
                    });
                }
                acceptedScopes.get(key).events.push(event);
            });
            let currentScopeRefreshed = false;
            for (const [key, group] of acceptedScopes) {
                try {
                    const snapshot = await requestJson('/api/method/uqqc-inspections-snapshot', {
                        method: 'POST',
                        body: JSON.stringify({ id: state.device.id, ...group.scope })
                    });
                    updateServerClock(snapshot.serverNowUtc);
                    if (snapshot.serverDateKey !== state.catalog?.serverDateKey) {
                        syncServerDay();
                        continue;
                    }
                    saveDetailSnapshot(group.scope, snapshot);
                    if (scopeComplete() && key === detailScopeKey(state.scope)) {
                        state.serverSnapshot = snapshot;
                        currentScopeRefreshed = true;
                    }
                } catch {
                    addAcceptedEventsToDetailSnapshot(group.scope, group.events);
                }
            }
            if (scopeComplete() && !currentScopeRefreshed) await refreshSnapshot(); else renderDefects();
        } catch (error) {
            if (!error.retryable) {
                appendSyncError(error?.message || t('syncFailed'));
                renderSettingsState();
                showToast(t('syncFailed'), true);
            }
        } finally {
            state.syncing = false;
        }
        if (state.queue.length && canReachApi()) window.setTimeout(syncQueue, 1200);
    }

    async function manualSync() {
        if (state.syncing) return;
        if (!navigator.onLine) {
            appendSyncError(t('offline'));
            renderSettingsState();
            showToast(t('offline'), true);
            return;
        }
        if (!canReachApi()) {
            appendSyncError(t('apiDisconnected'));
            renderSettingsState();
            showToast(t('apiDisconnected'), true);
            return;
        }
        if (!isApproved()) {
            appendSyncError(t('pendingApproval'));
            renderSettingsState();
            showToast(t('pendingApproval'), true);
            return;
        }

        elements.syncNowButton.disabled = true;
        const labelSpan = elements.syncNowButton.querySelector('span');
        const originalText = labelSpan ? labelSpan.textContent : '';
        if (labelSpan) labelSpan.textContent = t('syncing');

        try {
            if (state.queue.length) {
                await syncQueue();
            } else if (scopeComplete()) {
                await refreshSnapshot();
            }
            state.lastSync = new Date().toLocaleTimeString();
            localStorage.setItem(keys.lastSync, state.lastSync);
            renderSettingsState();
            showToast(t('syncSuccess'));
        } catch (error) {
            appendSyncError(error?.message || t('syncFailed'));
            renderSettingsState();
            showToast(t('syncFailed'), true);
        } finally {
            elements.syncNowButton.disabled = false;
            if (labelSpan && originalText) labelSpan.textContent = originalText;
        }
    }

    async function refreshSnapshot() {
        if (state.clearingCache) return;
        if (!scopeComplete() || !isApproved()) {
            state.serverSnapshot = emptySnapshot();
            renderDefects();
            return;
        }
        try {
            const requestedScope = { ...state.scope };
            const requestedDeviceId = state.device.id;
            const snapshot = await requestJson('/api/method/uqqc-inspections-snapshot', {
                method: 'POST',
                body: JSON.stringify({ id: requestedDeviceId, ...requestedScope })
            });
            if (state.clearingCache || state.device?.id !== requestedDeviceId || !state.catalog) return;
            updateServerClock(snapshot.serverNowUtc);
            if (snapshot.serverDateKey && state.catalog.serverDateKey !== snapshot.serverDateKey) {
                state.catalog.serverDateKey = snapshot.serverDateKey;
                state.serverSnapshot = emptySnapshot();
                pruneDetailSnapshots();
                restoreScope();
                restoreActivePiece();
                renderScopeControls();
                return;
            }
            saveDetailSnapshot(requestedScope, snapshot);
            if (Object.keys(requestedScope).some(key => requestedScope[key] !== state.scope[key])) return;
            state.serverSnapshot = snapshot;
        } catch { /* pending local events remain visible while offline */ }
        renderDefects();
    }

    function handleScopeChange(level) {
        endActivePiece(true);
        if (level === 'line') state.scope = { ...emptyScope(), lineId: elements.line.value };
        else if (level === 'product') Object.assign(state.scope, { productId: elements.product.value, colorId: '', sizeId: '', marketId: '' });
        else if (level === 'market') Object.assign(state.scope, { marketId: elements.market.value, colorId: '', sizeId: '' });
        else if (level === 'color') Object.assign(state.scope, { colorId: elements.color.value, sizeId: '' });
        else if (level === 'size') state.scope.sizeId = elements.size.value;
        if (level === 'product') rememberRecentProduct(state.scope.productId);
        state.serverSnapshot = emptySnapshot();
        persistScope();
        renderScopeControls();
    }

    function applyScrollDirection() {
        const horizontal = localStorage.getItem(keys.scrollDirection) === 'horizontal';
        elements.defectGrid.classList.add('no-gutters');
        elements.defectGrid.classList.remove('flex-nowrap', 'overflow-auto');
        elements.defectGrid.classList.toggle('uqqc-scroll-horizontal', horizontal);
        elements.defectGrid.dataset.scrollDirection = horizontal ? 'horizontal' : 'vertical';
        elements.scrollDirection.setAttribute('aria-pressed', String(horizontal));
    }

    function toggleScrollDirection() {
        const horizontal = localStorage.getItem(keys.scrollDirection) === 'horizontal';
        localStorage.setItem(keys.scrollDirection, horizontal ? 'vertical' : 'horizontal');
        applyScrollDirection();
    }

    function isDomFullscreenActive() {
        return Boolean(
            document.fullscreenElement ||
            document.webkitFullscreenElement ||
            document.mozFullScreenElement ||
            document.msFullscreenElement
        );
    }

    function isStandaloneDisplayMode() {
        try {
            return navigator.standalone === true ||
                window.matchMedia?.('(display-mode: standalone)').matches === true ||
                window.matchMedia?.('(display-mode: fullscreen)').matches === true;
        } catch {
            return false;
        }
    }

    function isFullscreenActive() {
        return isDomFullscreenActive() || isStandaloneDisplayMode();
    }

    function isFullscreenButtonEvent(event) {
        const button = elements.fullscreen;
        if (!button || !event) return false;
        if (typeof event.composedPath === 'function') {
            return event.composedPath().includes(button);
        }
        return event.target instanceof Node && button.contains(event.target);
    }

    function enterFullscreen() {
        if (isDomFullscreenActive()) return Promise.resolve(true);
        const el = document.documentElement;
        const r = el.requestFullscreen ||
            el.webkitRequestFullscreen ||
            el.webkitRequestFullScreen ||
            el.mozRequestFullScreen ||
            el.msRequestFullscreen;
        if (typeof r !== 'function') return Promise.resolve(false);
        try {
            const res = r.call(el);
            if (res && typeof res.then === 'function') {
                return res.then(() => true).catch(() => false);
            }
            return Promise.resolve(true);
        } catch {
            return Promise.resolve(false);
        }
    }

    function exitFullscreen() {
        if (!isDomFullscreenActive()) return Promise.resolve(false);
        const x = document.exitFullscreen ||
            document.webkitExitFullscreen ||
            document.mozCancelFullScreen ||
            document.msExitFullscreen;
        if (typeof x !== 'function') return Promise.resolve(false);
        try {
            const res = x.call(document);
            if (res && typeof res.then === 'function') {
                return res.then(() => true).catch(() => false);
            }
            return Promise.resolve(true);
        } catch {
            return Promise.resolve(false);
        }
    }

    function toggleFullscreen() {
        if (isDomFullscreenActive()) {
            void exitFullscreen();
        } else {
            enterFullscreen().then(ok => {
                if (!ok) showToast(t('fullscreenFailed'), true);
            });
        }
        updateFullscreenButton();
    }

    function updateFullscreenButton() {
        const active = isFullscreenActive();
        elements.fullscreen.querySelector('.uqqc-fullscreen-expand')?.classList.toggle('d-none', active);
        elements.fullscreen.querySelector('.uqqc-fullscreen-collapse')?.classList.toggle('d-none', !active);
    }

    function ensureFullscreen() {
        if (isDomFullscreenActive()) return;
        void enterFullscreen().then(ok => {
            if (ok) updateFullscreenButton();
        });
    }

    function scheduleFullscreenAttempts() {
        if (typeof window === 'undefined') return;
        let activated = isFullscreenActive();
        let pending = false;
        const handleUserInteraction = event => {
            if (!event?.isTrusted || document.hidden || activated || pending || isFullscreenButtonEvent(event)) return;
            if (isFullscreenActive()) {
                activated = true;
                return;
            }
            pending = true;
            enterFullscreen().then(ok => {
                pending = false;
                if (ok) {
                    activated = true;
                    updateFullscreenButton();
                }
            });
        };

        document.addEventListener('pointerup', handleUserInteraction, { capture: true, passive: true });
        document.addEventListener('click', handleUserInteraction, { capture: true, passive: true });
        ['fullscreenchange', 'webkitfullscreenchange', 'mozfullscreenchange', 'MSFullscreenChange'].forEach(evtName => {
            document.addEventListener(evtName, () => {
                if (isFullscreenActive()) activated = true;
            });
        });
    }

    function parseDeviceId(value) {
        const raw = String(value || '').trim();
        if (!raw) return '';
        try {
            const json = JSON.parse(raw);
            if (json?.id || json?.deviceId) return String(json.id || json.deviceId).trim();
        } catch { /* raw QR values are expected */ }
        try {
            const url = new URL(raw);
            return String(url.searchParams.get('id') || url.searchParams.get('deviceId') || raw).trim();
        } catch {
            return raw;
        }
    }

    async function startQrScanner() {
        openDevicePanel();
        if (!window.isSecureContext) {
            setMessage(elements.deviceMessage, t('cameraSecureRequired'), true);
            return;
        }
        if (!navigator.mediaDevices?.getUserMedia) {
            setMessage(elements.deviceMessage, t('cameraUnsupported'), true);
            return;
        }
        if (!('BarcodeDetector' in window)) {
            setMessage(elements.deviceMessage, t('qrUnsupported'), true);
            return;
        }

        try {
            stopQrScanner();
            qrDetector = qrDetector || new BarcodeDetector({ formats: ['qr_code'] });
            qrStream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: 'environment' } }, audio: false });
            elements.qrVideo.srcObject = qrStream;
            elements.qrVideo.hidden = false;
            await elements.qrVideo.play();
            elements.qrStatus.hidden = false;
            elements.qrStatus.textContent = t('qrScanning');
            elements.scanQr.disabled = true;
            qrTimer = window.setInterval(scanQrFrame, 350);
        } catch {
            stopQrScanner();
            setMessage(elements.deviceMessage, t('cameraFailed'), true);
        }
    }

    async function scanQrFrame() {
        if (!qrDetector || elements.qrVideo.readyState < 2) return;
        try {
            const codes = await qrDetector.detect(elements.qrVideo);
            const deviceId = parseDeviceId(codes?.[0]?.rawValue || '');
            if (!deviceId) return;
            elements.manualDeviceId.value = deviceId;
            stopQrScanner();
            setMessage(elements.deviceMessage, t('qrReceived'));
        } catch { /* individual frame errors do not stop the scanner */ }
    }

    function stopQrScanner() {
        window.clearInterval(qrTimer);
        qrTimer = 0;
        if (qrStream) qrStream.getTracks().forEach(track => track.stop());
        qrStream = null;
        elements.qrVideo.pause();
        elements.qrVideo.srcObject = null;
        elements.qrVideo.hidden = true;
        elements.qrStatus.hidden = true;
        elements.qrStatus.textContent = t('cameraIdle');
        elements.scanQr.disabled = false;
    }

    async function clearClientCache() {
        if (state.clearingCache) return;
        if (!window.confirm(t('clearCacheConfirm'))) return;
        state.clearingCache = true;
        elements.clearCache.disabled = true;
        // Preserve the pre-hydration cache for verification, even if an in-flight restore returns less data.
        const preservedDetail = state.detailSnapshots || readJson(keys.detailSnapshots, null);
        let reloadPending = false;
        renderDefects();
        try {
            if (state.queue.length || state.activePiece || state.syncPromise) {
                if (!navigator.onLine || !canReachApi() || !isApproved()) {
                    showToast(t('clearCachePending'), true);
                    return;
                }
                do {
                    const count = state.queue.length;
                    await syncQueue();
                    if (state.queue.length && state.queue.length >= count) {
                        showToast(t('clearCachePending'), true);
                        return;
                    }
                } while (state.queue.length);
            }
            if (state.detailHydrationPromise) await state.detailHydrationPromise;
            const currentDetail = state.detailSnapshots || readJson(keys.detailSnapshots, null);
            const localDetails = [preservedDetail, currentDetail].filter(Boolean);
            if (localDetails.some(saved => Object.keys(saved.scopes || {}).length) || state.activePiece) {
                let data;
                try {
                    data = await requestJson('/api/method/uqqc-inspections-detail-snapshot', {
                        method: 'POST', body: JSON.stringify({ id: state.device.id })
                    });
                } catch {
                    showToast(t('clearCacheUnverified'), true);
                    return;
                }
                const verified = localDetails.every(saved => detailSnapshotCoversLocal(data, saved));
                if (!verified) {
                    showToast(t('clearCacheUnverified'), true);
                    return;
                }
            }
            endActivePiece(false);
            await removeClientCache();
            reloadPending = true;
        } finally {
            if (!reloadPending) {
                state.clearingCache = false;
                elements.clearCache.disabled = false;
                renderDefects();
            }
        }
    }

    async function removeClientCache() {
        stopQrScanner();
        Object.keys(localStorage).filter(key => key.startsWith(PREFIX)).forEach(key => localStorage.removeItem(key));
        Object.keys(sessionStorage).filter(key => key.startsWith(PREFIX)).forEach(key => sessionStorage.removeItem(key));
        if ('caches' in window) {
            const cacheKeys = await caches.keys();
            await Promise.all(cacheKeys.filter(key => key.startsWith('fm-uqqc-')).map(key => caches.delete(key)));
        }
        if ('serviceWorker' in navigator) {
            const registration = await navigator.serviceWorker.getRegistration('/uqqc');
            const scope = new URL('/uqqc', window.location.href).href;
            const scriptUrl = new URL('/uqqc-sw.js', window.location.href).href;
            const isOwnRegistration = registration?.scope === scope &&
                [registration.active, registration.waiting, registration.installing]
                    .some(worker => worker?.scriptURL === scriptUrl);
            if (isOwnRegistration) await registration.unregister();
        }
        window.location.reload();
    }

    async function registerServiceWorker() {
        if (!('serviceWorker' in navigator) || !window.isSecureContext) return;
        try {
            const registration = await navigator.serviceWorker.register('/uqqc-sw.js', { scope: '/uqqc', updateViaCache: 'none' });
            await registration.update();
            if (registration.waiting) registration.waiting.postMessage({ type: 'SKIP_WAITING' });
        } catch { /* PWA remains usable without offline shell registration */ }
    }

    function bindEvents() {
        elements.settings.addEventListener('click', () => openSettingsPanel());
        elements.settingsClose.addEventListener('click', closeSettingsPanel);
        elements.settingsPanel.addEventListener('click', event => { if (event.target === elements.settingsPanel) closeSettingsPanel(); });
        elements.detailOpen.addEventListener('click', openDetailPanel);
        elements.detailRetry.addEventListener('click', () => void hydrateDetailSnapshots());
        elements.detailClose.addEventListener('click', closeDetailPanel);
        elements.detailPanel.addEventListener('click', event => { if (event.target === elements.detailPanel) closeDetailPanel(); });
        [elements.detailProduct, elements.detailLine].forEach(select => {
            select.addEventListener('change', () => {
                state.detailFilters.productId = elements.detailProduct.value;
                state.detailFilters.lineId = elements.detailLine.value;
                renderDetail();
            });
        });
        elements.syncNowButton.addEventListener('click', () => void manualSync());
        elements.openDeviceSettingsButton.addEventListener('click', () => { closeSettingsPanel(); openDevicePanel(); });
        elements.deviceClose.addEventListener('click', closeDevicePanel);
        elements.devicePanel.addEventListener('click', event => { if (event.target === elements.devicePanel) closeDevicePanel(); });
        elements.activateDevice.addEventListener('click', activateDevice);
        elements.scanQr.addEventListener('click', startQrScanner);
        elements.clearCache.addEventListener('click', () => { void clearClientCache(); });
        elements.manualDeviceId.addEventListener('input', () => setMessage(elements.deviceMessage, ''));
        elements.manualDeviceId.addEventListener('keydown', event => { if (event.key === 'Enter') void activateDevice(); });
        elements.fullscreen.addEventListener('click', event => {
            toggleFullscreen();
            if (event.detail > 0) elements.fullscreen.blur();
        });
        elements.scrollDirection.addEventListener('click', event => {
            toggleScrollDirection();
            if (event.detail > 0) elements.scrollDirection.blur();
        });
        Object.entries(pickerDefinitions).forEach(([kind, definition]) => {
            definition.button.addEventListener('click', () => openScopePicker(kind));
        });
        elements.scopePickerClose.addEventListener('click', closeScopePicker);
        elements.scopePickerPanel.addEventListener('click', event => { if (event.target === elements.scopePickerPanel) closeScopePicker(); });
        elements.positionClose.addEventListener('click', closeDefectPositionPicker);
        elements.positionPanel.addEventListener('click', event => { if (event.target === elements.positionPanel) closeDefectPositionPicker(); });
        elements.moreDefectYes.addEventListener('click', () => answerMoreDefect(true));
        elements.moreDefectNo.addEventListener('click', () => answerMoreDefect(false));
        document.addEventListener('keydown', event => {
            if (event.key === 'Escape' && state.activePicker) closeScopePicker();
            else if (event.key === 'Escape' && state.activeDefectId) closeDefectPositionPicker();
            else if (event.key === 'Escape' && elements.detailPanel.classList.contains('open')) closeDetailPanel();
            else if (event.key === 'Escape' && elements.settingsPanel.classList.contains('open')) closeSettingsPanel();
            else if (event.key === 'Escape' && elements.devicePanel.classList.contains('open')) closeDevicePanel();
        });
        elements.confirmPass.addEventListener('click', () => {
            ensureFullscreen();
            queuePass();
        });
        elements.confirmRework.addEventListener('click', () => {
            ensureFullscreen();
            queueRework();
        });
        elements.line.addEventListener('change', () => handleScopeChange('line'));
        elements.product.addEventListener('change', () => handleScopeChange('product'));
        elements.market.addEventListener('change', () => handleScopeChange('market'));
        elements.color.addEventListener('change', () => handleScopeChange('color'));
        elements.size.addEventListener('change', () => handleScopeChange('size'));
        if (elements.arrangeToggle) {
            elements.arrangeToggle.addEventListener('click', () => {
                ensureFullscreen();
                toggleArrangeMode();
            });
        }
        elements.defectGrid.addEventListener('click', event => {
            ensureFullscreen();
            if (suppressNextDefectClick) {
                suppressNextDefectClick = false;
                event.preventDefault();
                return;
            }

            const shiftButton = event.target.closest('.uqqc-defect-shift-btn');
            if (shiftButton) {
                event.preventDefault();
                event.stopPropagation();
                if (!state.defectArrangeMode || shiftButton.disabled) return;
                const card = shiftButton.closest('.uqqc-defect-card');
                const dir = Number(shiftButton.dataset.shift) || 0;
                if (card?.dataset.defectId && dir && shiftVisibleDefectOneStep(card.dataset.defectId, dir)) {
                    renderDefects();
                }
                return;
            }

            const favoriteButton = event.target.closest('.uqqc-favorite-button');
            if (favoriteButton) {
                event.preventDefault();
                event.stopPropagation();
                toggleFavorite(favoriteButton.dataset.defectId);
                return;
            }

            const card = event.target.closest('.uqqc-defect-card');
            if (!card || card.classList.contains('uqqc-is-disabled')) return;
            if (state.defectArrangeMode) return;

            const defectId = card.dataset.defectId;
            if (defectId) {
                openDefectPositionPicker(defectId);
            }
        });
        elements.defectGrid.addEventListener('dragstart', handleDefectDragStart);
        elements.defectGrid.addEventListener('dragover', handleDefectDragOver);
        elements.defectGrid.addEventListener('dragleave', handleDefectDragLeave);
        elements.defectGrid.addEventListener('drop', handleDefectDrop);
        elements.defectGrid.addEventListener('dragend', handleDefectDragEnd);
        elements.defectGrid.addEventListener('pointerdown', handleDefectPointerDown, { passive: true });
        elements.defectGrid.addEventListener('lostpointercapture', handleDefectPointerCancel);

        ['fullscreenchange', 'webkitfullscreenchange', 'mozfullscreenchange', 'MSFullscreenChange'].forEach(evt => {
            document.addEventListener(evt, updateFullscreenButton);
        });
        if (window.jQuery?.fn?.modal) {
            window.jQuery(elements.moreDefectPanel).on('hide.bs.modal', event => {
                if (state.activePiece?.decisionPending) event.preventDefault();
            });
            panels().forEach(panel => window.jQuery(panel).on('hidden.bs.modal', () => {
                panel.classList.remove('open');
                panel.setAttribute('aria-hidden', 'true');
                if (panel === elements.devicePanel) stopQrScanner();
                if (panel === elements.scopePickerPanel) state.activePicker = '';
                if (panel === elements.positionPanel) state.activeDefectId = '';
                if (panel === elements.moreDefectPanel && state.activePiece?.decisionPending) {
                    window.setTimeout(openMoreDefectDialog, 0);
                }
            }));
        }

        window.addEventListener('online', () => {
            updateNetwork();
            if (storedDeviceId()) void checkDevice();
            if (state.queue.length) void syncQueue();
            startBootstrapRefreshWatchdog();
            startSyncWatchdog();
        });
        window.addEventListener('offline', updateNetwork);
        window.addEventListener('pagehide', stopQrScanner);
    }

    let bootstrapRefreshTimer = null;
    function startBootstrapRefreshWatchdog() {
        window.clearInterval(bootstrapRefreshTimer);
        if (!config.liveBootstrapEnabled) return;
        const intervalMs = config.pollingSeconds * 1000;
        bootstrapRefreshTimer = window.setInterval(async () => {
            if (!navigator.onLine) return;
            if (isApproved()) {
                void loadCatalog(true);
            } else if (storedDeviceId()) {
                void checkDevice();
            }
        }, intervalMs);
    }

    let syncWatchdogTimer = null;
    function startSyncWatchdog() {
        window.clearInterval(syncWatchdogTimer);
        const intervalMs = config.syncWatchdogSeconds * 1000;
        syncWatchdogTimer = window.setInterval(() => {
            syncServerDay();
            if (canReachApi() && isApproved() && state.queue.length && !state.syncing) {
                void syncQueue();
            }
        }, intervalMs);
    }

    async function start() {
        if (navigator.onLine) {
            try { await ensureDataEpoch(); } catch { if (epochReloading) return; }
        }
        apply(document);
        renderHeaderTitle();
        updateNetwork();
        updatePending();
        renderSettingsState();
        applyScrollDirection();
        updateFullscreenButton();
        bindEvents();
        scheduleFullscreenAttempts();
        renderInactiveScope();
        void registerServiceWorker();
        if (storedDeviceId()) await checkDevice(); else openDevicePanel('', false);
        elements.app.setAttribute('aria-busy', 'false');
        startBootstrapRefreshWatchdog();
        startSyncWatchdog();
    }

    void start();
}());
