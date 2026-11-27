window.QCInternalReportView = (() => {
  const inspectedTypes = new Set(['CumulativeSubtract', 'CumulativeAdd']);
  const number = new Intl.NumberFormat('vi-VN', {maximumFractionDigits: 0});
  const percent = new Intl.NumberFormat('vi-VN', {style: 'percent', maximumFractionDigits: 2});

  function summarize(rows) {
    const companies = new Map();
    const products = new Map();
    const dailyProduct = new Map();
    for (const row of rows) {
      const eventType = String(row.eventType || '');
      const qty = Number(row.quantitySummary || 0);
      const date = String(row.occurredDate || '').slice(0, 10);
      const line = row.productionLinesCode || '';
      const productCode = row.productsCode || '';
      const companyId = `${row.companiesCode || ''}|${row.companiesName || ''}`;
      let company = companies.get(companyId);
      if (!company) {
        company = {
          id: companyId,
          code: row.companiesCode || '',
          name: row.companiesName || __('Chưa gán công ty'),
          inspected: 0,
          defects: 0,
          days: new Map(),
          dailyProduct: new Map(),
          defectMap: new Map(),
        };
        companies.set(companyId, company);
      }
      const inspectedQty = inspectedTypes.has(eventType) ? qty : 0;
      const defectQty = eventType === 'DefectAdd' ? qty : 0;
      company.inspected += inspectedQty;
      company.defects += defectQty;

      let day = company.days.get(date);
      if (!day) {
        day = {date, inspected: 0, defects: 0};
        company.days.set(date, day);
      }
      day.inspected += inspectedQty;
      day.defects += defectQty;

      const dayProductKey = `${date}|${line}|${productCode}`;
      company.dailyProduct.set(dayProductKey, (company.dailyProduct.get(dayProductKey) || 0) + inspectedQty);

      if (defectQty && row.qcDefectsCode && row.qcDefectsName) {
        const defectKey = `${row.qcDefectsCode}|${row.qcDefectsName}`;
        const defect = company.defectMap.get(defectKey) || {
          code: row.qcDefectsCode,
          name: row.qcDefectsName,
          quantity: 0,
        };
        defect.quantity += defectQty;
        company.defectMap.set(defectKey, defect);
      }

      const productKey = `${productCode}|${row.productsName || ''}`;
      let product = products.get(productKey);
      if (!product) {
        product = {code: productCode, name: row.productsName || __('Chưa gán mã hàng'), inspected: 0, defects: 0};
        products.set(productKey, product);
      }
      product.inspected += inspectedQty;
      product.defects += defectQty;
    }

    const companyRows = Array.from(companies.values());
    const grandInspected = companyRows.reduce((sum, company) => sum + company.inspected, 0);
    const grandDefects = companyRows.reduce((sum, company) => sum + company.defects, 0);
    for (const company of companyRows) {
      company.defectRate = divide(company.defects, company.inspected);
      company.share = divide(company.inspected, grandInspected);
      company.averagePerDayLineProduct = company.dailyProduct.size
        ? Array.from(company.dailyProduct.values()).reduce((sum, value) => sum + value, 0) / company.dailyProduct.size
        : 0;
      company.trend = Array.from(company.days.values())
        .sort((left, right) => left.date.localeCompare(right.date))
        .map((day, index, values) => ({
          ...day,
          rate: divide(day.defects, day.inspected),
          direction: index === 0 || day.defects / (day.inspected || Infinity) === values[index - 1].defects / (values[index - 1].inspected || Infinity)
            ? 'flat'
            : day.defects / (day.inspected || Infinity) > values[index - 1].defects / (values[index - 1].inspected || Infinity) ? 'up' : 'down',
        }));
      company.topDefects = Array.from(company.defectMap.values())
        .sort((left, right) => right.quantity - left.quantity || left.code.localeCompare(right.code))
        .slice(0, 3)
        .map((defect) => ({...defect, share: divide(defect.quantity, company.defects)}));
      let rank = 0;
      let previous = null;
      company.rankedDefects = Array.from(company.defectMap.values())
        .sort((left, right) => right.quantity - left.quantity || left.code.localeCompare(right.code))
        .map((defect) => {
          if (previous !== defect.quantity) rank += 1;
          previous = defect.quantity;
          return {...defect, rank, share: divide(defect.quantity, company.defects), rate: divide(defect.quantity, company.inspected)};
        });
    }
    const productRows = Array.from(products.values())
      .map((product) => ({...product, passed: product.inspected - product.defects, rate: divide(product.defects, product.inspected)}))
      .sort((left, right) => right.defects - left.defects || left.code.localeCompare(right.code));
    return {
      companies: companyRows.sort((left, right) => right.inspected - left.inspected || left.name.localeCompare(right.name)),
      products: productRows,
      grandInspected,
      grandDefects,
      grandPassed: grandInspected - grandDefects,
      defectRate: divide(grandDefects, grandInspected),
    };
  }

  function render({tab, summary, metrics, content}) {
    renderMetrics(summary, metrics);
    if (tab === 'summary') renderOverview(summary, content);
    else if (tab === 'company') renderCompanies(summary, content);
    else if (tab === 'product') renderProducts(summary, content);
    else renderDefects(summary, content);
  }

  function renderMetrics(summary, target) {
    const cards = [
      ['Tổng kiểm', summary.grandInspected, 'blue'],
      ['Tổng lỗi', summary.grandDefects, 'red'],
      ['Số lượng đạt', summary.grandPassed, 'green'],
      ['Tỷ lệ lỗi', percent.format(summary.defectRate), 'orange'],
    ];
    target.replaceChildren();
    target.innerHTML = cards.map(([label, value, tone]) => `
      <article class="qc-ir-metric qc-ir-metric--${tone}">
        <div class="qc-ir-metric-label">${escapeHtml(__(label))}</div>
        <div class="qc-ir-metric-value">${escapeHtml(typeof value === 'number' ? number.format(value) : value)}</div>
      </article>`).join('');
  }

  function renderOverview(summary, target) {
    if (!summary.companies.length) return empty(target);
    target.innerHTML = `
      <div class="qc-ir-overview-scroll"><div class="qc-ir-overview">
        <div class="qc-ir-overview-head"><span>Công ty</span><span>Tỷ trọng</span><span>Tổng kiểm</span><span>Tổng lỗi</span><span>Tỷ lệ lỗi</span><span>TB kiểm/ngày</span><span>Top 3 lỗi</span><span>Biểu đồ lỗi theo ngày</span></div>
        ${summary.companies.map((company) => `
          <div class="qc-ir-overview-row">
            <div class="qc-ir-company-name" title="${escapeHtml(company.code)}">${escapeHtml(company.name)}</div>
            <div class="qc-ir-share" title="${escapeHtml(percent.format(company.share))}">${shareDots(company.share)}</div>
            <div class="qc-ir-number">${number.format(company.inspected)}</div>
            <div class="qc-ir-number qc-ir-danger">${number.format(company.defects)}</div>
            <div class="qc-ir-gauge-cell">${gauge(company.defectRate)}</div>
            <div class="qc-ir-number">${number.format(company.averagePerDayLineProduct)}</div>
            <div class="qc-ir-top-defects">${topDefects(company)}</div>
            <div class="qc-ir-trend-cell">${trendChart(company.trend)}</div>
          </div>`).join('')}
      </div></div>`;
  }

  function renderCompanies(summary, target) {
    if (!summary.companies.length) return empty(target);
    target.innerHTML = `<div class="qc-ir-company-list">${summary.companies.map((company) => `
      <article class="qc-ir-company-card">
        <div class="qc-ir-company-card-head">
          <div><div class="qc-ir-eyebrow">${escapeHtml(company.code || __('Công ty'))}</div><h3>${escapeHtml(company.name)}</h3></div>
          <div class="qc-ir-rate-pill">${percent.format(company.defectRate)}</div>
        </div>
        <div class="qc-ir-company-stats">
          <span><b>${number.format(company.inspected)}</b>Tổng kiểm</span>
          <span><b>${number.format(company.defects)}</b>Tổng lỗi</span>
          <span><b>${number.format(company.inspected - company.defects)}</b>Số lượng đạt</span>
          <span><b>${number.format(company.averagePerDayLineProduct)}</b>TB kiểm/ngày</span>
        </div>
        <div class="qc-ir-chart-title">Tỷ lệ lỗi theo ngày</div>${trendChart(company.trend, true)}
      </article>`).join('')}</div>`;
  }

  function renderProducts(summary, target) {
    if (!summary.products.length) return empty(target);
    target.innerHTML = `<div class="qc-ir-table-scroll"><table class="qc-ir-table">
      <thead><tr><th>#</th><th>Mã hàng</th><th>Tổng kiểm</th><th>Tổng lỗi</th><th>Số lượng đạt</th><th>Rate_Defect / Tỷ lệ lỗi</th></tr></thead>
      <tbody>${summary.products.map((product, index) => `
        <tr><td>${index + 1}</td><td><strong>${escapeHtml(product.code || product.name)}</strong><small>${escapeHtml(product.name)}</small></td>
        <td>${number.format(product.inspected)}</td><td class="qc-ir-danger">${number.format(product.defects)}</td><td>${number.format(product.passed)}</td>
        <td><div class="qc-ir-rate-cell"><span class="qc-ir-donut" style="--rate:${clamp(product.rate * 100, 0, 100)}%"><i></i></span><strong>${percent.format(product.rate)}</strong><span class="qc-ir-bar"><i style="width:${clamp(product.rate * 100, 0, 100)}%"></i></span></div></td></tr>`).join('')}</tbody>
    </table></div>`;
  }

  function renderDefects(summary, target) {
    const rows = summary.companies.flatMap((company) => company.rankedDefects.map((defect) => ({company, defect})));
    if (!rows.length) return empty(target);
    target.innerHTML = `<div class="qc-ir-table-scroll"><table class="qc-ir-table qc-ir-defect-table">
      <thead><tr><th>Công ty</th><th>Hạng</th><th>Mã lỗi</th><th>Loại lỗi</th><th>Số lượng lỗi</th><th>Tỷ trọng lỗi công ty</th><th>Tỷ lệ lỗi / tổng kiểm</th></tr></thead>
      <tbody>${rows.map(({company, defect}) => `
        <tr><td>${escapeHtml(company.name)}</td><td><span class="qc-ir-rank">${defect.rank}</span></td><td>${escapeHtml(defect.code)}</td><td><strong>${escapeHtml(defect.name)}</strong></td>
        <td class="qc-ir-danger">${number.format(defect.quantity)}</td><td>${percent.format(defect.share)}</td><td>${percent.format(defect.rate)}</td></tr>`).join('')}</tbody>
    </table></div>`;
  }

  function shareDots(share) {
    const filled = Math.round(clamp(share * 100, 0, 100));
    return `<span class="qc-ir-dots" aria-label="${escapeHtml(percent.format(share))}">${Array.from({length: 100}, (_, index) => `<i class="${index < filled ? 'is-filled' : ''}"></i>`).join('')}</span>`;
  }

  function gauge(rate) {
    const value = clamp(rate, 0, 1);
    const color = value > 0.5 ? '#dc2626' : value > 0.25 ? '#ea580c' : '#16a34a';
    const circumference = 125.66;
    return `<svg class="qc-ir-gauge" viewBox="0 0 100 62" role="img" aria-label="${escapeHtml(percent.format(rate))}">
      <path d="M10 54 A40 40 0 0 1 90 54" fill="none" stroke="#e2e8f0" stroke-width="9" stroke-linecap="round" />
      <path d="M10 54 A40 40 0 0 1 90 54" fill="none" stroke="${color}" stroke-width="9" stroke-linecap="round" stroke-dasharray="${(circumference * value).toFixed(2)} ${circumference}" />
      <text x="50" y="50" text-anchor="middle">${escapeHtml(percent.format(rate))}</text></svg>`;
  }

  function topDefects(company) {
    if (!company.topDefects.length) return '<span class="qc-ir-muted">—</span>';
    return company.topDefects.map((defect, index) => `<div class="qc-ir-top-defect"><span>${index + 1}. ${escapeHtml(defect.name)}</span><strong>${number.format(defect.quantity)} <small>(${percent.format(defect.share)})</small></strong></div>`).join('');
  }

  function trendChart(points, large = false) {
    if (!points.length) return '<div class="qc-ir-muted">Chưa có dữ liệu</div>';
    const width = large ? 760 : 420;
    const height = large ? 175 : 76;
    const left = 14;
    const right = width - 14;
    const top = 12;
    const bottom = height - 18;
    const max = Math.max(...points.map((point) => point.rate), 0.01);
    const positions = points.map((point, index) => ({
      ...point,
      x: points.length === 1 ? width / 2 : left + (index / (points.length - 1)) * (right - left),
      y: bottom - (point.rate / max) * (bottom - top),
    }));
    const path = positions.map((point, index) => `${index ? 'L' : 'M'}${point.x.toFixed(1)},${point.y.toFixed(1)}`).join(' ');
    const labels = [0, Math.floor((positions.length - 1) / 2), positions.length - 1];
    return `<svg class="qc-ir-trend ${large ? 'is-large' : ''}" viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" role="img" aria-label="${__('Tỷ lệ lỗi theo ngày')}">
      <path d="M${left},${bottom} H${right}" stroke="#e2e8f0" stroke-width="1" fill="none"/><path d="${path}" stroke="#f87171" stroke-width="2.5" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
      ${positions.map((point) => `<circle cx="${point.x.toFixed(1)}" cy="${point.y.toFixed(1)}" r="${large ? 4 : 3}" fill="${point.direction === 'up' ? '#dc2626' : point.direction === 'down' ? '#16a34a' : '#94a3b8'}"><title>${escapeHtml(formatDate(point.date))}: ${escapeHtml(percent.format(point.rate))}</title></circle>`).join('')}
      ${Array.from(new Set(labels)).map((index) => `<text x="${positions[index].x.toFixed(1)}" y="${height - 2}" text-anchor="middle">${escapeHtml(formatDate(points[index].date))}</text>`).join('')}</svg>`;
  }

  function empty(target) {
    target.innerHTML = `<div class="qc-ir-empty"><span>◎</span><strong>${__('Không có dữ liệu trong khoảng thời gian đã chọn')}</strong><small>${__('Thử thay đổi ngày hoặc bộ lọc để xem báo cáo.')}</small></div>`;
  }

  function divide(value, denominator) {
    return denominator ? value / denominator : 0;
  }

  function clamp(value, minimum, maximum) {
    return Math.min(Math.max(Number(value) || 0, minimum), maximum);
  }

  function formatDate(value) {
    const match = String(value || '').match(/^(\d{4})-(\d{2})-(\d{2})/);
    return match ? `${match[3]}/${match[2]}` : value;
  }

  function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>"']/g, (character) => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    }[character]));
  }

  return {summarize, render};
})();
