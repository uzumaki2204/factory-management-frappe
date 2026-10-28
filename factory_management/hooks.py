app_name = "factory_management"
app_title = "Factory Management"
app_publisher = "Onichan"
app_description = "Quality Control"
app_email = ""
app_license = "Proprietary"

add_to_apps_screen = [
    {
        "name": app_name,
        "title": app_title,
        "logo": "/assets/factory_management/images/qc-desktop.svg",
        "route": "/qc",
    }
]

after_install = "factory_management.install.after_install"
after_migrate = "factory_management.install.ensure_schema"
update_website_context = [
    "factory_management.qc_web_page.update_website_context",
    "factory_management.uqqc.web_page.update_website_context",
]
has_permission = {"Web Page": "factory_management.web_page_permissions.has_permission"}
permission_query_conditions = {"Web Page": "factory_management.web_page_permissions.query_conditions"}
doc_events = {
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
app_include_css = ["/assets/factory_management/css/desktop_shortcuts.css"]
