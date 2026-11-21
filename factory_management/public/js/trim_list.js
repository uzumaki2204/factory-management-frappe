frappe.listview_settings['Trim'] = {
  onload(listview) {
    if (frappe.user.has_role('System Manager') || frappe.user.has_role('Trim Manager')) {
      listview.page.add_inner_button(__('Import Trim'), () => frappe.set_route('trim-import'));
    }
  },
};
