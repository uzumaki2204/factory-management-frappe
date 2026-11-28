window.QCInternalReportView = (() => {
  const version = '20261128f';
  const inspectTypes = new Set(['CumulativeSubtract', 'CumulativeAdd']);
  const num = new Intl.NumberFormat('vi-VN', {maximumFractionDigits: 0});
  const pct = new Intl.NumberFormat('vi-VN', {style: 'percent', maximumFractionDigits: 0});
  const companyNameCollator = new Intl.Collator('vi', {numeric: true});
  const companyColors = [
    '#7b168c', '#1496ee', '#202ca6', '#f26435', '#00a878',
    '#d92662', '#c98a00', '#0f766e', '#6d4c41', '#475569',
  ];
  const defectColors = ['#168dee', '#86128f', '#202ca6'];

  function companyColor(index) {
    if (index < companyColors.length) return companyColors[index];
    return 'hsl(' + Math.round((index * 137.508) % 360) + ', 68%, 42%)';
  }

  function summarize(rows) {
    const companies = new Map(), products = new Map(), defects = new Map(), daily = new Map();
    rows.forEach((row) => {
      const type = String(row.eventType || ''), qty = Number(row.quantitySummary || 0);
      const date = String(row.occurredDate || '').slice(0, 10);
      const line = row.productionLinesCode || '', productCode = row.productsCode || '';
      const companyKey = String(row.companiesCode || '') + '|' + String(row.companiesName || '');
      let company = companies.get(companyKey);
      if (!company) {
        company = {code: row.companiesCode || '', name: row.companiesName || __('Chưa gán công ty'),
          inspected: 0, defects: 0, days: new Map(), lineDays: new Map(), defectMap: new Map()};
        companies.set(companyKey, company);
      }
      const inspected = inspectTypes.has(type) ? qty : 0;
      const defectQty = type === 'DefectAdd' ? qty : 0;
      company.inspected += inspected;
      company.defects += defectQty;
      let day = company.days.get(date);
      if (!day) { day = {date, inspected: 0, defects: 0}; company.days.set(date, day); }
      day.inspected += inspected;
      day.defects += defectQty;
      const key = date + '|' + line + '|' + productCode;
      company.lineDays.set(key, (company.lineDays.get(key) || 0) + inspected);
      daily.set(key, (daily.get(key) || 0) + inspected);
      if (defectQty) {
        const code = row.qcDefectsCode || row.qcDefectsName || __('Chưa phân loại');
        const name = row.qcDefectsName || code;
        add(defects, code, name, defectQty);
        add(company.defectMap, code, name, defectQty);
      }
      const productKey = String(productCode) + '|' + String(row.productsName || '');
      let product = products.get(productKey);
      if (!product) { product = {code: productCode, name: row.productsName || __('Chưa gán mã hàng'), inspected: 0, defects: 0}; products.set(productKey, product); }
      product.inspected += inspected;
      product.defects += defectQty;
    });

    const companyRows = Array.from(companies.values());
    const totalInspected = companyRows.reduce((n, item) => n + item.inspected, 0);
    const totalDefects = companyRows.reduce((n, item) => n + item.defects, 0);
    companyRows.forEach((company) => {
      company.passed = company.inspected - company.defects;
      company.share = ratio(company.inspected, totalInspected);
      company.defectRate = ratio(company.defects, company.inspected);
      company.passRate = ratio(company.passed, company.inspected);
      company.average = mean(company.lineDays);
      company.defectMap = Array.from(company.defectMap.values()).sort(byQuantity);
      company.topDefects = company.defectMap.slice(0, 3).map((item) => ({...item, share: ratio(item.quantity, company.defects)}));
      const days = Array.from(company.days.values()).sort((a, b) => a.date.localeCompare(b.date));
      company.trend = days.map((item, index) => {
        const rate = ratio(item.defects, item.inspected);
        const prev = index ? ratio(days[index - 1].defects, days[index - 1].inspected) : null;
        return {...item, rate, direction: prev === null ? 'first' : rate > prev ? 'up' : rate < prev ? 'down' : 'flat'};
      });
    });
    const productRows = Array.from(products.values()).map((item) => ({
      ...item, passed: item.inspected - item.defects, rate: ratio(item.defects, item.inspected),
    })).sort((a, b) => b.rate - a.rate || b.defects - a.defects || a.code.localeCompare(b.code));
    const defectRows = Array.from(defects.values())
      .map((item) => ({...item, share: ratio(item.quantity, totalDefects)})).sort(byQuantity);
    return {
      companies: companyRows.sort((a, b) => b.inspected - a.inspected || a.name.localeCompare(b.name)),
      products: productRows, defects: defectRows, topDefects: defectRows.slice(0, 3),
      totalInspected, totalDefects, totalPassed: totalInspected - totalDefects,
      defectRate: ratio(totalDefects, totalInspected), passRate: ratio(totalInspected - totalDefects, totalInspected),
      average: mean(daily),
    };
  }

  function add(map, code, name, quantity) {
    const key = String(code) + '|' + String(name);
    const item = map.get(key) || {code: String(code), name: String(name), quantity: 0};
    item.quantity += quantity;
    map.set(key, item);
  }

  function render({tab, summary, content}) {
    if (tab === 'summary') overview(summary, content);
    else if (tab === 'company') companyPage(summary, content);
    else if (tab === 'product') productPage(summary, content);
    else defectPage(summary, content);
  }

  function overview(s, target) {
    if (!s.companies.length) return empty(target);
    const companies = s.companies.slice().sort((a, b) => companyNameCollator.compare(a.name, b.name));
    const rows = companies.map((c) =>
      '<div class="qc-ir-overview-row"><div class="qc-ir-company-name">' + esc(c.name) + '</div>' +
      '<div class="qc-ir-share"><strong>' + pct.format(c.share) + '</strong>' + dots(c.share) + '</div>' +
      '<div class="qc-ir-number">' + num.format(c.inspected) + '</div><div class="qc-ir-number qc-ir-danger">' + num.format(c.defects) + '</div>' +
      '<div>' + gauge(c.defectRate) + '</div><div class="qc-ir-number">' + num.format(c.average) + '</div>' +
      '<div class="qc-ir-top-defects">' + top3(c) + '</div><div class="qc-ir-trend-cell">' + trend(c) + '</div></div>'
    ).join('');
    target.innerHTML = '<div class="qc-ir-overview-scroll"><div class="qc-ir-overview">' +
      '<div class="qc-ir-overview-head"><span>Công ty</span><span>Tỷ trọng</span><span>Tổng kiểm</span><span>Tổng lỗi</span><span>Tỷ lệ lỗi</span><span>Trung bình<br>kiểm/ngày</span><span>Top 3 lỗi</span><span>Biểu đồ lỗi theo ngày</span></div>' + rows +
      '</div></div>';
  }

  function companyPage(s, target) {
    if (!s.companies.length) return empty(target);
    const topCodes = s.topDefects.map((item) => item.code);
    target.innerHTML = '<div class="qc-ir-company-page"><div class="qc-ir-company-kpis">' +
      barPanel(s.companies, 'inspected', 'TỔNG HÀNG KIỂM', '#168dee', (c) => c.share) +
      barPanel(s.companies, 'defects', 'TỔNG HÀNG LỖI', '#d94655', (c) => c.defectRate) +
      barPanel(s.companies, 'passed', 'TỔNG HÀNG ĐẠT', '#00c853', (c) => c.passRate) +
      '</div><div class="qc-ir-company-analysis">' + groupedDefects(s.companies, topCodes) +
      '<section class="qc-ir-chart-panel"><h2>TỶ LỆ LỖI THEO NGÀY</h2>' + companyTrend(s.companies) + '</section></div></div>';
  }

  function barPanel(companies, field, title, color, ratioFn) {
    const list = companies.slice().sort((a, b) => b[field] - a[field]);
    const max = Math.max(1, ...list.map((c) => c[field]));
    const bars = list.map((c) => '<div class="qc-ir-bar-column" title="' + esc(c.name + ': ' + num.format(c[field])) + '">' +
      '<strong>' + num.format(c[field]) + '</strong><div class="qc-ir-column-plot"><i style="--bar-height:' + Math.max(3, c[field] / max * 100) + '%;--bar-color:' + color + '"><b>' + pct.format(ratioFn(c)) + '</b></i></div>' +
      '<span>' + esc(c.name) + '</span></div>').join('');
    return '<section class="qc-ir-chart-panel"><h2 style="--title-color:' + color + '">' + title + '</h2><div class="qc-ir-company-bars">' + bars + '</div></section>';
  }

  function groupedDefects(companies, codes) {
    const defects = codes.map((code) => {
      for (const c of companies) { const d = c.defectMap.find((item) => item.code === code); if (d) return d; }
      return null;
    }).filter(Boolean);
    const legend = defects.map((d, i) => '<span><i style="--legend-color:' + defectColors[i % 3] + '"></i>' + esc(d.name) + '</span>').join('');
    const groups = companies.map((c) => '<div class="qc-ir-company-group"><div class="qc-ir-group-bars">' +
      defects.map((d, i) => {
        const found = c.defectMap.find((item) => item.code === d.code);
        const value = found ? ratio(found.quantity, c.defects) : 0;
        return '<div class="qc-ir-group-bar" title="' + esc(d.name + ': ' + pct.format(value)) + '"><strong>' + pct.format(value) +
          '</strong><i style="--bar-height:' + Math.max(1, value * 100) + '%;--bar-color:' + defectColors[i % 3] + '"></i></div>';
      }).join('') + '</div><span>' + esc(c.name) + '</span></div>').join('');
    return '<section class="qc-ir-chart-panel"><h2>TOP 3 LỖI PHỔ BIẾN</h2><div class="qc-ir-legend">' + legend +
      '</div><div class="qc-ir-grouped-chart">' + groups + '</div></section>';
  }

  function productPage(s, target) {
    if (!s.companies.length && !s.products.length) return empty(target);
    target.innerHTML = '<div class="qc-ir-product-page"><div class="qc-ir-product-kpis">' +
      barPanel(s.companies, 'inspected', 'TỔNG HÀNG KIỂM', '#168dee', (c) => c.share) +
      barPanel(s.companies, 'defects', 'TỔNG HÀNG LỖI', '#d94655', (c) => c.defectRate) +
      '<section class="qc-ir-chart-panel"><h2>TỶ LỆ LỖI</h2>' + donut(s) + '</section></div>' +
      '<div class="qc-ir-product-analysis"><section class="qc-ir-average-card"><strong>' + num.format(s.average) +
      '</strong><span>Trung bình kiểm/chuyền/ngày</span></section>' + productRates(s.products) + '</div></div>';
  }

  function donut(s) {
    return '<div class="qc-ir-donut-layout"><div class="qc-ir-donut-label"><strong>' + num.format(s.totalDefects) + '</strong><span>(' + pct.format(s.defectRate) + ')</span></div>' +
      '<div class="qc-ir-donut-chart" style="--defect-angle:' + (s.defectRate * 360) + 'deg"><i></i></div>' +
      '<div class="qc-ir-donut-label"><strong>' + num.format(s.totalPassed) + '</strong><span>(' + pct.format(s.passRate) + ')</span></div></div>';
  }

  function productRates(products) {
    if (!products.length) return '<section class="qc-ir-chart-panel"><h2>TỶ LỆ LỖI THEO MÃ HÀNG</h2>' + emptyHtml() + '</section>';
    const max = Math.max(0.01, ...products.map((p) => p.rate));
    const bars = products.map((p) => '<div class="qc-ir-product-bar" title="' + esc(p.name + ': ' + pct.format(p.rate)) + '">' +
      '<strong>' + pct.format(p.rate) + '</strong><i style="--bar-height:' + Math.max(3, p.rate / max * 100) + '%"></i><span>' + esc(p.code || p.name) + '</span></div>').join('');
    return '<section class="qc-ir-chart-panel qc-ir-product-rate-panel"><h2>TỶ LỆ LỖI THEO MÃ HÀNG</h2>' +
      '<div class="qc-ir-product-rate-scroll"><div class="qc-ir-product-bars">' + bars + '</div></div></section>';
  }

  function defectPage(s, target) {
    target.innerHTML = '<div class="qc-ir-defect-page"><section class="qc-ir-defect-total"><strong>' + num.format(s.totalDefects) +
      '</strong><span>Tổng lỗi</span></section>' + defectTop(s.topDefects) + defectChart(s.defects) + '</div>';
  }

  function defectTop(items) {
    if (!items.length) return '<section class="qc-ir-chart-panel"><h2>TOP 3 LỖI PHỔ BIẾN</h2>' + emptyHtml() + '</section>';
    const max = Math.max(1, ...items.map((d) => d.quantity));
    const bars = items.map((d) => '<div class="qc-ir-top-defect-column"><strong>' + num.format(d.quantity) + '</strong>' +
      '<div class="qc-ir-top-defect-track"><i style="--bar-height:' + d.quantity / max * 100 + '%"><b>' + pct.format(d.share) + '</b></i></div>' +
      '<span>' + esc(d.name) + '</span></div>').join('');
    return '<section class="qc-ir-chart-panel qc-ir-defect-top-panel"><h2>TOP 3 LỖI PHỔ BIẾN</h2><div class="qc-ir-top-defect-chart">' + bars + '</div></section>';
  }

  function defectChart(items) {
    if (!items.length) return '<section class="qc-ir-chart-panel"><h2>BIỂU ĐỒ LỖI</h2>' + emptyHtml() + '</section>';
    const max = Math.max(1, ...items.map((d) => d.quantity));
    const bars = items.map((d) => '<div class="qc-ir-all-defect-column" title="' + esc(d.name + ': ' + num.format(d.quantity)) + '">' +
      '<strong>' + pct.format(d.share) + '</strong><b>' + num.format(d.quantity) + '</b><i style="--bar-height:' + Math.max(3, d.quantity / max * 100) + '%"></i><span>' + esc(d.name) + '</span></div>').join('');
    return '<section class="qc-ir-chart-panel qc-ir-all-defects-panel"><h2>BIỂU ĐỒ LỖI</h2><div class="qc-ir-all-defects-scroll"><div class="qc-ir-all-defect-chart">' + bars + '</div></div></section>';
  }

  function dots(share) {
    const count = Math.max(0, Math.min(100, Math.round(share * 100)));
    return '<span class="qc-ir-dots">' + Array.from({length: count}, () => '<i></i>').join('') + '</span>';
  }

  function gauge(rate) {
    const r = Math.max(0, Math.min(1, rate || 0)), c = 125.66;
    return '<svg class="qc-ir-gauge" viewBox="0 0 100 62" aria-label="' + pct.format(rate) + '">' +
      '<path d="M10 54 A40 40 0 0 1 90 54" fill="none" stroke="#e1e5eb" stroke-width="9"></path>' +
      '<path d="M10 54 A40 40 0 0 1 90 54" fill="none" stroke="#e6232a" stroke-width="9" stroke-dasharray="' + (c * r) + ' ' + c + '"></path>' +
      '<text x="50" y="48" text-anchor="middle">' + pct.format(rate) + '</text></svg>';
  }

  function top3(company) {
    return company.topDefects.map((d) => '<div class="qc-ir-top-defect"><span>' + esc(d.name) + '</span><strong>' + num.format(d.quantity) + ' (' + pct.format(d.share) + ')</strong></div>').join('');
  }

  function trend(company) {
    const points = company.trend, w = 600, h = 110, left = 18, right = w - 18, top = 22, bottom = h - 22;
    if (!points.length) return '<span class="qc-ir-muted">—</span>';
    const max = Math.max(0.01, ...points.map((p) => p.rate));
    const xy = points.map((p, i) => ({...p, x: points.length === 1 ? w / 2 : left + i / (points.length - 1) * (right - left), y: bottom - p.rate / max * (bottom - top)}));
    const path = xy.map((p, i) => (i ? 'L' : 'M') + p.x + ',' + p.y).join(' ');
    const area = path + ' L' + xy[xy.length - 1].x + ',' + bottom + ' L' + xy[0].x + ',' + bottom + ' Z';
    const id = 'qc-gradient-' + String(company.code || company.name).replace(/[^a-z0-9_-]/gi, '-');
    const labels = xy.map((p, i) => {
      const x = p.x / w * 100 + '%', y = p.y / h * 100 + '%';
      const marker = i === 0
        ? '<span class="qc-ir-trend-point" style="left:' + x + ';top:' + y + '"></span>'
        : '<span class="qc-ir-trend-marker is-' + (p.direction === 'up' ? 'up' : 'down') + '" style="left:' + x + ';top:' + y + '"></span>';
      return '<span class="qc-ir-trend-value" style="left:' + x + ';top:' + y + '">' + pct.format(p.rate) + '</span>' + marker +
        '<span class="qc-ir-trend-date" style="left:' + x + '">' + esc(dateLabel(p.date)) + '</span>';
    }).join('');
    const accessibleLabel = esc(xy.map((p) => dateLabel(p.date) + ': ' + pct.format(p.rate)).join(', '));
    return '<div class="qc-ir-trend" role="img" aria-label="Tỷ lệ lỗi theo ngày: ' + accessibleLabel + '">' +
      '<svg class="qc-ir-trend-svg" viewBox="0 0 ' + w + ' ' + h + '" preserveAspectRatio="none" aria-hidden="true"><defs><linearGradient id="' + id + '" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="#ed4a53" stop-opacity=".42"></stop><stop offset="1" stop-color="#ed4a53" stop-opacity="0"></stop></linearGradient></defs>' +
      '<path d="' + area + '" fill="url(#' + id + ')"></path><path d="' + path + '" fill="none" stroke="#ff626b" stroke-width="2.5" vector-effect="non-scaling-stroke"></path></svg>' +
      '<div class="qc-ir-trend-label-layer" aria-hidden="true">' + labels + '</div></div>';
  }

  function triangle(x, y, direction, color) {
    const points = direction === 'up' ? x + ',' + (y - 5) + ' ' + (x + 4) + ',' + (y + 3) + ' ' + (x - 4) + ',' + (y + 3) :
      (x - 4) + ',' + (y - 3) + ' ' + (x + 4) + ',' + (y - 3) + ' ' + x + ',' + (y + 5);
    return '<polygon points="' + points + '" fill="' + color + '"></polygon>';
  }

  function companyTrend(companies) {
    const dates = Array.from(new Set(companies.flatMap((c) => c.trend.map((p) => p.date)))).sort();
    if (!dates.length) return emptyHtml();
    const w = 920, h = 270, left = 38, right = w - 20, top = 38, bottom = h - 38;
    const rates = companies.flatMap((c) => c.trend.map((p) => p.rate));
    const min = Math.max(0, Math.min(...rates) - .06), max = Math.min(1, Math.max(...rates) + .06), span = Math.max(.08, max - min);
    const xAt = (i) => dates.length === 1 ? (left + right) / 2 : left + i / (dates.length - 1) * (right - left);
    let lines = '';
    companies.forEach((c, ci) => {
      const byDate = new Map(c.trend.map((p) => [p.date, p]));
      const pts = dates.map((date, i) => { const p = byDate.get(date); return p ? {...p, x: xAt(i), y: bottom - (p.rate - min) / span * (bottom - top)} : null; }).filter(Boolean);
      if (!pts.length) return;
      const color = companyColor(ci);
      const path = pts.map((p, i) => (i ? 'L' : 'M') + p.x + ',' + p.y).join(' ');
      lines += '<path d="' + path + '" fill="none" stroke="' + color + '" stroke-width="3"></path>' +
        pts.map((p) => '<polygon points="' + p.x + ',' + (p.y - 5) + ' ' + (p.x + 5) + ',' + p.y + ' ' + p.x + ',' + (p.y + 5) + ' ' + (p.x - 5) + ',' + p.y + '" fill="' + color + '"></polygon><text x="' + p.x + '" y="' + (p.y - 10 - ci % 2 * 12) + '" text-anchor="middle">' + pct.format(p.rate) + '</text>').join('');
    });
    const axis = dates.map((date, i) => '<text class="qc-ir-multi-date" x="' + xAt(i) + '" y="' + (h - 8) + '" text-anchor="middle">' + dateLabel(date) + '</text>').join('');
    const legend = companies.map((c, i) => '<span><i style="--legend-color:' + companyColor(i) + '"></i>' + esc(c.name) + '</span>').join('');
    return '<div class="qc-ir-multi-wrap"><div class="qc-ir-legend">' + legend + '</div><svg class="qc-ir-multi-trend" viewBox="0 0 ' + w + ' ' + h + '" preserveAspectRatio="none"><path d="M' + left + ',' + bottom + ' H' + right + '" stroke="#d9e0e7"></path>' + lines + axis + '</svg></div>';
  }

  function empty(target) { target.innerHTML = emptyHtml(); }
  function emptyHtml() { return '<div class="qc-ir-empty"><strong>' + __('Không có dữ liệu trong khoảng thời gian đã chọn') + '</strong></div>'; }
  function mean(map) { return map.size ? Array.from(map.values()).reduce((a, b) => a + b, 0) / map.size : 0; }
  function ratio(a, b) { return b ? a / b : 0; }
  function byQuantity(a, b) { return b.quantity - a.quantity || a.code.localeCompare(b.code); }
  function dateLabel(value) { const m = String(value || '').match(/^(\d{4})-(\d{2})-(\d{2})/); return m ? m[3] + '/' + m[2] : value; }
  function esc(value) { return String(value ?? '').replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }

  return {version, summarize, render};
})();
