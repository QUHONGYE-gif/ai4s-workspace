/* Interface motion only: page entrance, count tickers and card spotlight.
   Patterns follow Magic UI (BlurFade, NumberTicker) and Aceternity (card spotlight),
   rebuilt without a framework. Nothing here changes data or application state. */
window.Motion = (() => {
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
  const ENTER_MS = 700;
  const TICK_MS = 600;
  let lastPageKey = '';
  let enterTimer = 0;

  // Sections of a newly opened page fade up one after another (BlurFade).
  // Re-renders on the same page, such as changing a field, do not replay it.
  const playPageEnter = function playPageEnter(main, pageKey) {
    if (pageKey === lastPageKey) return;
    lastPageKey = pageKey;
    if (reducedMotion.matches) return;
    clearTimeout(enterTimer);
    main.classList.remove('page-enter');
    void main.offsetWidth; // restart the animation for the new page
    main.classList.add('page-enter');
    enterTimer = setTimeout(() => main.classList.remove('page-enter'), ENTER_MS + 400);
  };

  // Counts roll from their previous value to the new one (NumberTicker).
  const tickCount = function tickCount(element) {
    const text = element.textContent.trim();
    const target = Number(text);
    const previous = Number(element.dataset.shownValue);
    element.dataset.shownValue = text;
    if (!Number.isFinite(target) || !Number.isFinite(previous) || previous === target) return;
    if (reducedMotion.matches) return;
    const padding = text.length;
    const startedAt = performance.now();
    const step = function step(now) {
      const progress = Math.min(1, (now - startedAt) / TICK_MS);
      const eased = 1 - Math.pow(1 - progress, 3);
      const value = Math.round(previous + (target - previous) * eased);
      element.textContent = String(value).padStart(padding, '0');
      if (progress < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  };

  const afterRender = function afterRender(main, pageKey) {
    playPageEnter(main, pageKey);
    document.querySelectorAll('.nav-count').forEach(tickCount);
  };

  // Cards light up softly under the pointer (Aceternity card spotlight).
  // Position updates are batched into one animation frame.
  const SPOTLIGHT = '.entry-card, .tool-card, .storage-card, .panel-spotlight';
  let pendingPointer = null;
  document.addEventListener('pointermove', (event) => {
    if (event.pointerType !== 'mouse') return;
    const card = event.target.closest?.(SPOTLIGHT);
    if (!card) return;
    if (!pendingPointer) {
      requestAnimationFrame(() => {
        const { card: target, x, y } = pendingPointer;
        const box = target.getBoundingClientRect();
        target.style.setProperty('--spot-x', `${x - box.left}px`);
        target.style.setProperty('--spot-y', `${y - box.top}px`);
        pendingPointer = null;
      });
    }
    pendingPointer = { card, x: event.clientX, y: event.clientY };
  });

  return { afterRender };
})();
