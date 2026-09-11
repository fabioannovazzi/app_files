/* Only reveal precompiled evidence-bound views. No financial arithmetic or IO. */
(() => {
  document.querySelectorAll('[data-comparison-group]').forEach(group => {
    const period = group.querySelector('[data-report-period]');
    const scenario = group.querySelector('[data-report-scenario]');
    const panels = [...group.querySelectorAll('[data-comparison-panel]')];
    const announce = group.querySelector('.comparison-selection');
    const choose = () => {
      const allowed = [...new Set(panels.filter(p => p.dataset.period === period.value)
        .map(p => p.dataset.scenario))];
      const previous = scenario.value;
      scenario.replaceChildren(...allowed.map(value => new Option(value, value)));
      scenario.value = allowed.includes(previous) ? previous : allowed[0];
      panels.forEach(panel => {
        panel.hidden = panel.dataset.period !== period.value || panel.dataset.scenario !== scenario.value;
      });
      announce.textContent = `${period.value} · ${scenario.value}`;
    };
    period.disabled = false;
    scenario.disabled = false;
    period.addEventListener('change', choose);
    scenario.addEventListener('change', choose);
    choose();
  });
  document.querySelectorAll('[data-report-print]').forEach(button => {
    button.hidden = false;
    button.addEventListener('click', () => window.print());
  });
})();
