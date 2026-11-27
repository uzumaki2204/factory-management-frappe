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

  const controls = {
    company: makeControl('CÔNG TY', 'company', 'Link', '', 'Company', __('All')),
    factory: makeControl('XƯỞNG', 'factory', 'Link', '', 'Factory', __('All')),
    production_line: makeControl('CHUYỀN', 'production_line', 'Link', '', 'Production Line', __('All')),
    product: makeControl('MÃ HÀNG', 'product', 'Link', '', 'Product', __('All')),
    qc: makeControl('QC', 'qc', 'Select', 'QC1', '\nAll\nQC1\nQC2'),
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
  refreshButton.addEventListener('click', runReport);
  tabs.addEventListener('click', (event) => {
    const button = event.target.closest('[data-tab]');
    if (button) selectTab(button.dataset.tab);
  });

  let ready = false;
  let refreshTimer;
  Object.values(controls).forEach(({control}) => {
    if (control.$input) control.$input.on('change awesomplete-selectcomplete', scheduleReport);
  });
  selectTab('summary', false);
  ready = true;
  runReport();

  function makeControl(label, fieldname, fieldtype, defaultValue = '', options = '', placeholder = '') {
    const wrapper = document.createElement('div');
    wrapper.className = 'qc-ir-control';
    const df = {fieldtype, fieldname, label: __(label), options, default: defaultValue};
    if (placeholder) df.placeholder = placeholder;
    const control = frappe.ui.form.make_control({parent: wrapper, df, render_input: true});
    control.refresh();
    if (defaultValue) control.set_value(defaultValue);
    return {wrapper, control};
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
    if (refresh && ready) runReport();
  }

  function scheduleReport() {
    if (!ready) return;
    window.clearTimeout(refreshTimer);
    refreshTimer = window.setTimeout(runReport, 400);
  }

  async function runReport() {
    const request = ++state.request;
    const fromDate = normalizeDate(readDateInput(controls.from_date.control));
    const toDate = normalizeDate(readDateInput(controls.to_date.control));
    if (!fromDate || !toDate || fromDate > toDate) {
      showStatus(__('Vui lòng chọn khoảng ngày hợp lệ.'), true);
      return;
    }
    showStatus(__('Đang tải dữ liệu QC…'), false);
    content.replaceChildren();
    refreshButton.disabled = true;
    const filters = {
      from_date: fromDate,
      to_date: toDate,
      qc: controls.qc.control.get_value() === 'All' ? '' : controls.qc.control.get_value() || '',
      company: state.active === 'summary' ? '' : controls.company.control.get_value() || '',
      factory: state.active === 'summary' ? '' : controls.factory.control.get_value() || '',
      line_group: '',
      production_line: state.active === 'summary' ? '' : controls.production_line.control.get_value() || '',
      customer: '',
      product: controls.product.control.get_value() || '',
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
      state.rows = normalizeRows(result.columns || [], result.result || []);
      showStatus('', false);
      renderResults();
    } catch (error) {
      if (request !== state.request) return;
      state.rows = [];
      content.replaceChildren();
      showStatus(__('Không tải được dữ liệu QC. Kiểm tra quyền báo cáo và bộ lọc.'), true);
      console.error('QC Internal Report failed', error);
    } finally {
      if (request === state.request) refreshButton.disabled = false;
    }
  }

  function renderResults() {
    if (!window.QCInternalReportView) {
      showStatus(__('Thiếu thành phần hiển thị báo cáo QC.'), true);
      return;
    }
    const summary = window.QCInternalReportView.summarize(state.rows);
    window.QCInternalReportView.render({tab: state.active, summary, content});
  }

  function showStatus(message, isError) {
    status.textContent = message;
    status.classList.toggle('is-error', Boolean(isError));
    status.classList.toggle('is-visible', Boolean(message));
  }

  function normalizeRows(columns, rows) {
    const aliases = {
      occurreddate: 'occurredDate', companiescode: 'companiesCode', companiesname: 'companiesName',
      factoriescode: 'factoriesCode', factoriesname: 'factoriesName',
      linegroupscode: 'lineGroupsCode', linegroupsname: 'lineGroupsName',
      productionlinescode: 'productionLinesCode', productionlinesname: 'productionLinesName',
      customerscode: 'customersCode', customersname: 'customersName',
      productscode: 'productsCode', productsname: 'productsName',
      qcdefectscode: 'qcDefectsCode', qcdefectsname: 'qcDefectsName',
      eventtype: 'eventType', quantitysummary: 'quantitySummary',
    };
    const canonical = (name) => aliases[String(name).toLowerCase()] || name;
    const names = columns.map((column) => {
      const name = typeof column === 'string' ? column.split(':')[0] : column.label || column.fieldname || '';
      return canonical(name.split(':')[0]);
    });
    return rows.map((row) => Array.isArray(row)
      ? Object.fromEntries(names.map((name, index) => [name, row[index]]))
      : Object.fromEntries(Object.entries(row).map(([name, value]) => [canonical(name), value])));
  }

  function normalizeDate(value) {
    if (!value) return '';
    const date = String(value).trim();
    const iso = date.match(/^(\d{4})-(\d{1,2})-(\d{1,2})$/);
    if (iso) return iso[1] + '-' + iso[2].padStart(2, '0') + '-' + iso[3].padStart(2, '0');
    const localized = date.match(/^(\d{1,2})[./-](\d{1,2})[./-](\d{4})$/);
    if (localized) return localized[3] + '-' + localized[2].padStart(2, '0') + '-' + localized[1].padStart(2, '0');
    return '';
  }

  function readDateInput(control) {
    return control.$input ? control.$input.val() : control.get_value();
  }

  const stylesheet = '/assets/factory_management/css/qc_internal_report.css';
  if (!document.querySelector('link[href="' + stylesheet + '"]')) {
    const link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = stylesheet;
    document.head.append(link);
  }
};
