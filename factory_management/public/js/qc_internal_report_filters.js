window.QCInternalReportFilters = (() => {
  const fields = [
    {fieldname: 'company', valueField: 'companyId', codeField: 'companiesCode', labelField: 'companiesName'},
    {fieldname: 'factory', valueField: 'factoryId', codeField: 'factoriesCode', labelField: 'factoriesName'},
    {fieldname: 'production_line', valueField: 'productionLineId', codeField: 'productionLinesCode', labelField: 'productionLinesName'},
    {fieldname: 'product', valueField: 'productId', codeField: 'productsCode', labelField: 'productsName'},
  ];

  function makeMultiControl(label, onChange) {
    const wrapper = document.createElement('div');
    wrapper.className = 'qc-ir-control qc-ir-multiselect';
    const labelElement = document.createElement('span');
    labelElement.className = 'control-label';
    labelElement.textContent = __(label);
    const trigger = document.createElement('button');
    trigger.type = 'button';
    trigger.className = 'form-control qc-ir-multiselect-trigger';
    trigger.setAttribute('aria-label', __(label));
    trigger.setAttribute('aria-haspopup', 'true');
    trigger.setAttribute('aria-expanded', 'false');
    const menu = document.createElement('div');
    menu.className = 'qc-ir-multiselect-menu';
    menu.hidden = true;
    const search = document.createElement('input');
    search.type = 'search';
    search.className = 'qc-ir-multiselect-search';
    search.placeholder = __('Tìm giá trị…');
    const optionList = document.createElement('div');
    optionList.className = 'qc-ir-multiselect-options';
    optionList.setAttribute('role', 'group');
    optionList.setAttribute('aria-label', __(label));
    const clearButton = document.createElement('button');
    clearButton.type = 'button';
    clearButton.className = 'qc-ir-multiselect-clear';
    clearButton.textContent = __('Bỏ chọn');
    menu.append(search, optionList, clearButton);
    wrapper.append(labelElement, trigger, menu);

    let options = [];
    const selected = new Set();
    trigger.addEventListener('click', () => {
      const opening = menu.hidden;
      menu.hidden = !opening;
      wrapper.classList.toggle('is-open', opening);
      trigger.setAttribute('aria-expanded', String(opening));
      if (opening) search.focus();
    });
    search.addEventListener('input', renderOptions);
    clearButton.addEventListener('click', () => {
      selected.clear();
      updateTrigger();
      renderOptions();
      onChange();
    });
    document.addEventListener('click', (event) => {
      if (!wrapper.contains(event.target)) closeMenu();
    });

    function closeMenu() {
      menu.hidden = true;
      wrapper.classList.remove('is-open');
      trigger.setAttribute('aria-expanded', 'false');
    }

    function updateTrigger() {
      const chosen = options.filter((item) => selected.has(item.value));
      trigger.textContent = chosen.length === 0
        ? __('Tất cả')
        : chosen.length === 1 ? chosen[0].label : chosen.length + ' ' + __('đã chọn');
      trigger.title = chosen.length ? chosen.map((item) => item.label).join(', ') : __('Tất cả');
    }

    function renderOptions() {
      const query = search.value.trim().toLocaleLowerCase();
      optionList.replaceChildren();
      const visible = options.filter((item) => item.label.toLocaleLowerCase().includes(query));
      if (!visible.length) {
        const empty = document.createElement('div');
        empty.className = 'qc-ir-multiselect-empty';
        empty.textContent = options.length ? __('Không tìm thấy giá trị') : __('Không có dữ liệu');
        optionList.append(empty);
        return;
      }
      visible.forEach((item) => {
        const option = document.createElement('label');
        option.className = 'qc-ir-multiselect-option';
        const checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.checked = selected.has(item.value);
        checkbox.addEventListener('change', () => {
          if (checkbox.checked) selected.add(item.value);
          else selected.delete(item.value);
          updateTrigger();
          onChange();
        });
        const text = document.createElement('span');
        text.textContent = item.label;
        option.append(checkbox, text);
        optionList.append(option);
      });
    }

    updateTrigger();
    return {
      wrapper,
      getValues: () => Array.from(selected),
      setOptions(nextOptions) {
        const unchanged = options.length === nextOptions.length && options.every((item, index) =>
          item.value === nextOptions[index].value && item.label === nextOptions[index].label
        );
        options = nextOptions;
        const available = new Set(options.map((item) => item.value));
        Array.from(selected).forEach((value) => {
          if (!available.has(value)) selected.delete(value);
        });
        updateTrigger();
        if (!unchanged) renderOptions();
      },
    };
  }

  function getOptions(rows, valueField, codeField, labelField) {
    const options = new Map();
    rows.forEach((row) => {
      const value = String(row[valueField] || '').trim();
      if (!value) return;
      const name = String(row[labelField] || '').trim();
      const code = String(row[codeField] || '').trim();
      const label = name && code ? name + ' (' + code + ')' : name || code || value;
      options.set(value, {value, label});
    });
    return Array.from(options.values()).sort((left, right) => left.label.localeCompare(right.label, 'vi'));
  }

  function updateOptions(rows, qc, activeFilters, controls) {
    const qcRows = rows.filter((row) => row.qc === qc);
    const selections = Object.fromEntries(fields.map((item) => [item.fieldname, controls[item.fieldname].getValues()]));
    let optionsByField = {};
    for (let attempt = 0; attempt <= fields.length; attempt++) {
      optionsByField = {};
      fields.forEach((item) => {
        if (!activeFilters.includes(item.fieldname)) return;
        const matchingRows = qcRows.filter((row) => activeFilters.every((fieldname) => {
          if (fieldname === item.fieldname || !selections[fieldname].length) return true;
          const other = fields.find((candidate) => candidate.fieldname === fieldname);
          return selections[fieldname].includes(String(row[other.valueField] || ''));
        }));
        optionsByField[item.fieldname] = getOptions(matchingRows, item.valueField, item.codeField, item.labelField);
      });
      let changed = false;
      activeFilters.forEach((fieldname) => {
        const available = new Set((optionsByField[fieldname] || []).map((item) => item.value));
        const valid = selections[fieldname].filter((value) => available.has(value));
        if (valid.length !== selections[fieldname].length) {
          selections[fieldname] = valid;
          changed = true;
        }
      });
      if (!changed) break;
    }
    Object.entries(optionsByField).forEach(([fieldname, options]) => controls[fieldname].setOptions(options));
  }

  function filterRows(rows, qc, activeFilters, controls) {
    return rows.filter((row) => {
      if (row.qc !== qc) return false;
      return activeFilters.every((fieldname) => {
        const item = fields.find((field) => field.fieldname === fieldname);
        const selected = controls[fieldname].getValues();
        return !selected.length || selected.includes(String(row[item.valueField] || ''));
      });
    });
  }

  function normalizeRows(columns, rows) {
    const aliases = {
      qc: 'qc', occurreddate: 'occurredDate', companiescode: 'companiesCode', companiesname: 'companiesName',
      companyid: 'companyId', factoryid: 'factoryId', productionlineid: 'productionLineId', productid: 'productId',
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

  return {fields, makeMultiControl, updateOptions, filterRows, normalizeRows, normalizeDate, readDateInput};
})();
