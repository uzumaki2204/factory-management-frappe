(function () {
    'use strict';
    const languages = window.UQQCCatalog || {};
    const language = (document.documentElement.lang || 'vi').split('-')[0];
    const catalog = Object.freeze(languages[language] || languages.vi || {});
    function t(key) { return catalog[key] || languages.en?.[key] || key; }
    function apply(root) {
        const target = root || document;
        for (const [suffix, attribute] of [['', null], ['-aria', 'aria-label'], ['-title', 'title'], ['-placeholder', 'placeholder'], ['-alt', 'alt']]) {
            const name = 'data-i18n' + suffix;
            target.querySelectorAll('[' + name + ']').forEach(element => {
                const value = t(element.getAttribute(name));
                if (attribute) element.setAttribute(attribute, value); else element.textContent = value;
            });
        }
    }
    window.UQQCI18n = Object.freeze({ t, apply });
    window.UQQCI18nReady = Promise.resolve();
}());
