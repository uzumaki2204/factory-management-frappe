(function () {
    const shortcuts = [
        {
            id: "uqqc",
            label: "UQQC",
            logo: "/assets/factory_management/uqqc/icon.svg",
            href: "/uqqc",
            newTab: true,
        },
        {
            id: "qc",
            label: "QC",
            logo: "/assets/factory_management/images/qc-desktop.svg",
            href: "/qc",
            newTab: true,
        },
        {
            id: "api-management",
            label: "API Docs",
            logo: "/assets/factory_management/images/api-management-desktop.svg",
            href: "/desk/api-management/qc-api-docs",
            systemManagerOnly: true,
        },
    ];

    function addShortcuts() {
        const grid = document.querySelector(".desktop-container .icons-container .icons");
        if (!grid || !window.frappe || typeof frappe.render_template !== "function") return;
        grid.classList.add("factory-management-shortcuts");

        const canManageApi = frappe.session?.user === "Administrator" ||
            frappe.user?.has_role?.("System Manager") === true;

        for (const shortcut of shortcuts) {
            if (shortcut.systemManagerOnly && !canManageApi) continue;
            if (grid.querySelector(`[data-factory-shortcut="${shortcut.id}"]`)) continue;

            const markup = frappe.render_template("desktop_icon", {
                icon: { label: shortcut.label, logo_url: shortcut.logo },
            });
            const tile = document.createElement("div");
            tile.innerHTML = markup.trim();
            const icon = tile.firstElementChild;
            if (!icon) continue;

            icon.dataset.factoryShortcut = shortcut.id;
            for (const link of icon.querySelectorAll(".icon-link, .icon-title")) {
                link.setAttribute("href", shortcut.href);
                if (shortcut.newTab) {
                    link.setAttribute("target", "_blank");
                    link.setAttribute("rel", "noopener noreferrer");
                }
            }
            grid.appendChild(icon);
        }
    }

    if (window.jQuery) {
        window.jQuery(document).on("desktop_screen.factory_management_shortcuts", addShortcuts);
    }
    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", addShortcuts, { once: true });
    } else {
        addShortcuts();
    }
})();
