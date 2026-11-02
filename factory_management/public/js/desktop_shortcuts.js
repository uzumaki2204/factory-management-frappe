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
        {
            id: "spl-po-import",
            label: "Import SPL",
            logo: "/assets/factory_management/images/spl-import-desktop.svg",
            href: "/desk/factory-management/spl-po-import",
            systemManagerOnly: true,
        },
    ];

    let currentGrid = null;

    function addShortcuts() {
        const grid = document.querySelector(".desktop-container .icons-container .icons");
        if (!grid || !window.frappe || typeof frappe.render_template !== "function") return;
        grid.classList.add("factory-management-shortcuts");

        const isSystemManager = frappe.session?.user === "Administrator" ||
            frappe.user?.has_role?.("System Manager") === true;
        const visibleShortcuts = shortcuts.filter(
            (shortcut) => !shortcut.systemManagerOnly || isSystemManager
        );

        if (grid === currentGrid && visibleShortcuts.every(
            (shortcut) => grid.querySelector(`[data-factory-shortcut="${shortcut.id}"]`)
        )) return;
        currentGrid = grid;

        for (const shortcut of visibleShortcuts) {
            if (grid.querySelector(`[data-factory-shortcut="${shortcut.id}"]`)) continue;

            const markup = frappe.render_template("desktop_icon", {
                icon: { label: __(shortcut.label), logo_url: shortcut.logo },
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

    function watchDesk() {
        const root = document.body || document.documentElement;
        if (!root) return;

        addShortcuts();
        const observer = new MutationObserver(addShortcuts);
        observer.observe(root, { childList: true, subtree: true });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", watchDesk, { once: true });
    } else {
        watchDesk();
    }
})();
