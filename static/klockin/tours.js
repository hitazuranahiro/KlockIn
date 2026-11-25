/* KlockIN guided tours, built from the existing company-scoped tour API. */
(() => {
  const config = window.KLOCKIN_TOURS;
  const driver = window.driver?.js?.driver;
  if (!config || !driver) return;

  const launcher = () => document.getElementById('tourLauncherBtn');
  const translate = (text) => typeof gettext === 'function' ? gettext(text) : text;
  let panel;
  let controller;
  let tours = [];
  let requestNumber = 0;
  let progressWrites = Promise.resolve();

  function textElement(tag, text, className = '') {
    const element = document.createElement(tag);
    element.textContent = text;
    element.className = className;
    return element;
  }

  function escapeText(text) {
    return textElement('span', text || '').innerHTML;
  }

  function focusLauncher() {
    const button = launcher();
    const target = button?.getClientRects().length ? button : document.querySelector('[data-workspace-tools]');
    target?.focus({ preventScroll: true });
  }

  function closePanel(restoreFocus = false) {
    if (!panel || panel.hidden) return;
    panel.hidden = true;
    launcher()?.setAttribute('aria-expanded', 'false');
    if (restoreFocus) focusLauncher();
  }

  function record(tourId, status, lastStep) {
    const body = new FormData();
    const token = document.querySelector('[name=csrfmiddlewaretoken]')?.value
      || document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/)?.[1] || '';
    body.set('csrfmiddlewaretoken', token);
    body.set('tour_id', tourId);
    body.set('status', status);
    if (Number.isInteger(lastStep)) body.set('last_step', lastStep);
    progressWrites = progressWrites.then(() => fetch(config.progressUrl, { method: 'POST', body })).catch(() => {});
  }

  function start(tour) {
    if (!tour?.steps?.length) return;
    controller?.destroy();
    closePanel();
    const steps = tour.steps.map((step) => ({
      element: step.element || undefined,
      popover: {
        title: escapeText(step.title),
        description: escapeText(step.description),
        side: step.side || 'bottom',
        align: step.align || 'start',
      },
    }));
    controller = driver({
      animate: !window.matchMedia('(prefers-reduced-motion: reduce)').matches,
      allowClose: tour.allow_close !== false,
      showProgress: tour.show_progress !== false,
      popoverClass: 'ki-tour-popover',
      nextBtnText: translate('Next'),
      prevBtnText: translate('Back'),
      doneBtnText: translate('Finish'),
      steps,
      onDestroyStarted(_element, _step, { state }) {
        const completed = state.activeIndex >= steps.length - 1;
        record(tour.id, completed ? 'completed' : 'skipped', state.activeIndex);
        if (completed) launcher()?.querySelector('.workspace-tour-dot')?.remove();
        const ending = controller;
        controller = null;
        ending?.destroy();
        focusLauncher();
      },
    });
    record(tour.id, 'in_progress', 0);
    controller.drive(0);
  }

  async function loadTours() {
    const path = window.location.pathname;
    const params = new URLSearchParams({ path });
    const response = await fetch(`${config.activeUrl}?${params}`, {
      headers: { 'X-Requested-With': 'XMLHttpRequest' },
    });
    if (!response.ok) throw new Error('Tour list unavailable');
    const data = await response.json();
    return window.location.pathname === path ? (data.tours || []) : [];
  }

  function buildPanel() {
    if (panel) return panel;
    panel = document.createElement('section');
    panel.id = 'klockinTourPanel';
    panel.className = 'ki-tour-panel';
    panel.hidden = true;
    panel.setAttribute('role', 'dialog');
    panel.setAttribute('aria-labelledby', 'klockinTourHeading');
    document.body.appendChild(panel);
    return panel;
  }

  function renderPanel(message = '') {
    if (panel.hidden) return;
    const heading = textElement('h2', translate('Guided tours'));
    heading.id = 'klockinTourHeading';
    const header = document.createElement('header');
    const close = textElement('button', '×', 'ki-tour-close');
    close.type = 'button';
    close.setAttribute('aria-label', translate('Close guided tours'));
    close.addEventListener('click', () => closePanel(true));
    header.append(heading, close);
    panel.replaceChildren(header);
    if (message || !tours.length) {
      const status = textElement('p', message || translate('There are no guided tours for this page.'));
      status.setAttribute('role', 'status');
      panel.append(status);
    } else {
      const list = document.createElement('ul');
      for (const tour of tours) {
        const item = document.createElement('li');
        const button = document.createElement('button');
        button.type = 'button';
        button.append(textElement('strong', tour.title));
        if (tour.description) button.append(textElement('span', tour.description));
        button.addEventListener('click', () => start(tour));
        item.append(button);
        list.append(item);
      }
      panel.append(list);
    }
    close.focus({ preventScroll: true });
  }

  async function toggle() {
    const button = launcher();
    if (!button) return;
    const container = buildPanel();
    if (!container.hidden) return closePanel(true);

    const bounds = button.getBoundingClientRect();
    container.style.setProperty('--ki-tour-top', `${Math.round(bounds.bottom + 8)}px`);
    container.style.setProperty('--ki-tour-right', `${Math.max(8, Math.round(window.innerWidth - bounds.right))}px`);
    container.hidden = false;
    button.setAttribute('aria-expanded', 'true');
    const request = ++requestNumber;
    renderPanel(translate('Loading guided tours…'));
    try {
      const response = await loadTours();
      if (request !== requestNumber) return;
      tours = response;
      renderPanel();
    } catch {
      if (request === requestNumber) renderPanel(translate('Guided tours could not load. Reopen the menu to try again.'));
    }
  }

  document.addEventListener('click', (event) => {
    if (launcher()?.contains(event.target)) {
      toggle();
    } else if (panel && !panel.contains(event.target)) {
      closePanel();
    }
  });
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') closePanel(true);
  });
  document.addEventListener('htmx:beforeSwap', (event) => {
    if (['ohMainContent', 'header'].includes(event.detail?.target?.id)) closePanel();
  });

  document.addEventListener('DOMContentLoaded', () => {
    if (!launcher()) return;
    loadTours().then((response) => {
      tours = response;
      const next = tours.find((tour) => tour.auto_start);
      if (next && !controller && (!panel || panel.hidden)) start(next);
    }).catch(() => {});
  });
})();
