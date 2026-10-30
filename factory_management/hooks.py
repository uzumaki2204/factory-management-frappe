app_name = "factory_management"
app_title = "Factory Management"
app_publisher = "Onichan"
app_description = "Quality Control"
app_email = ""
app_license = "Proprietary"

after_install = "factory_management.install.after_install"
after_migrate = "factory_management.install.ensure_schema"
scheduler_events = {
    "cron": {"* * * * *": ["factory_management.spl_po.schedule.tick"]},
    "daily": ["factory_management.spl_po.service.cleanup_snapshots"],
}
update_website_context = [
    "factory_management.qc_web_page.update_website_context",
    "factory_management.uqqc.web_page.update_website_context",
]
has_permission = {"Web Page": "factory_management.web_page_permissions.has_permission"}
permission_query_conditions = {"Web Page": "factory_management.web_page_permissions.query_conditions"}
doc_events = {
    "SPL Import Settings": {"validate": "factory_management.spl_po.settings.validate"},
    "API Documentation Service": {"validate": "factory_management.api_docs.validate_service"},
    "API Documentation Endpoint": {"validate": "factory_management.api_docs.validate_endpoint"},
    "QC Defect": {"validate": "factory_management.catalog.validate_qc_defect"},
    "QC Defect Position": {"validate": "factory_management.catalog.validate_qc_position"},
    "UQQC Defect": {"validate": "factory_management.catalog.validate_uqqc_defect"},
    "UQQC Defect Position": {"validate": "factory_management.catalog.validate_uqqc_position"},
    "Factory Device": {"before_naming": "factory_management.device_registry.before_naming"},
    "Factory": {"before_naming": "factory_management.factory_naming.before_naming"},
}

app_include_js = [
    "/assets/factory_management/js/dock_url_fix_v1.js",
    "/assets/factory_management/js/desktop_shortcuts.js",
]
app_include_css = [
    "/assets/factory_management/css/desktop_shortcuts.css",
    "/assets/factory_management/css/spl_import_settings.css",
]
doctype_js = {
    "SPL Import Settings": "public/js/spl_import_settings.js",
}
