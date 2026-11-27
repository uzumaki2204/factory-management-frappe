frappe.query_reports['QC Internal Dataset'] = {
  filters: [
    {fieldname: 'from_date', label: __('From Date'), fieldtype: 'Date', reqd: 1},
    {fieldname: 'to_date', label: __('To Date'), fieldtype: 'Date', reqd: 1},
    {fieldname: 'qc', label: __('QC'), fieldtype: 'Select', options: '\nQC1\nQC2'},
    {fieldname: 'company', label: __('Company'), fieldtype: 'Link', options: 'Company'},
    {fieldname: 'factory', label: __('Factory'), fieldtype: 'Link', options: 'Factory'},
    {fieldname: 'line_group', label: __('Line Group'), fieldtype: 'Link', options: 'Line Group'},
    {fieldname: 'production_line', label: __('Production Line'), fieldtype: 'Link', options: 'Production Line'},
    {fieldname: 'customer', label: __('Customer'), fieldtype: 'Link', options: 'Customer'},
    {fieldname: 'product', label: __('Product'), fieldtype: 'Link', options: 'Product'},
  ],
};
