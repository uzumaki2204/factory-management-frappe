frappe.pages['uqqc-report'].on_page_load = function (wrapper) {
  const page = frappe.ui.make_app_page({
    parent: wrapper,
    title: __('UQQC Report'),
    single_column: true,
  });

  const UQQC_RPT_VERSION = '20261128d';

  // Inject versioned CSS — xoá link cũ (kể cả link app_include_css không có ?v=)
  (function injectCss(v) {
    const base = '/assets/factory_management/css/uqqc_report.css';
    const href = `${base}?v=${v}`;
    document.querySelectorAll(`link[href*="${base}"]`).forEach((el) => {
      if (el.getAttribute('href') !== href) el.remove();
    });
    if (!document.querySelector(`link[href="${href}"]`)) {
      const link = document.createElement('link');
      link.rel = 'stylesheet';
      link.href = href;
      document.head.append(link);
    }
  })(UQQC_RPT_VERSION);

  const today = frappe.datetime.get_today();
  const state = { active: 'summary', request: 0 };
  const root = document.createElement('section');
  root.className = 'uqqc-report';

  // ── Filters Panel ──────────────────────────────────────────────────────────
  const filtersPanel = document.createElement('section');
  filtersPanel.className = 'uqqc-report__panel uqqc-report__filters';
  const filterRow = document.createElement('div');
  filterRow.className = 'uqqc-report__filter-row';
  const controls = {
    from_date: makeDateControl('From Date', 'from_date', today),
    to_date: makeDateControl('To Date', 'to_date', today),
    qc: makeControl('QC', 'qc', 'Select', '\nQC1\nQC2'),
    company: makeControl('Company', 'company', 'Link', 'Company'),
    product: makeControl('Product', 'product', 'Link', 'Product'),
    device: makeControl('Device', 'device', 'Link', 'Factory Device'),
    market: makeControl('Market', 'market', 'Link', 'Market'),
    color: makeControl('Color', 'color', 'Link', 'Product Color'),
    size: makeControl('Size', 'size', 'Link', 'ProductSize'),
  };

  // Run button — cùng dòng với các filter (cột cuối)
  const runButton = document.createElement('button');
  runButton.type = 'button';
  runButton.className = 'btn btn-primary uqqc-report__run';
  runButton.textContent = __('View Report');

  for (const key of ['from_date', 'to_date', 'qc', 'company', 'product']) {
    filterRow.append(controls[key].wrapper);
  }
  filterRow.append(runButton);

  const detailFilters = document.createElement('div');
  detailFilters.className = 'uqqc-report__filter-row uqqc-report__filter-row--detail';
  for (const key of ['device', 'market', 'color', 'size']) {
    detailFilters.append(controls[key].wrapper);
  }

  filtersPanel.append(filterRow, detailFilters);
  root.append(filtersPanel);

  // ── Tabs ───────────────────────────────────────────────────────────────────
  const tabs = document.createElement('div');
  tabs.className = 'uqqc-report__tabs';
  tabs.setAttribute('role', 'tablist');
  tabs.setAttribute('aria-label', __('UQQC report type'));
  const summaryTab = makeTab('summary', 'Item Summary');
  const deviceTab = makeTab('device', 'Device Details');
  tabs.append(summaryTab, deviceTab);
  root.append(tabs);

  // ── Metrics ────────────────────────────────────────────────────────────────
  const metrics = document.createElement('section');
  metrics.className = 'uqqc-report__metrics';
  metrics.setAttribute('aria-label', __('Selected period metrics'));
  metrics.setAttribute('aria-live', 'polite');
  root.append(metrics);

  // ── Results Panel ──────────────────────────────────────────────────────────
  const resultsPanel = document.createElement('section');
  resultsPanel.className = 'uqqc-report__panel uqqc-report__results';
  const resultsHeader = document.createElement('div');
  resultsHeader.className = 'uqqc-report__results-header';
  const resultsMeta = document.createElement('div');
  resultsMeta.className = 'uqqc-report__results-meta';
  resultsHeader.append(resultsMeta);

  const status = document.createElement('div');
  status.className = 'uqqc-report__status';
  status.setAttribute('role', 'status');
  status.setAttribute('aria-live', 'polite');

  const tableWrap = document.createElement('div');
  tableWrap.className = 'uqqc-report__table-wrap';
  resultsPanel.append(resultsHeader, status, tableWrap);
  root.append(resultsPanel);
  page.body.append(root);

  runButton.addEventListener('click', runReport);
  summaryTab.addEventListener('click', () => selectTab('summary'));
  deviceTab.addEventListener('click', () => selectTab('device'));
  Promise.all([controls.from_date.ready, controls.to_date.ready]).then(() => {
    selectTab('summary');
  });

  function makeControl(label, fieldname, fieldtype, options = '', defaultValue = '') {
    const wrapper = document.createElement('div');
    wrapper.className = 'uqqc-report__date-control';
    const control = frappe.ui.form.make_control({
      parent: wrapper,
      df: {
        fieldtype,
        fieldname,
        label: __(label),
        options,
        reqd: fieldtype === 'Date' ? 1 : 0,
        default: defaultValue,
      },
      render_input: true,
    });
    control.refresh();
    return { wrapper, control };
  }

  // Date control đặc biệt: icon lịch, bấm mở datepicker (không bàn phím), default = hôm nay
  function makeDateControl(label, fieldname, defaultValue) {
    const { wrapper, control } = makeControl(label, fieldname, 'Date', '', defaultValue);
    wrapper.classList.add('uqqc-report__control--date');

    const ready = Promise.resolve(control.set_value(defaultValue)).then(() => {
      if (control.$input && !control.$input.val()) {
        const formatted = frappe.datetime && frappe.datetime.str_to_user
          ? frappe.datetime.str_to_user(defaultValue)
          : defaultValue;
        control.$input.val(formatted);
      }
    }).catch(() => {});

    const $input = control.$input;
    const input = $input && $input[0];
    if ($input && $input.length) {
      $input.prop('readonly', true);
      $input.attr('inputmode', 'none');
      $input.attr('autocomplete', 'off');
      $input.attr('tabindex', '-1');
    }

    const inputContainer = wrapper.querySelector('.control-input')
      || wrapper.querySelector('.control-input-wrapper')
      || (input && input.parentElement)
      || wrapper;

    if (!inputContainer.querySelector('.uqqc-rpt-cal-btn')) {
      inputContainer.style.position = 'relative';

      const calBtn = document.createElement('button');
      calBtn.type = 'button';
      calBtn.className = 'uqqc-rpt-cal-btn';
      calBtn.tabIndex = -1;
      calBtn.setAttribute('aria-label', __('Open calendar'));
      calBtn.innerHTML =
        '<svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24"' +
        ' fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"' +
        ' stroke-linejoin="round" aria-hidden="true">' +
        '<rect x="3" y="4" width="18" height="18" rx="2" ry="2"></rect>' +
        '<line x1="16" y1="2" x2="16" y2="6"></line>' +
        '<line x1="8" y1="2" x2="8" y2="6"></line>' +
        '<line x1="3" y1="10" x2="21" y2="10"></line>' +
        '</svg>';

      let wasOpenOnPress = false;
      let touched = false;

      inputContainer.addEventListener('touchstart', () => {
        touched = true;
        const dp = getDatepicker(control);
        wasOpenOnPress = Boolean(dp && dp.visible);
      }, { passive: true });

      inputContainer.addEventListener('mousedown', (e) => {
        e.preventDefault();
        if (!touched) {
          const dp = getDatepicker(control);
          wasOpenOnPress = Boolean(dp && dp.visible);
        }
        touched = false;
      });

      inputContainer.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        const shouldClose = wasOpenOnPress;
        wasOpenOnPress = false;
        if (input && document.activeElement === input) input.blur();
        const dp = getDatepicker(control);
        if (!dp) return;
        if (shouldClose || dp.visible) {
          dp.hide();
        } else {
          setTimeout(() => dp.show(), 0);
        }
      });

      inputContainer.append(calBtn);
    }

    return { wrapper, control, ready };
  }

  // Lazy-get Air Datepicker instance từ Frappe Date control
  function getDatepicker(control) {
    if (control.datepicker) return control.datepicker;
    if (control.$input) {
      const dp = control.$input.data('datepicker');
      if (dp) return dp;
      // Khởi tạo datepicker nếu chưa có
      if (typeof control.set_datepicker === 'function') {
        control.set_datepicker();
        return control.$input.data('datepicker') || control.datepicker || null;
      }
    }
    return null;
  }

  function makeTab(key, label) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'uqqc-report__tab';
    button.dataset.tab = key;
    button.setAttribute('role', 'tab');
    button.setAttribute('aria-controls', 'uqqc-report-results');
    button.textContent = __(label);
    return button;
  }

  function selectTab(tab) {
    state.active = tab;
    for (const button of tabs.querySelectorAll('[role="tab"]')) {
      const active = button.dataset.tab === tab;
      button.classList.toggle('is-active', active);
      button.setAttribute('aria-selected', String(active));
      button.tabIndex = active ? 0 : -1;
    }
    detailFilters.hidden = tab !== 'device';
    resultsPanel.id = 'uqqc-report-results';
    runReport();
  }

  async function runReport() {
    const request = ++state.request;
    const fromDate = controls.from_date.control.get_value();
    const toDate = controls.to_date.control.get_value();
    if (!fromDate || !toDate) {
      runButton.disabled = false;
      runButton.classList.remove('is-loading');
      clearResults();
      showStatus(__('Choose both report dates.'), 'error');
      return;
    }
    if (fromDate > toDate) {
      runButton.disabled = false;
      runButton.classList.remove('is-loading');
      clearResults();
      showStatus(__('The start date must be on or before the end date.'), 'error');
      return;
    }

    clearResults();
    runButton.disabled = true;
    runButton.classList.add('is-loading');
    showSkeleton();
    try {
      const filters = {
        from_date: fromDate,
        to_date: toDate,
        qc: controls.qc.control.get_value() || '',
        company: controls.company.control.get_value() || '',
        product: controls.product.control.get_value() || '',
      };
      if (state.active === 'device') {
        for (const key of ['device', 'market', 'color', 'size']) {
          filters[key] = controls[key].control.get_value() || '';
        }
      }
      const response = await frappe.call({
        method: 'frappe.desk.query_report.run',
        args: {
          report_name: state.active === 'summary' ? 'UQQC Item Summary' : 'UQQC Device Details',
          filters: JSON.stringify(filters),
          are_default_filters: 0,
        },
      });
      if (request !== state.request) return;
      const result = response.message || {};
      const columns = result.columns || [];
      const rows = result.result || [];
      renderMetrics(columns, rows);
      renderTable(columns, rows);
      resultsMeta.textContent = __('Rows: {0}', [rows.length]);
      showStatus('', '');
    } catch {
      if (request !== state.request) return;
      clearResults();
      showStatus(__('Unable to load the UQQC report.'), 'error');
      frappe.show_alert({ message: __('Report request failed.'), indicator: 'red' });
    } finally {
      if (request === state.request) {
        runButton.disabled = false;
        runButton.classList.remove('is-loading');
      }
    }
  }

  function renderMetrics(columns, rows) {
    const names = state.active === 'summary'
      ? { passed: 'Số lượng đạt', rework: 'Số lượng tái sửa', defect: 'Số lượng lỗi' }
      : { passed: 'Đạt', rework: 'Tái sửa', defect: 'Lỗi' };
    const passed = sumColumn(columns, rows, names.passed);
    const rework = sumColumn(columns, rows, names.rework);
    const defect = sumColumn(columns, rows, names.defect);
    const inspected = passed + defect;
    const rate = inspected ? (defect * 100) / inspected : 0;
    const rateTone = rate > 5 ? 'danger' : rate > 2 ? 'warning' : 'neutral';
    const cards = [
      { label: 'Passed', value: passed, tone: 'success' },
      { label: 'Rework', value: rework, tone: 'warning' },
      { label: 'Defects', value: defect, tone: 'danger' },
      { label: 'Inspected', value: inspected, tone: 'primary' },
      { label: 'Defect Rate', value: rate, tone: rateTone, percent: true },
    ];
    metrics.replaceChildren();
    for (const item of cards) {
      const card = document.createElement('article');
      card.className = `uqqc-report__metric uqqc-report__metric--${item.tone}`;

      const label = document.createElement('div');
      label.className = 'uqqc-report__metric-label';
      label.textContent = __(item.label);

      const value = document.createElement('div');
      value.className = 'uqqc-report__metric-value';
      value.textContent = item.percent ? formatPercent(rate) : formatNumber(item.value);

      card.append(label, value);
      metrics.append(card);
    }
  }

  function sumColumn(columns, rows, label) {
    const column = columns.find((item) => item.label === label);
    if (!column) return 0;
    return rows.reduce((total, row) => total + (Number(row[column.fieldname]) || 0), 0);
  }

  function renderTable(columns, rows) {
    if (!rows.length) {
      const empty = document.createElement('div');
      empty.className = 'uqqc-report__empty';
      const title = document.createElement('strong');
      title.textContent = __('No records found for this period.');
      const hint = document.createElement('span');
      hint.textContent = __('Try another date range.');
      empty.append(title, hint);
      tableWrap.replaceChildren(empty);
      return;
    }

    const table = document.createElement('table');
    table.className = 'uqqc-report__table';
    table.setAttribute('aria-label', __(state.active === 'summary' ? 'Item Summary' : 'Device Details'));
    const head = table.createTHead().insertRow();
    for (const column of columns) {
      const cell = document.createElement('th');
      cell.scope = 'col';
      cell.textContent = column.label || column.fieldname || '';
      if (isNumericColumn(column)) cell.classList.add('is-numeric');
      head.append(cell);
    }
    const body = table.createTBody();
    for (const row of rows) {
      const tr = body.insertRow();
      for (const column of columns) {
        const cell = tr.insertCell();
        const value = row[column.fieldname];
        cell.textContent = formatValue(column, value);
        if (isNumericColumn(column)) cell.classList.add('is-numeric');
        if (isDefectColumn(column) && Number(value) > 0) cell.classList.add('is-defect');
        if (isRateColumn(column)) cell.classList.add('is-rate');
      }
    }

    // ── Grand Total Row ──────────────────────────────────────────────────────
    const numericColumns = columns.filter(isNumericColumn);
    if (numericColumns.length > 0 && rows.length > 1) {
      const totals = {};
      for (const col of numericColumns) {
        totals[col.fieldname] = rows.reduce(
          (sum, row) => sum + (Number(row[col.fieldname]) || 0), 0
        );
      }
      const tfoot = table.createTFoot();
      const totalRow = tfoot.insertRow();
      totalRow.className = 'uqqc-report__total-row';
      for (let i = 0; i < columns.length; i++) {
        const col = columns[i];
        const cell = totalRow.insertCell();
        if (i === 0) {
          cell.textContent = __('Total');
          cell.className = 'uqqc-report__total-label';
        } else if (isNumericColumn(col)) {
          // Skip rate/percent columns — summing % values is meaningless
          if (!isRateColumn(col)) {
            cell.textContent = formatNumber(totals[col.fieldname] || 0);
          }
          cell.classList.add('is-numeric');
        }
      }
    }

    tableWrap.replaceChildren(table);
  }

  function isNumericColumn(column) {
    return ['Int', 'Float', 'Currency', 'Percent'].includes(column.fieldtype);
  }

  function isDefectColumn(column) {
    return (column.label || '').toLowerCase().includes('lỗi') ||
      (column.label || '').toLowerCase().includes('defect');
  }

  function isRateColumn(column) {
    return column.fieldtype === 'Percent' ||
      (column.label || '').toLowerCase().includes('tỷ lệ') ||
      (column.label || '').toLowerCase().includes('rate');
  }

  function formatValue(column, value) {
    if (value === null || value === undefined) return '';
    if (isRateColumn(column)) return formatPercent(value);
    if (typeof value === 'number') return formatNumber(value);
    return String(value);
  }

  function formatNumber(value) {
    return new Intl.NumberFormat(frappe.boot.lang || undefined, {
      maximumFractionDigits: 2,
    }).format(value);
  }

  function formatPercent(value) {
    return `${new Intl.NumberFormat(frappe.boot.lang || undefined, {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(value)}%`;
  }

  function clearResults() {
    metrics.replaceChildren();
    resultsMeta.textContent = '';
    tableWrap.replaceChildren();
  }

  function showSkeleton() {
    status.textContent = '';
    status.className = 'uqqc-report__status';
    const skeleton = document.createElement('div');
    skeleton.className = 'uqqc-report__skeleton';
    // Render a placeholder metrics strip
    const metricsSkel = document.createElement('div');
    metricsSkel.className = 'uqqc-report__skeleton-metrics';
    for (let i = 0; i < 5; i++) {
      const card = document.createElement('div');
      card.className = 'uqqc-report__skeleton-metric';
      metricsSkel.append(card);
    }
    metrics.replaceChildren(metricsSkel);
    // Render table rows skeleton
    for (let i = 0; i < 7; i++) {
      const row = document.createElement('div');
      row.className = 'uqqc-report__skeleton-row';
      skeleton.append(row);
    }
    tableWrap.replaceChildren(skeleton);
  }

  function showStatus(message, type) {
    status.textContent = message || '';
    status.className = `uqqc-report__status${type ? ` is-${type}` : ''}`;
  }
};
