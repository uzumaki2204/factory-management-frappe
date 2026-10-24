# Desk-editable UQQC API. Authentication and validation live in the UQQC package.
frappe.response["message"] = frappe.call("factory_management.uqqc.api.dispatch", operation="snapshot")
