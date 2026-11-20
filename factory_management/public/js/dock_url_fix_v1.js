(function () {
    const marker = "__factory_management_dock_url_fix__";

    function install() {
        const sidebar = window.frappe && window.frappe.app && window.frappe.app.sidebar;
        if (!sidebar || typeof sidebar.open_dock_entry !== "function") return false;

        const current = sidebar.open_dock_entry;
        if (current[marker]) return true;

        function openDockEntry(entry) {
            if (entry && entry.link_type === "URL" && typeof entry.url === "string" && entry.url.trim()) {
                const destination = new URL(entry.url, window.location.origin);
                if (destination.protocol === "http:" || destination.protocol === "https:") {
                    window.open(destination.href, "_blank", "noopener,noreferrer");
                    return;
                }
            }
            return current.apply(this, arguments);
        }

        openDockEntry[marker] = true;
        sidebar.open_dock_entry = openDockEntry;
        return true;
    }

    if (install()) return;

    let attempts = 0;
    const timer = window.setInterval(function () {
        if (install() || ++attempts >= 120) window.clearInterval(timer);
    }, 250);
})();
