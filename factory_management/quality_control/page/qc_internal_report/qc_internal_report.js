frappe.pages['qc-internal-report'].on_page_load = function (wrapper) {
  frappe.require('/assets/factory_management/js/qc_internal_report_filters.js')
    .then(() => initializeQcInternalReport(wrapper));
};

function initializeQcInternalReport(wrapper) {
  const page = frappe.ui.make_app_page({
    parent: wrapper,
    title: __('Báo cáo QC nội bộ'),
    single_column: true,
  });
  const today = frappe.datetime.get_today();
  const state = {active: 'summary', request: 0, rows: [], datasetKey: ''};
  const rendererReady = frappe.require('/assets/factory_management/js/qc_internal_report_view.js');
  const root = document.createElement('section');
  root.className = 'qc-internal-report';

  const tabDefinitions = [
    {key: 'company', label: 'Công ty', title: 'BÁO CÁO TÌNH HÌNH CHẤT LƯỢNG THEO CÔNG TY'},
    {key: 'product', label: 'Mã hàng', title: 'BÁO CÁO TÌNH HÌNH CHẤT LƯỢNG THEO MÃ HÀNG'},
    {key: 'defect', label: 'Loại lỗi', title: 'BÁO CÁO TÌNH HÌNH CHẤT LƯỢNG THEO LOẠI LỖI'},
    {key: 'summary', label: 'Tổng hợp', title: 'BÁO CÁO TỔNG HỢP CHẤT LƯỢNG KIM THÀNH GROUP'},
  ];

  const masthead = document.createElement('header');
  masthead.className = 'qc-ir-masthead';
  const logo = document.createElement('img');
  logo.className = 'qc-ir-logo';
  logo.src = '/assets/factory_management/images/qc-logo.png';
  logo.alt = 'Kim Thành Group';
  const title = document.createElement('h1');
  const refreshButton = document.createElement('button');
  refreshButton.type = 'button';
  refreshButton.className = 'qc-ir-refresh';
  refreshButton.title = __('Cập nhật báo cáo');
  refreshButton.setAttribute('aria-label', __('Cập nhật báo cáo'));
  refreshButton.textContent = '↻';
  masthead.append(logo, title, refreshButton);

  const filtersPanel = document.createElement('section');
  filtersPanel.className = 'qc-ir-filters';
  const filterGrid = document.createElement('div');
  filterGrid.className = 'qc-ir-filter-grid';

  let ready = false;
  let refreshTimer;
  const filterChanged = () => {
    if (ready) refreshFilters();
  };
  const controls = {
    company: QCInternalReportFilters.makeMultiControl('CÔNG TY', filterChanged),
    factory: QCInternalReportFilters.makeMultiControl('XƯỞNG', filterChanged),
    production_line: QCInternalReportFilters.makeMultiControl('CHUYỀN', filterChanged),
    product: QCInternalReportFilters.makeMultiControl('MÃ HÀNG', filterChanged),
    qc: makeControl('QC', 'qc', 'Select', 'QC1', 'QC1\nQC2', '', true),
    from_date: makeControl('TỪ NGÀY', 'from_date', 'Date', today.slice(0, 8) + '01'),
    to_date: makeControl('ĐẾN NGÀY', 'to_date', 'Date', today),
  };

  const dateRange = document.createElement('div');
  dateRange.className = 'qc-ir-date-range';
  const dateLabel = document.createElement('span');
  dateLabel.className = 'qc-ir-date-label';
  dateLabel.textContent = __('NGÀY');
  const dateInputs = document.createElement('div');
  dateInputs.className = 'qc-ir-date-inputs';
  dateInputs.append(controls.from_date.wrapper, controls.to_date.wrapper);
  dateRange.append(dateLabel, dateInputs);
  filtersPanel.append(filterGrid);

  const status = document.createElement('div');
  status.className = 'qc-ir-status';
  status.setAttribute('role', 'status');
  status.setAttribute('aria-live', 'polite');
  filtersPanel.append(status);

  const content = document.createElement('div');
  content.className = 'qc-ir-content';
  const results = document.createElement('section');
  results.className = 'qc-ir-results';
  results.append(content);
  const tabs = document.createElement('nav');
  tabs.className = 'qc-ir-tabs';
  tabs.setAttribute('aria-label', __('Các trang báo cáo QC'));
  tabDefinitions.forEach((item) => {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'qc-ir-tab';
    button.dataset.tab = item.key;
    button.textContent = __(item.label);
    tabs.append(button);
  });

  page.body.append(root);
  root.append(masthead, filtersPanel, results, tabs);
  refreshButton.addEventListener('click', () => runReport(true));
  tabs.addEventListener('click', (event) => {
    const button = event.target.closest('[data-tab]');
    if (button) selectTab(button.dataset.tab);
  });

  [controls.from_date, controls.to_date].forEach(({control}) => {
    if (control.$input) control.$input.on('change', scheduleReport);
  });
  controls.qc.control.$input.on('change', onQcChange);
  selectTab('summary', false);
  ready = true;
  runReport(true);

  function makeControl(label, fieldname, fieldtype, defaultValue = '', options = '', placeholder = '', required = false) {
    const wrapper = document.createElement('div');
    wrapper.className = 'qc-ir-control';
    const df = {fieldtype, fieldname, label: __(label), options, default: defaultValue, reqd: required};
    if (placeholder) df.placeholder = placeholder;
    const control = frappe.ui.form.make_control({parent: wrapper, df, render_input: true});
    control.refresh();
    if (defaultValue) control.set_value(defaultValue);
    const result = {wrapper, control};
    if (fieldtype === 'Date') attachDateCalButton(result);
    return result;
  }

  function attachDateCalButton({wrapper, control}) {
    // Find the input wrapper created by Frappe
    const inputWrapper = wrapper.querySelector('.control-input-wrapper') || wrapper;
    if (inputWrapper.querySelector('.qc-ir-date-cal-btn')) return; // idempotent
    inputWrapper.style.position = 'relative';

    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'qc-ir-date-cal-btn';
    btn.setAttribute('aria-label', __('Mở lịch'));
    btn.innerHTML =
      '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24"' +
      ' fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"' +
      ' stroke-linejoin="round" aria-hidden="true">' +
      '<rect x="3" y="4" width="18" height="18" rx="2" ry="2"></rect>' +
      '<line x1="16" y1="2" x2="16" y2="6"></line>' +
      '<line x1="8" y1="2" x2="8" y2="6"></line>' +
      '<line x1="3" y1="10" x2="21" y2="10"></line>' +
      '</svg>';

    // Prevent mobile keyboard from popping up when tapping the icon
    btn.addEventListener('mousedown', (e) => e.preventDefault());
    btn.addEventListener('touchstart', (e) => e.preventDefault(), {passive: false});

    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      const $input = control.$input;
      if (!$input || !$input.length) return;
      // Blur first so the virtual keyboard is dismissed, then show the datepicker
      $input[0].blur();
      const dp = $input.data('datepicker');
      if (dp) {
        setTimeout(() => dp.show(), 30);
      } else {
        // Frappe v16: datepicker may be under a different key — trigger focus as fallback
        $input.trigger('focus');
      }
    });

    inputWrapper.append(btn);
  }

  function selectTab(tab, refresh = true) {
    state.active = tab;
    const definition = tabDefinitions.find((item) => item.key === tab);
    title.textContent = __(definition.title);
    tabs.querySelectorAll('[data-tab]').forEach((button) => {
      const active = button.dataset.tab === tab;
      button.classList.toggle('is-active', active);
      button.setAttribute('aria-current', active ? 'page' : 'false');
    });
    filterGrid.replaceChildren();
    filterGrid.classList.toggle('is-summary', tab === 'summary');
    if (tab === 'summary') {
      filterGrid.append(controls.product.wrapper, controls.qc.wrapper, dateRange);
    } else {
      filterGrid.append(
        controls.company.wrapper,
        controls.factory.wrapper,
        controls.production_line.wrapper,
        controls.product.wrapper,
        controls.qc.wrapper,
        dateRange
      );
    }
    if (refresh && ready) refreshFilters();
  }

  function scheduleReport() {
    if (!ready) return;
    window.clearTimeout(refreshTimer);
    refreshTimer = window.setTimeout(() => runReport(true), 400);
  }

  function onQcChange() {
    refreshFilters();
  }

  function refreshFilters() {
    updateFilterOptions();
    applyFilters();
  }

  async function runReport(force = false) {
    const request = ++state.request;
    const fromDate = QCInternalReportFilters.normalizeDate(
      QCInternalReportFilters.readDateInput(controls.from_date.control)
    );
    const toDate = QCInternalReportFilters.normalizeDate(
      QCInternalReportFilters.readDateInput(controls.to_date.control)
    );
    if (!fromDate || !toDate || fromDate > toDate) {
      showStatus(__('Vui lòng chọn khoảng ngày hợp lệ.'), true);
      return;
    }
    const datasetKey = JSON.stringify([fromDate, toDate]);
    if (!force && state.datasetKey === datasetKey) {
      updateFilterOptions();
      applyFilters();
      return;
    }
    showStatus(__('Đang tải dữ liệu QC…'), false);
    content.replaceChildren();
    refreshButton.disabled = true;
    const filters = {
      from_date: fromDate,
      to_date: toDate,
      qc: '',
      company: '',
      factory: '',
      line_group: '',
      production_line: '',
      customer: '',
      product: '',
    };
    try {
      await rendererReady;
      const response = await frappe.call({
        method: 'frappe.desk.query_report.run',
        type: 'POST',
        args: {
          report_name: 'QC Internal Dataset',
          filters: JSON.stringify(filters),
          are_default_filters: 0,
        },
      });
      if (request !== state.request) return;
      const result = response.message || {};
      state.rows = QCInternalReportFilters.normalizeRows(result.columns || [], result.result || []);
      state.datasetKey = datasetKey;
      updateQcOptions();
      updateFilterOptions();
      showStatus('', false);
      applyFilters();
    } catch (error) {
      if (request !== state.request) return;
      state.rows = [];
      state.datasetKey = '';
      updateQcOptions();
      updateFilterOptions();
      content.replaceChildren();
      showStatus(__('Không tải được dữ liệu QC. Kiểm tra quyền báo cáo và bộ lọc.'), true);
      console.error('QC Internal Report failed', error);
    } finally {
      if (request === state.request) refreshButton.disabled = false;
    }
  }

  function updateQcOptions() {
    const control = controls.qc.control;
    const select = control.$input[0];
    const current = control.get_value();
    const available = Array.from(new Set(state.rows.map((row) => String(row.qc || '').trim())))
      .filter((value) => value === 'QC1' || value === 'QC2')
      .sort();
    control.df.options = available.join('\n');
    select.replaceChildren();
    if (!available.length) {
      select.add(new Option(__('Không có dữ liệu'), ''));
      select.disabled = true;
      return;
    }
    available.forEach((value) => select.add(new Option(value, value)));
    select.disabled = false;
    select.value = available.includes(current) ? current : available.includes('QC1') ? 'QC1' : available[0];
  }

  function updateFilterOptions() {
    const qc = controls.qc.control.get_value();
    const activeFilters = state.active === 'summary' ? ['product'] : QCInternalReportFilters.fields.map((item) => item.fieldname);
    QCInternalReportFilters.updateOptions(state.rows, qc, activeFilters, controls);
  }

  function applyFilters() {
    const qc = controls.qc.control.get_value();
    if (qc !== 'QC1' && qc !== 'QC2') {
      const hasAvailableQc = state.rows.some((row) => row.qc === 'QC1' || row.qc === 'QC2');
      showStatus(
        hasAvailableQc ? __('Chọn QC1 hoặc QC2 để xem báo cáo.') : __('Không có dữ liệu QC1 hoặc QC2 trong khoảng ngày này.'),
        hasAvailableQc
      );
      renderResults([]);
      return;
    }
    const activeFilters = state.active === 'summary'
      ? ['product']
      : ['company', 'factory', 'production_line', 'product'];
    const rows = QCInternalReportFilters.filterRows(state.rows, qc, activeFilters, controls);
    showStatus(rows.length ? '' : __('Không có dữ liệu phù hợp với các bộ lọc đã chọn.'), false);
    renderResults(rows);
  }

  function renderResults(rows = state.rows) {
    if (!window.QCInternalReportView) {
      showStatus(__('Thiếu thành phần hiển thị báo cáo QC.'), true);
      return;
    }
    const summary = window.QCInternalReportView.summarize(rows);
    window.QCInternalReportView.render({tab: state.active, summary, content});
  }

  function showStatus(message, isError) {
    status.textContent = message;
    status.classList.toggle('is-error', Boolean(isError));
    status.classList.toggle('is-visible', Boolean(message));
  }

  const stylesheet = '/assets/factory_management/css/qc_internal_report.css';
  if (!document.querySelector('link[href="' + stylesheet + '"]')) {
    const link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = stylesheet;
    document.head.append(link);
  }
}
