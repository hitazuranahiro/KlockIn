(() => {
    const sidebar = document.getElementById('sidebar');
    const content = document.querySelector('.workspace-scroll');
    const floating = document.getElementById('floating-buttons');
    const main = document.getElementById('ohMainContent');
    const navToggle = document.querySelector('[data-workspace-nav]');
    const navClose = sidebar.querySelector('[data-workspace-close]');
    const backdrop = document.querySelector('.workspace-nav-backdrop');
    const toolsToggle = document.querySelector('[data-workspace-tools]');
    const tools = document.getElementById('workspace-tools');
    const narrow = window.matchMedia('(max-width: 900px)');
    const compactTools = window.matchMedia('(max-width: 760px)');
    const dropdowns = Array.from(document.querySelectorAll('.workspace-header .workspace-dropdown'));
    let openDropdown = null;

    function setDropdown(dropdown, returnFocus = false) {
        if (openDropdown) {
            openDropdown.classList.remove('is-open');
            const oldToggle = openDropdown.querySelector(':scope > button');
            oldToggle.setAttribute('aria-expanded', 'false');
            if (returnFocus) oldToggle.focus({preventScroll: true});
        }
        openDropdown = dropdown;
        if (dropdown) {
            dropdown.classList.add('is-open');
            dropdown.querySelector(':scope > button').setAttribute('aria-expanded', 'true');
        }
    }

    dropdowns.forEach((dropdown, index) => {
        const toggle = dropdown.querySelector(':scope > button');
        const panel = dropdown.querySelector(':scope > .dropdown-content');
        if (!toggle || !panel) return;
        panel.id ||= `workspace-header-popover-${index}`;
        toggle.setAttribute('aria-controls', panel.id);
        toggle.setAttribute('aria-expanded', 'false');
        toggle.addEventListener('click', () => setDropdown(openDropdown === dropdown ? null : dropdown));
        dropdown.addEventListener('focusout', event => {
            if (openDropdown === dropdown && event.relatedTarget && !dropdown.contains(event.relatedTarget)) setDropdown(null);
        });
    });

    function setNavigation(open) {
        document.body.classList.toggle('workspace-nav-open', open);
        navToggle.setAttribute('aria-expanded', String(open));
        sidebar.inert = narrow.matches && !open;
        content.inert = open;
        floating.inert = open;
        backdrop.hidden = !open;
        if (open) {
            sidebar.setAttribute('role', 'dialog');
            sidebar.setAttribute('aria-modal', 'true');
        } else {
            sidebar.removeAttribute('role');
            sidebar.removeAttribute('aria-modal');
        }
    }

    function closeNavigation(focusTarget = navToggle) {
        setNavigation(false);
        if (focusTarget) focusTarget.focus({preventScroll: true});
    }

    function setTools(open, returnFocus = false) {
        if (!open && openDropdown && tools.contains(openDropdown)) setDropdown(null);
        tools.classList.toggle('is-open', open);
        toolsToggle.setAttribute('aria-expanded', String(open));
        if (returnFocus) toolsToggle.focus({preventScroll: true});
    }

    navToggle.addEventListener('click', () => {
        setDropdown(null);
        setTools(false);
        setNavigation(true);
        navClose.focus({preventScroll: true});
    });
    navClose.addEventListener('click', () => closeNavigation());
    backdrop.addEventListener('click', () => closeNavigation());
    narrow.addEventListener('change', () => {
        const returnFocus = narrow.matches && sidebar.contains(document.activeElement);
        closeNavigation(returnFocus ? navToggle : null);
    });
    sidebar.addEventListener('click', event => {
        if (!narrow.matches || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
        if (event.target.closest('a[href]')) closeNavigation(main);
    }, true);
    setNavigation(false);

    toolsToggle.addEventListener('click', () => {
        setTools(!tools.classList.contains('is-open'));
    });
    compactTools.addEventListener('change', () => setTools(false));
    document.addEventListener('click', event => {
        if (openDropdown && !openDropdown.contains(event.target)) setDropdown(null);
        if (!event.target.closest('.workspace-tools-wrap')) setTools(false);
    });
    document.addEventListener('htmx:beforeRequest', event => {
        const trigger = event.detail.elt;
        if (trigger?.matches('#workspace-tools > a')) setTools(false);
        if (trigger?.matches('.workspace-account-menu a')) setDropdown(null);
    });

    document.addEventListener('keydown', event => {
        if (document.body.classList.contains('workspace-nav-open')) {
            if (event.key === 'Escape') {
                event.preventDefault();
                closeNavigation();
            } else if (event.key === 'Tab') {
                const items = Array.from(sidebar.querySelectorAll('a[href], button:not([disabled])'))
                    .filter(item => item.getClientRects().length > 0);
                const first = items[0];
                const last = items[items.length - 1];
                if (event.shiftKey && document.activeElement === first) {
                    event.preventDefault();
                    last.focus();
                } else if (!event.shiftKey && document.activeElement === last) {
                    event.preventDefault();
                    first.focus();
                }
            }
        } else if (event.key === 'Escape' && openDropdown) {
            event.preventDefault();
            setDropdown(null, true);
        } else if (event.key === 'Escape' && tools.classList.contains('is-open')) {
            event.preventDefault();
            setTools(false, true);
        }
    });
})();
