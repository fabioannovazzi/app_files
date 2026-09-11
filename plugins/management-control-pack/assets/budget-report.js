(() => {
  'use strict';
  document.querySelectorAll('.budget-report').forEach(report => {
    const controls = report.querySelector('.budget-controls');
    const buttons = [...report.querySelectorAll('[data-budget-select]')];
    const views = [...report.querySelectorAll('[data-budget-view]')];
    const select = id => {
      views.forEach(view => { view.hidden = view.dataset.budgetView !== id; });
      buttons.forEach(button => {
        button.setAttribute('aria-pressed', String(button.dataset.budgetSelect === id));
      });
    };
    buttons.forEach(button => button.addEventListener('click', () => select(button.dataset.budgetSelect)));
    report.querySelector('[data-budget-print]').addEventListener('click', () => window.print());
    controls.hidden = false;
    select(buttons[0].dataset.budgetSelect);
  });
})();
