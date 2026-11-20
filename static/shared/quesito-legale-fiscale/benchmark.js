// Public benchmark methodology and results for this workflow.
(() => {
  const page = window.MPARANZA_FUNCTION_PAGES["quesito-legale-fiscale"];
  page.publicExampleHref = "/static/shared/vera/benchmark/metodologia.html";
  const linkLabels = {
    it: "Metodo e risultati dei benchmark →",
    en: "Benchmark method and results (Italian) →",
    fr: "Méthode et résultats des benchmarks (en italien) →",
    de: "Benchmark-Methode und Ergebnisse (auf Italienisch) →",
    es: "Método y resultados de los benchmarks (en italiano) →"
  };
  for (const [language, linkLabel] of Object.entries(linkLabels)) {
    Object.assign(page.copy[language], {
      publicExampleTitle: "Benchmark fiscale Vera",
      publicExampleLinkLabel: linkLabel
    });
  }
})();
