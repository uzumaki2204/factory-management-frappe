frappe.pages['qc-api-docs'].on_page_load = function (wrapper) {
  const page = frappe.ui.make_app_page({
    parent: wrapper,
    title: __('API Documentation'),
    single_column: true,
  });
  const frame = document.createElement('iframe');
  frame.title = __('API Documentation');
  frame.src = '/qc-api-docs?embedded=1';
  frame.style.cssText = 'display:block;width:100%;height:calc(100vh - 140px);min-height:620px;border:0;background:#f3f7fc;';
  page.body.append(frame);
};
