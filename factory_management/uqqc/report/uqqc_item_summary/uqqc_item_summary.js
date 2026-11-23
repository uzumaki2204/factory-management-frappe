frappe.query_reports['UQQC Item Summary'] = {
  onload(report) {
    if (report.uqqcFiltersInitialized) return;
    report.uqqcFiltersInitialized = true;
    const getFilterValues = report.get_filter_values.bind(report);
    report.get_filter_values = (raise) => {
      const defaults = report.report_name === 'UQQC Device Details'
        ? {qc: '', company: '', product: '', device: '', market: '', color: '', size: ''}
        : report.report_name === 'UQQC Item Summary'
          ? {qc: '', company: '', product: ''}
          : {};
      return {...defaults, ...getFilterValues(raise)};
    };
  },
  filters: [
    {
      fieldname: 'from_date',
      label: __('From Date'),
      fieldtype: 'Date',
      reqd: 1,
      default: `${frappe.datetime.get_today().slice(0, 8)}01`,
    },
    {
      fieldname: 'to_date',
      label: __('To Date'),
      fieldtype: 'Date',
      reqd: 1,
      default: frappe.datetime.get_today(),
    },
    {fieldname: 'qc', label: __('QC'), fieldtype: 'Select', options: '\nQC1\nQC2'},
    {fieldname: 'company', label: __('Company'), fieldtype: 'Link', options: 'Company'},
    {fieldname: 'product', label: __('Product'), fieldtype: 'Link', options: 'Product'},
  ],
};
