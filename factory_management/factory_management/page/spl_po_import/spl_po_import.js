frappe.pages['spl-po-import'].on_page_load = function (wrapper) {
  const page = frappe.ui.make_app_page({parent: wrapper, title: __('SPL PO Import'), single_column: true});
  const api = 'factory_management.spl_po.api.';
  const state = {previewRun: null, token: null, page: 1, pageSize: 100, excluded: new Set(), timer: null};
  const escape = frappe.utils.escape_html;
  const root = document.createElement('div');
  root.style.cssText = 'max-width:1100px;padding:24px 8px;display:grid;gap:18px;';
  page.body.append(root);

  const actions = document.createElement('div');
  actions.style.cssText = 'display:flex;flex-wrap:wrap;gap:8px;align-items:center;';
  root.append(actions);
  const addButton = (label, action, primary = false) => {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = primary ? 'btn btn-primary' : 'btn btn-default';
    button.textContent = __(label);
    button.addEventListener('click', action);
    actions.append(button);
    return button;
  };
  addButton('SPL Import Settings', () => frappe.set_route('Form', 'SPL Import Settings'));
  addButton('SPL Import Runs', () => frappe.set_route('List', 'SPL Import Run'));
  addButton('Test SPL Connection', () => start('test_connection'));
  addButton('Preview SPL Report', () => start('start_preview'), true);
  const uploadButton = addButton('Upload Workbook', () => upload.click());
  const upload = document.createElement('input');
  upload.type = 'file';
  upload.accept = '.xls,.xlsx';
  upload.hidden = true;
  root.append(upload);
  upload.addEventListener('change', async () => {
    if (!upload.files.length) return;
    if (upload.files[0].size > 20 * 1024 * 1024) {
      frappe.msgprint(__('SPL_FILE_SIZE_INVALID'));
      return;
    }
    const body = new FormData();
    body.append('file', upload.files[0]);
    body.append('is_private', '1');
    try {
      uploadButton.disabled = true;
      setStatus('Uploading workbook');
      const response = await fetch('/api/method/upload_file', {
        method: 'POST', body, credentials: 'same-origin',
        headers: {'X-Frappe-CSRF-Token': frappe.csrf_token},
      });
      const result = await response.json();
      if (!response.ok || !result.message?.file_url) throw new Error(__('SPL_UPLOAD_FAILED'));
      await start('start_preview', {file_url: result.message.file_url});
    } catch (error) { frappe.msgprint(error.message); }
    finally { uploadButton.disabled = false; upload.value = ''; }
  });

  const status = document.createElement('div');
  status.setAttribute('role', 'status');
  status.setAttribute('aria-live', 'polite');
  root.append(status);
  const setStatus = key => { status.textContent = __(key); };
  const summary = document.createElement('div');
  root.append(summary);
  const tableWrap = document.createElement('div');
  tableWrap.style.cssText = 'overflow-x:auto;';
  root.append(tableWrap);
  const footer = document.createElement('div');
  footer.style.cssText = 'display:flex;gap:8px;align-items:center;flex-wrap:wrap;';
  root.append(footer);

  async function call(method, args = {}) {
    const result = await frappe.call({method: api + method, args});
    return result.message;
  }
  async function start(method, args = {}) {
    try {
      state.excluded.clear();
      state.previewRun = null;
      state.token = null;
      tableWrap.replaceChildren();
      footer.replaceChildren();
      setStatus('SPL_JOB_QUEUED');
      const result = await call(method, args);
      poll(result.run_name);
    } catch (error) { setStatus('SPL_IMPORT_FAILED'); }
  }
  async function poll(runName) {
    clearTimeout(state.timer);
    try {
      const run = await call('get_run', {run_name: runName});
      status.textContent = run.message || __(run.status);
      if (run.status === 'Queued' || run.status === 'Running') {
        state.timer = setTimeout(() => poll(runName), 1500);
      } else if (run.status === 'Preview Ready') {
        state.previewRun = runName;
        state.token = run.snapshot_token;
        state.page = 1;
        await loadPage();
      } else if (run.error_detail) {
        const lines = document.createElement('pre');
        lines.textContent = run.error_detail;
        summary.replaceChildren(lines);
      }
    } catch (error) { setStatus('SPL_IMPORT_FAILED'); }
  }
  async function loadPage() {
    try {
      const data = await call('get_preview_page', {
        run_name: state.previewRun, token: state.token, page: state.page, page_size: state.pageSize,
      });
      summary.textContent = __('SPL_PREVIEW_SUMMARY', [data.total_rows, data.total_orders, data.errors, data.missing_masters]);
      const table = document.createElement('table');
      table.className = 'table table-bordered';
      const header = document.createElement('thead');
      header.innerHTML = '<tr>' + ['Select PO', 'Row', 'PO Number', 'Revision No', 'Sample Code', 'Market',
        'Product Color', 'Size', 'Order Qty', 'Status'].map(key => `<th>${escape(__(key))}</th>`).join('') + '</tr>';
      table.append(header);
      const body = document.createElement('tbody');
      for (const row of data.rows) {
        const tr = document.createElement('tr');
        const checkCell = tr.insertCell();
        const checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.checked = !state.excluded.has(row.row_number);
        checkbox.dataset.group = row.group_key;
        checkbox.setAttribute('aria-label', __('Select row {0}', [row.row_number]));
        checkbox.addEventListener('change', () => {
          for (const number of data.group_rows[row.group_key]) {
            if (checkbox.checked) state.excluded.delete(number);
            else state.excluded.add(number);
          }
          for (const other of body.querySelectorAll('input[type="checkbox"]')) {
            if (other.dataset.group === row.group_key) other.checked = checkbox.checked;
          }
        });
        checkCell.append(checkbox);
        for (const value of [row.row_number, row.po_number, row.revision_no, row.sample_code,
          row.market_code, row.color_code, row.size_code, row.order_qty,
          row.error || row.warnings?.join('; ') || __('Valid')]) {
          tr.insertCell().textContent = value ?? '';
        }
        body.append(tr);
      }
      table.append(body);
      tableWrap.replaceChildren(table);
      footer.replaceChildren();
      const button = (label, handler) => {
        const element = document.createElement('button');
        element.type = 'button';
        element.className = 'btn btn-default';
        element.textContent = __(label);
        element.addEventListener('click', handler);
        footer.append(element);
      };
      button('Previous', () => { if (state.page > 1) { state.page--; loadPage(); } });
      const pageLabel = document.createElement('span');
      pageLabel.textContent = __('Page {0} of {1}', [data.page, Math.max(1, Math.ceil(data.total_rows / data.page_size))]);
      footer.append(pageLabel);
      button('Next', () => { if (state.page * data.page_size < data.total_rows) { state.page++; loadPage(); } });
      button('Import Selected Rows', async () => {
        try {
          const result = await call('start_import', {
            run_name: state.previewRun, token: state.token, selected_rows: 'all',
            excluded_rows: JSON.stringify([...state.excluded]),
          });
          setStatus('SPL_JOB_QUEUED');
          poll(result.run_name);
        } catch (error) { frappe.msgprint(__('SPL_SELECTION_INCOMPLETE')); }
      });
    } catch (error) { setStatus('SPL_PREVIEW_EXPIRED'); }
  }
};
