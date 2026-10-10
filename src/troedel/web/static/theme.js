// Light or dark, decided before the stylesheet loads so that nothing flashes.
// Follows the device; a choice stored under "troedel.theme" (light | dark) wins.
(function () {
    var root = document.documentElement, query = matchMedia('(prefers-color-scheme: dark)');
    function apply() {
        var choice = null;
        try { choice = localStorage.getItem('troedel.theme'); } catch (_) { /* private mode */ }
        var theme = choice === 'light' || choice === 'dark' ? choice : (query.matches ? 'dark' : 'light');
        root.setAttribute('data-theme', theme);
        root.style.colorScheme = theme;
        // The status bar colour in the page head is tied to the device setting.
        document.querySelectorAll('meta[name="theme-color"]').forEach(function (meta) {
            if (!meta.dataset.media) meta.dataset.media = meta.media;
            meta.media = !choice ? meta.dataset.media : (meta.dataset.media.indexOf(theme) > -1 ? 'all' : 'not all');
        });
    }
    apply();
    if (query.addEventListener) query.addEventListener('change', apply);
    window.troedelTheme = function (choice) {
        try {
            if (choice) localStorage.setItem('troedel.theme', choice); else localStorage.removeItem('troedel.theme');
        } catch (_) { /* private mode */ }
        apply();
    };
})();
