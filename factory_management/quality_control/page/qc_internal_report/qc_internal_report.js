frappe.pages['qc-internal-report'].on_page_load = function (wrapper) {
  const page = frappe.ui.make_app_page({
    parent: wrapper,
    title: __('Báo cáo QC nội bộ'),
    single_column: true,
  });
  const today = frappe.datetime.get_today();
  const state = {active: 'summary', request: 0, rows: []};
  const rendererReady = frappe.require('/assets/factory_management/js/qc_internal_report_view.js');
  const root = document.createElement('section');
  root.className = 'qc-internal-report';
  page.body.append(root);

  const filtersPanel = document.createElement('section');
  filtersPanel.className = 'qc-ir-panel qc-ir-filters';
  const filterRows = [document.createElement('div'), document.createElement('div')];
  filterRows.forEach((row) => row.className = 'qc-ir-filter-row');
  const controls = {
    from_date: makeControl('Từ ngày', 'from_date', 'Date', `${today.slice(0, 8)}01`),
    to_date: makeControl('Đến ngày', 'to_date', 'Date', today),
    qc: makeControl('QC', 'qc', 'Select', '', '\nQC1\nQC2'),
    company: makeControl('Công ty', 'company', 'Link', '', 'Company'),
    factory: makeControl('Nhà máy', 'factory', 'Link', '', 'Factory'),
    line_group: makeControl('Nhóm chuyền', 'line_group', 'Link', '', 'Line Group'),
    production_line: makeControl('Chuyền', 'production_line', 'Link', '', 'Production Line'),
    customer: makeControl('Khách hàng', 'customer', 'Link', '', 'Customer'),
    product: makeControl('Mã hàng', 'product', 'Link', '', 'Product'),
  };
  ['from_date', 'to_date', 'qc', 'company', 'factory'].forEach((key) => filterRows[0].append(controls[key].wrapper));
  ['line_group', 'production_line', 'customer', 'product'].forEach((key) => filterRows[1].append(controls[key].wrapper));

  const actions = document.createElement('div');
  actions.className = 'qc-ir-actions';
  const status = document.createElement('div');
  status.className = 'qc-ir-status';
  status.setAttribute('role', 'status');
  status.setAttribute('aria-live', 'polite');
  const runButton = document.createElement('button');
  runButton.type = 'button';
  runButton.className = 'btn btn-primary';
  runButton.textContent = __('Xem báo cáo');
  actions.append(status, runButton);
  filtersPanel.append(...filterRows, actions);
  root.append(filtersPanel);

  const tabs = document.createElement('div');
  tabs.className = 'qc-ir-tabs';
  tabs.setAttribute('role', 'tablist');
  tabs.setAttribute('aria-label', __('Các trang báo cáo QC'));
  const tabDefinitions = [
    ['summary', 'Tổng hợp', 'Theo công ty'],
    ['company', 'Công ty', 'Sản lượng và xu hướng'],
    ['product', 'Mã hàng', 'Tỷ lệ lỗi theo mã hàng'],
    ['defect', 'Loại lỗi', 'Xếp hạng lỗi'],
  ];
  tabDefinitions.forEach(([key, label, hint]) => tabs.append(makeTab(key, label, hint)));
  root.append(tabs);

  const metrics = document.createElement('section');
  metrics.className = 'qc-ir-metrics';
  const results = document.createElement('section');
  results.className = 'qc-ir-panel qc-ir-results';
  const meta = document.createElement('div');
  meta.className = 'qc-ir-meta';
  const content = document.createElement('div');
  content.className = 'qc-ir-content';
  results.append(meta, content);
  root.append(metrics, results);

  runButton.addEventListener('click', runReport);
  tabs.addEventListener('click', (event) => {
    const button = event.target.closest('[data-tab]');
    if (button) selectTab(button.dataset.tab);
  });
  selectTab('summary');
  runReport();

  function makeControl(label, fieldname, fieldtype, defaultValue = '', options = '') {
    const wrapper = document.createElement('div');
    wrapper.className = 'qc-ir-control';
    const control = frappe.ui.form.make_control({
      parent: wrapper,
      df: {fieldtype, fieldname, label: __(label), options, default: defaultValue},
      render_input: true,
    });
    control.refresh();
    if (defaultValue) control.set_value(defaultValue);
    return {wrapper, control};
  }

  function makeTab(key, label, hint) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'qc-ir-tab';
    button.dataset.tab = key;
    button.setAttribute('role', 'tab');
    button.setAttribute('aria-selected', 'false');
    button.textContent = __(label);
    const subtitle = document.createElement('span');
    subtitle.textContent = __(hint);
    button.append(subtitle);
    return button;
  }

  function selectTab(tab) {
    state.active = tab;
    tabs.querySelectorAll('[role="tab"]').forEach((button) => {
      const active = button.dataset.tab === tab;
      button.classList.toggle('is-active', active);
      button.setAttribute('aria-selected', String(active));
    });
    if (state.rows.length) renderResults();
  }

  async function runReport() {
    const request = ++state.request;
    const fromDate = normalizeDate(readDateInput(controls.from_date.control));
    const toDate = normalizeDate(readDateInput(controls.to_date.control));
    if (!fromDate || !toDate || fromDate > toDate) {
      showStatus(__('Khai báo ngày hợp lệ; Từ ngày phải trước hoặc bằng Đến ngày.'), true);
      return;
    }
    runButton.disabled = true;
    status.textContent = __('Đang tải dữ liệu QC…');
    content.replaceChildren();
    const filters = {from_date: fromDate, to_date: toDate};
    ['qc', 'company', 'factory', 'line_group', 'production_line', 'customer', 'product']
      .forEach((key) => filters[key] = controls[key].control.get_value() || '');
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
      state.rows = normalizeRows(result.columns || [], result.result || []);
      showStatus('', false);
      renderResults();
    } catch (error) {
      if (request !== state.request) return;
      state.rows = [];
      metrics.replaceChildren();
      content.replaceChildren();
      showStatus(__('Không tải được dữ liệu QC. Kiểm tra quyền báo cáo và bộ lọc.'), true);
      frappe.show_alert({message: __('Yêu cầu báo cáo thất bại.'), indicator: 'red'});
      console.error('QC Internal Report failed', error);
    } finally {
      if (request === state.request) runButton.disabled = false;
    }
  }

  function renderResults() {
    if (!window.QCInternalReportView) {
      showStatus(__('Thiếu thành phần hiển thị báo cáo QC.'), true);
      return;
    }
    const summary = window.QCInternalReportView.summarize(state.rows);
    window.QCInternalReportView.render({tab: state.active, summary, metrics, content});
    meta.textContent = __('Số nhóm dữ liệu: {0}', [state.rows.length.toLocaleString()]);
  }

  function showStatus(message, isError) {
    status.textContent = message;
    status.classList.toggle('is-error', Boolean(isError));
  }

  function normalizeRows(columns, rows) {
    const aliases = {
      occurreddate: 'occurredDate',
      companiescode: 'companiesCode',
      companiesname: 'companiesName',
      factoriescode: 'factoriesCode',
      factoriesname: 'factoriesName',
      linegroupscode: 'lineGroupsCode',
      linegroupsname: 'lineGroupsName',
      productionlinescode: 'productionLinesCode',
      productionlinesname: 'productionLinesName',
      customerscode: 'customersCode',
      customersname: 'customersName',
      productscode: 'productsCode',
      productsname: 'productsName',
      qcdefectscode: 'qcDefectsCode',
      qcdefectsname: 'qcDefectsName',
      eventtype: 'eventType',
      quantitysummary: 'quantitySummary',
    };
    const canonicalName = (name) => aliases[String(name).toLowerCase()] || name;
    const names = columns.map((column) => {
      const name = typeof column === 'string' ? column.split(':')[0] : column.label || column.fieldname || '';
      return canonicalName(name.split(':')[0]);
    });
    return rows.map((row) => {
      if (Array.isArray(row)) return Object.fromEntries(names.map((name, index) => [name, row[index]]));
      return Object.fromEntries(Object.entries(row).map(([name, value]) => [canonicalName(name), value]));
    });
  }

  function normalizeDate(value) {
    if (!value) return '';
    const date = String(value).trim();
    const iso = date.match(/^(\d{4})-(\d{1,2})-(\d{1,2})$/);
    if (iso) return `${iso[1]}-${iso[2].padStart(2, '0')}-${iso[3].padStart(2, '0')}`;
    const localized = date.match(/^(\d{1,2})[./-](\d{1,2})[./-](\d{4})$/);
    if (localized) {
      const [, day, month, year] = localized;
      return `${year}-${month.padStart(2, '0')}-${day.padStart(2, '0')}`;
    }
    return '';
  }

  function readDateInput(control) {
    return control.$input ? control.$input.val() : control.get_value();
  }

  const stylesheet = '/assets/factory_management/css/qc_internal_report.css';
  if (!document.querySelector(`link[href="${stylesheet}"]`)) {
    const link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = stylesheet;
    document.head.append(link);
  }
};
