// Public benchmark methodology and results for this workflow.
(() => {
  const page = window.MPARANZA_FUNCTION_PAGES["quesito-legale-fiscale"];
  page.publicExampleHref = "/static/shared/vera/benchmark/metodologia.html";
  const copy = {
    it: ["Come valutiamo le risposte di Vera", "Il metodo, i risultati delle tre prove e i limiti dei punteggi.", "Metodo e risultati dei benchmark →"],
    en: ["How we evaluate Vera’s answers", "The method, results from three evaluations and limits of the scores. Page in Italian.", "Benchmark method and results →"],
    fr: ["Comment nous évaluons les réponses de Vera", "La méthode, les résultats de trois évaluations et les limites des scores. Page en italien.", "Méthode et résultats des benchmarks →"],
    de: ["Wie wir Veras Antworten bewerten", "Die Methode, die Ergebnisse von drei Auswertungen und die Grenzen der Kennzahlen. Seite auf Italienisch.", "Benchmark-Methode und Ergebnisse →"],
    es: ["Cómo evaluamos las respuestas de Vera", "El método, los resultados de tres evaluaciones y los límites de las puntuaciones. Página en italiano.", "Método y resultados de los benchmarks →"]
  };
  for (const [language, [title, summary, linkLabel]] of Object.entries(copy)) {
    Object.assign(page.copy[language], {
      publicExampleLabel: "Benchmark",
      publicExampleTitle: title,
      publicExampleSummary: summary,
      publicExampleLinkLabel: linkLabel
    });
  }
})();
