(() => {
    const actions = document.querySelector('[data-quick-actions]');
    if (!actions) return;

    const toggle = actions.querySelector('.quick-actions-toggle');
    const panel = actions.querySelector('.quick-actions-panel');
    let activeModal = null;
    let modalObserver = null;

    function setExpanded(open, restoreFocus = false) {
        toggle.setAttribute('aria-expanded', String(open));
        panel.hidden = !open;
        if (open) panel.querySelector('button')?.focus();
        if (restoreFocus) toggle.focus({preventScroll: true});
    }

    function focusDialogContent(target) {
        const focusable = Array.from(target.querySelectorAll(
            '.oh-modal__close, .oh-modal__close--custom, input:not([type="hidden"]), select, textarea, button'
        )).find(element => !element.disabled && element.getClientRects().length);
        if (focusable) {
            focusable.focus({preventScroll: true});
            return;
        }
        target.tabIndex = -1;
        target.focus({preventScroll: true});
    }

    function watchModal(trigger) {
        const modal = document.querySelector(trigger.dataset.target);
        if (!modal) {
            toggle.focus({preventScroll: true});
            return;
        }

        modalObserver?.disconnect();
        activeModal = modal;
        const originalHidden = modal.getAttribute('aria-hidden');
        modal.classList.add('oh-modal--show');
        modal.setAttribute('aria-hidden', 'false');

        const dialog = document.querySelector(trigger.getAttribute('hx-target'));
        if (dialog) {
            dialog.tabIndex = -1;
            dialog.focus({preventScroll: true});
        }

        modalObserver = new MutationObserver(() => {
            if (modal.classList.contains('oh-modal--show')) return;
            modalObserver.disconnect();
            modalObserver = null;
            activeModal = null;
            if (originalHidden === null) modal.removeAttribute('aria-hidden');
            else modal.setAttribute('aria-hidden', originalHidden);
            if (document.activeElement === document.body || modal.contains(document.activeElement)) {
                toggle.focus({preventScroll: true});
            }
        });
        modalObserver.observe(modal, {attributes: true, attributeFilter: ['class']});
    }

    toggle.addEventListener('click', () => setExpanded(panel.hidden));
    panel.addEventListener('click', event => {
        const trigger = event.target.closest('[data-quick-action]');
        if (!trigger) return;
        setExpanded(false);
        watchModal(trigger);
    });
    document.addEventListener('htmx:afterSwap', event => {
        if (activeModal?.contains(event.detail.target)) focusDialogContent(event.detail.target);
    });
    actions.addEventListener('focusout', event => {
        if (!panel.hidden && event.relatedTarget && !actions.contains(event.relatedTarget)) setExpanded(false);
    });
    document.addEventListener('click', event => {
        if (!panel.hidden && !actions.contains(event.target)) setExpanded(false);
    });
    document.addEventListener('keydown', event => {
        if (event.key !== 'Escape') return;
        if (!panel.hidden) {
            event.preventDefault();
            setExpanded(false, true);
        } else if (activeModal?.contains(document.activeElement)) {
            event.preventDefault();
            activeModal.classList.remove('oh-modal--show');
        }
    });
})();
