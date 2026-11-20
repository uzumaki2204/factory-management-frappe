frappe.pages['trim-import'].on_page_load = function (wrapper) {
  const page = frappe.ui.make_app_page({parent: wrapper, title: __('Trim Import'), single_column: true});
  const api = 'factory_management.trim.api.';
  const state = {run: null, token: null, page: 1, polling: null, importing: false};
  const root = document.createElement('div');
  root.style.cssText = 'padding:24px 8px;display:grid;gap:16px;width:100%;box-sizing:border-box';
  page.body.append(root);
  const actions = document.createElement('div');
  actions.style.cssText = 'display:flex;gap:8px;flex-wrap:wrap;align-items:center';
  root.append(actions);
  const button = (label, handler, primary = false) => {
    const element = document.createElement('button');
    element.type = 'button';
    element.className = primary ? 'btn btn-primary' : 'btn btn-default';
    element.textContent = __(label);
    element.addEventListener('click', handler);
    actions.append(element);
    return element;
  };
  button('Trim Orders', () => frappe.set_route('List', 'Trim'));
  button('Import History', () => frappe.set_route('List', 'Trim Import Run'));
  const upload = document.createElement('input');
  upload.type = 'file';
  upload.accept = '.xlsx';
  upload.hidden = true;
  root.append(upload);
  const uploadButton = button('Upload Trim Workbook', () => upload.click(), true);
  const status = document.createElement('div');
  status.setAttribute('role', 'status');
  root.append(status);
  const summary = document.createElement('div');
  root.append(summary);
  const tableWrap = document.createElement('div');
  tableWrap.style.cssText = 'width:100%;overflow-x:auto';
  root.append(tableWrap);
  const footer = document.createElement('div');
  footer.style.cssText = 'display:flex;gap:10px;align-items:center;flex-wrap:wrap';
  root.append(footer);

  async function call(method, args = {}) {
    const result = await frappe.call({method: api + method, args});
    return result.message;
  }

  function showStatus(message) { status.textContent = __(message || ''); }
  function stopPolling() { if (state.polling) clearTimeout(state.polling); state.polling = null; }
  async function poll(runName, purpose) {
    try {
      const run = await call('get_run', {run_name: runName});
      showStatus(`${run.status}: ${run.message || ''} ${run.imported_orders || 0}/${run.total_orders || 0} orders, ${run.imported_items || 0}/${run.total_rows || 0} rows`);
      if (run.status === 'Queued' || run.status === 'Running') {
        state.polling = setTimeout(() => poll(runName, purpose), 2500);
      } else if (purpose === 'preview' && run.status === 'Preview Ready') {
        state.run = runName;
        state.token = run.snapshot_token;
        state.page = 1;
        await loadPage();
      } else if (purpose === 'import') {
        state.importing = false;
        footer.replaceChildren();
        if (run.error_detail) {
          const errors = document.createElement('pre');
          errors.textContent = run.error_detail;
          footer.append(errors);
        }
      }
    } catch (error) {
      showStatus(error.message || 'Could not read import status.');
      state.polling = setTimeout(() => poll(runName, purpose), 5000);
    }
  }

  async function loadPage() {
    try {
      const data = await call('get_preview_page', {
        run_name: state.run, token: state.token, page: state.page,
      });
      summary.textContent = `${data.total_orders} orders · ${data.total_rows} rows · ` +
        Object.entries(data.status_counts).map(([key, count]) => `${key}: ${count}`).join(' · ');
      const table = document.createElement('table');
      table.className = 'table table-bordered';
      table.style.cssText = 'min-width:1050px;width:100%';
      const head = table.createTHead().insertRow();
      for (const label of ['Row', 'Order No', 'Revision', 'Status', 'Raw Material Code',
        'Supplier Material Code', 'Item Code', 'Color', 'Size', 'Qty']) {
        const cell = document.createElement('th');
        cell.textContent = __(label);
        head.append(cell);
      }
      const body = table.createTBody();
      for (const row of data.rows) {
        const tr = body.insertRow();
        for (const value of [row.row_number, row.order_no, row.revision_no,
          row.document_status, row.raw_material_code, row.supplier_raw_material_code,
          row.item_code, row.color, row.size, row.order_qty]) {
          tr.insertCell().textContent = value ?? '';
        }
      }
      tableWrap.replaceChildren(table);
      footer.replaceChildren();
      const footerButton = (label, handler, primary = false) => {
        const element = document.createElement('button');
        element.type = 'button';
        element.className = primary ? 'btn btn-primary' : 'btn btn-default';
        element.textContent = __(label);
        element.addEventListener('click', handler);
        footer.append(element);
        return element;
      };
      footerButton('Previous', () => { if (state.page > 1) { state.page--; loadPage(); } });
      footer.append(document.createTextNode(`${data.page} / ${Math.ceil(data.total_rows / data.page_size)}`));
      footerButton('Next', () => {
        if (state.page * data.page_size < data.total_rows) { state.page++; loadPage(); }
      });
      const importButton = footerButton('Import All Orders', async () => {
        if (state.importing) return;
        state.importing = true;
        importButton.disabled = true;
        try {
          const result = await call('start_import', {run_name: state.run, token: state.token});
          showStatus('Import queued');
          poll(result.run_name, 'import');
        } catch (error) {
          state.importing = false;
          importButton.disabled = false;
          frappe.msgprint(error.message || __('Import failed'));
        }
      }, true);
      importButton.disabled = state.importing;
    } catch (error) {
      showStatus(error.message || 'Preview has expired. Upload the workbook again.');
    }
  }

  upload.addEventListener('change', async () => {
    const file = upload.files[0];
    if (!file) return;
    if (file.size > 20 * 1024 * 1024 || !file.name.toLowerCase().endsWith('.xlsx')) {
      frappe.msgprint(__('Choose an .xlsx workbook under 20 MB.'));
      return;
    }
    stopPolling();
    state.run = null;
    state.token = null;
    tableWrap.replaceChildren();
    footer.replaceChildren();
    summary.textContent = '';
    const data = new FormData();
    data.append('file', file);
    data.append('is_private', '1');
    uploadButton.disabled = true;
    showStatus('Uploading workbook');
    try {
      const response = await fetch('/api/method/upload_file', {
        method: 'POST', body: data, credentials: 'same-origin',
        headers: {'X-Frappe-CSRF-Token': frappe.csrf_token},
      });
      const payload = await response.json();
      if (!response.ok || !payload.message?.file_url) throw new Error(__('Upload failed'));
      const run = await call('start_preview', {file_url: payload.message.file_url});
      showStatus('Preparing preview');
      poll(run.run_name, 'preview');
    } catch (error) {
      frappe.msgprint(error.message || __('Upload failed'));
      showStatus('Upload failed');
    } finally {
      uploadButton.disabled = false;
      upload.value = '';
    }
  });
};
