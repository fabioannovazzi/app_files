// Public benchmark link for this workflow page.
(() => {
  const page = window.MPARANZA_FUNCTION_PAGES["quesito-legale-fiscale"];
  page.publicExampleHref = "/static/shared/vera/benchmark/index.html";
  const copy = {
    it: ["Benchmark", "Benchmark dei 12 pareri di Vera", "Risultati numerici, sintesi qualitativa e confronti dettagliati con le risposte di riferimento.", "Benchmark →"],
    en: ["Benchmark", "Benchmark of 12 Vera opinions", "Numerical results, qualitative summary and detailed comparisons with reference answers. Documents in Italian.", "Benchmark (Italian) →"],
    fr: ["Benchmark", "Évaluation de 12 avis de Vera", "Résultats chiffrés, synthèse qualitative et comparaisons détaillées avec les réponses de référence. Documents en italien.", "Benchmark (italien) →"],
    de: ["Benchmark", "Benchmark von 12 Vera-Gutachten", "Kennzahlen, qualitative Zusammenfassung und detaillierte Vergleiche mit Referenzantworten. Dokumente auf Italienisch.", "Benchmark (Italienisch) →"],
    es: ["Benchmark", "Evaluación de 12 dictámenes de Vera", "Resultados numéricos, resumen cualitativo y comparaciones detalladas con las respuestas de referencia. Documentos en italiano.", "Benchmark (italiano) →"]
  };
  for (const [language, values] of Object.entries(copy)) {
    Object.assign(page.copy[language], {publicExampleLabel: values[0], publicExampleTitle: values[1], publicExampleSummary: values[2], publicExampleLinkLabel: values[3]});
  }
})();
