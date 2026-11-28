((global) => {
  const VERSION = '20261128g';
  const SEARCH_THRESHOLD = 5;

  const FIELD_SPECS = [
    { fieldname: 'qc', valueField: 'qc', labelField: 'qc', codeField: '', tabs: ['summary', 'device'] },
    { fieldname: 'company', valueField: 'companyId', labelField: 'companyName', codeField: 'companyCode', tabs: ['summary', 'device'] },
    { fieldname: 'product', valueField: 'productId', labelField: 'productCode', codeField: 'productName', tabs: ['summary', 'device'] },
    { fieldname: 'device', valueField: 'deviceId', labelField: 'deviceName', codeField: '', tabs: ['device'] },
    { fieldname: 'market', valueField: 'marketId', labelField: 'marketName', codeField: 'marketCode', tabs: ['device'] },
    { fieldname: 'color', valueField: 'colorId', labelField: 'colorCode', codeField: 'colorName', tabs: ['device'] },
    { fieldname: 'size', valueField: 'sizeId', labelField: 'sizeLabel', codeField: 'sizeCode', tabs: ['device'] },
  ];

  const t = (text, args) => {
    if (typeof global.__ === 'function') return global.__(text, args);
    if (!Array.isArray(args)) return text;
    return text.replace(/\{(\d+)\}/g, (_, idx) => (args[idx] !== undefined ? args[idx] : ''));
  };

  function fieldsForTab(tab) {
    return FIELD_SPECS.filter((spec) => spec.tabs.includes(tab));
  }

  function formatOptionLabel(row, spec, value) {
    const primary = String(row[spec.labelField] || '').trim();
    const secondary = spec.codeField ? String(row[spec.codeField] || '').trim() : '';
    if (primary && secondary && primary !== secondary) {
      return `${primary} (${secondary})`;
    }
    return primary || secondary || value;
  }

  function getOptions(rows, spec) {
    const map = new Map();
    for (const row of rows) {
      const value = String(row[spec.valueField] || '').trim();
      if (!value || map.has(value)) continue;
      map.set(value, { value, label: formatOptionLabel(row, spec, value) });
    }
    return Array.from(map.values()).sort((a, b) => a.label.localeCompare(b.label, 'vi'));
  }

  function matchesSelections(row, specs, selections, skipFieldname) {
    return specs.every((other) => {
      if (other.fieldname === skipFieldname) return true;
      const chosen = selections[other.fieldname];
      if (!chosen.length) return true;
      return chosen.includes(String(row[other.valueField] || '').trim());
    });
  }

  function resolvePriorityConflicts(rows, activeSpecs, selections, priorityField) {
    const prioritySpec = activeSpecs.find((spec) => spec.fieldname === priorityField);
    if (!prioritySpec) return;

    const availablePriority = new Set(getOptions(rows, prioritySpec).map((item) => item.value));
    selections[priorityField] = selections[priorityField].filter((val) => availablePriority.has(val));
    if (!selections[priorityField].length) return;

    const priorityRows = rows.filter((row) => (
      selections[priorityField].includes(String(row[prioritySpec.valueField] || '').trim())
    ));
    for (const spec of activeSpecs) {
      if (spec.fieldname === priorityField) continue;
      const allowed = new Set(getOptions(priorityRows, spec).map((item) => item.value));
      selections[spec.fieldname] = selections[spec.fieldname].filter((val) => allowed.has(val));
    }

    // Keep priorityField locked if older siblings conflict with one another (e.g. stale color + size).
    const priorityIdx = activeSpecs.findIndex((spec) => spec.fieldname === priorityField);
    const pruneOrder = [
      ...activeSpecs.slice(priorityIdx + 1).reverse(),
      ...activeSpecs.slice(0, priorityIdx).reverse(),
    ];
    for (const victim of pruneOrder) {
      if (!selections[victim.fieldname].length) continue;
      const supported = new Set(
        getOptions(rows.filter((row) => matchesSelections(row, activeSpecs, selections, priorityField)), prioritySpec)
          .map((item) => item.value)
      );
      if (selections[priorityField].every((val) => supported.has(val))) break;
      selections[victim.fieldname] = [];
    }
  }

  function computeCascadingOptions(rows, tab, currentSelections, priorityField) {
    const activeSpecs = fieldsForTab(tab);
    const selections = {};
    for (const spec of activeSpecs) {
      selections[spec.fieldname] = Array.isArray(currentSelections[spec.fieldname])
        ? [...currentSelections[spec.fieldname]]
        : [];
    }

    if (priorityField && selections[priorityField] && selections[priorityField].length) {
      resolvePriorityConflicts(rows, activeSpecs, selections, priorityField);
    }

    let optionsByField = {};
    for (let pass = 0; pass <= activeSpecs.length; pass++) {
      optionsByField = {};
      for (const spec of activeSpecs) {
        const matchingRows = rows.filter((row) => matchesSelections(row, activeSpecs, selections, spec.fieldname));
        optionsByField[spec.fieldname] = getOptions(matchingRows, spec);
      }

      let changed = false;
      for (const spec of activeSpecs) {
        if (spec.fieldname === priorityField && selections[spec.fieldname].length) continue;
        const available = new Set(optionsByField[spec.fieldname].map((item) => item.value));
        const valid = selections[spec.fieldname].filter((val) => available.has(val));
        if (valid.length !== selections[spec.fieldname].length) {
          selections[spec.fieldname] = valid;
          changed = true;
        }
      }
      if (!changed) break;
    }

    return { optionsByField, selections };
  }

  function updateOptions(rows, tab, controls, changedField) {
    const activeSpecs = fieldsForTab(tab);
    const current = Object.fromEntries(activeSpecs.map((spec) => [spec.fieldname, controls[spec.fieldname].getValues()]));
    const { optionsByField } = computeCascadingOptions(rows, tab, current, changedField);
    for (const spec of activeSpecs) {
      controls[spec.fieldname].setOptions(optionsByField[spec.fieldname] || []);
    }
  }

  function makeMultiControl(label, fieldname, onChange) {
    const doc = global.document;
    const wrapper = doc.createElement('div');
    wrapper.className = 'uqqc-report__date-control uqqc-rpt-multiselect';
    wrapper.dataset.fieldname = fieldname;

    const labelEl = doc.createElement('label');
    labelEl.className = 'control-label';
    labelEl.textContent = t(label);

    const trigger = doc.createElement('button');
    trigger.type = 'button';
    trigger.className = 'form-control uqqc-rpt-multiselect-trigger';
    trigger.setAttribute('aria-label', t(label));
    trigger.setAttribute('aria-haspopup', 'true');
    trigger.setAttribute('aria-expanded', 'false');
    const triggerText = doc.createElement('span');
    triggerText.className = 'uqqc-rpt-multiselect-value';
    trigger.append(triggerText);

    const menu = doc.createElement('div');
    menu.className = 'uqqc-rpt-multiselect-menu';
    menu.hidden = true;

    const search = doc.createElement('input');
    search.type = 'search';
    search.className = 'uqqc-rpt-multiselect-search';
    search.placeholder = t('Search…');

    const optionList = doc.createElement('div');
    optionList.className = 'uqqc-rpt-multiselect-options';
    optionList.setAttribute('role', 'group');
    optionList.setAttribute('aria-label', t(label));

    const footer = doc.createElement('div');
    footer.className = 'uqqc-rpt-multiselect-footer';
    const clearButton = doc.createElement('button');
    clearButton.type = 'button';
    clearButton.className = 'uqqc-rpt-multiselect-clear';
    clearButton.textContent = t('Clear');
    footer.append(clearButton);

    menu.append(search, optionList, footer);
    wrapper.append(labelEl, trigger, menu);

    let options = [];
    const selected = new Set();

    function closeMenu() {
      menu.hidden = true;
      wrapper.classList.remove('is-open');
      menu.classList.remove('is-align-right');
      trigger.setAttribute('aria-expanded', 'false');
      if (search.value) {
        search.value = '';
        renderOptions();
      }
    }

    function openMenu() {
      // Close other open dropdowns before positioning this one.
      doc.dispatchEvent(new global.CustomEvent('uqqc-filter-open', { detail: { owner: wrapper } }));
      menu.hidden = false;
      wrapper.classList.add('is-open');
      trigger.setAttribute('aria-expanded', 'true');

      const rect = trigger.getBoundingClientRect ? trigger.getBoundingClientRect() : { left: 0 };
      const alignRight = rect.left + 260 > (global.innerWidth || 1024) - 12;
      menu.classList.toggle('is-align-right', alignRight);

      // Focus search only on desktop mouse/trackpad so tablets do not pop up the keyboard.
      const finePointer = global.matchMedia
        && global.matchMedia('(hover: hover) and (pointer: fine)').matches;
      if (finePointer && !search.hidden) {
        search.focus();
      }
    }

    trigger.addEventListener('click', () => {
      if (menu.hidden) openMenu();
      else closeMenu();
    });

    search.addEventListener('input', renderOptions);

    clearButton.addEventListener('click', () => {
      if (!selected.size) return;
      selected.clear();
      updateTrigger();
      renderOptions();
      onChange();
    });

    doc.addEventListener('uqqc-filter-open', (event) => {
      if (event.detail && event.detail.owner !== wrapper) closeMenu();
    });
    doc.addEventListener('click', (event) => {
      if (!wrapper.contains(event.target)) closeMenu();
    });
    wrapper.addEventListener('keydown', (event) => {
      if (event.key === 'Escape' && !menu.hidden) {
        closeMenu();
        trigger.focus();
      }
    });

    function updateTrigger() {
      const chosen = options.filter((item) => selected.has(item.value));
      clearButton.disabled = chosen.length === 0;
      if (chosen.length === 0) {
        triggerText.textContent = t('All');
        trigger.title = t('All');
        trigger.classList.add('is-placeholder');
      } else if (chosen.length === 1) {
        triggerText.textContent = chosen[0].label;
        trigger.title = chosen[0].label;
        trigger.classList.remove('is-placeholder');
      } else {
        const text = t('{0} selected', [chosen.length]);
        triggerText.textContent = text;
        trigger.title = chosen.map((item) => item.label).join(', ');
        trigger.classList.remove('is-placeholder');
      }
    }

    function renderOptions() {
      const showSearch = options.length > SEARCH_THRESHOLD;
      search.hidden = !showSearch;
      if (!showSearch && search.value) search.value = '';

      const query = search.value.trim().toLocaleLowerCase();
      optionList.replaceChildren();
      const visible = query
        ? options.filter((item) => item.label.toLocaleLowerCase().includes(query))
        : options;

      if (!visible.length) {
        const empty = doc.createElement('div');
        empty.className = 'uqqc-rpt-multiselect-empty';
        empty.textContent = options.length ? t('No matching values') : t('No data in report');
        optionList.append(empty);
        clearButton.disabled = selected.size === 0;
        return;
      }

      for (const item of visible) {
        const option = doc.createElement('label');
        option.className = 'uqqc-rpt-multiselect-option';
        const checkbox = doc.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.checked = selected.has(item.value);
        checkbox.addEventListener('change', () => {
          if (checkbox.checked) selected.add(item.value);
          else selected.delete(item.value);
          updateTrigger();
          clearButton.disabled = selected.size === 0;
          onChange();
        });
        const text = doc.createElement('span');
        text.textContent = item.label;
        option.append(checkbox, text);
        optionList.append(option);
      }
      clearButton.disabled = selected.size === 0;
    }

    updateTrigger();
    renderOptions();

    return {
      wrapper,
      getValues: () => Array.from(selected),
      setOptions(nextOptions) {
        const unchanged = options.length === nextOptions.length && options.every((item, idx) => (
          item.value === nextOptions[idx].value && item.label === nextOptions[idx].label
        ));
        options = nextOptions;
        const available = new Set(options.map((item) => item.value));
        for (const val of Array.from(selected)) {
          if (!available.has(val)) selected.delete(val);
        }
        updateTrigger();
        if (!unchanged) renderOptions();
      },
    };
  }

  const exported = {
    version: VERSION,
    FIELD_SPECS,
    fieldsForTab,
    getOptions,
    computeCascadingOptions,
    updateOptions,
    makeMultiControl,
  };

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = exported;
  } else {
    global.UQQCReportFilters = exported;
  }
})(typeof window !== 'undefined' ? window : globalThis);
