// Separate public benchmarks for this workflow.
(() => {
  const page = window.MPARANZA_FUNCTION_PAGES["quesito-legale-fiscale"];
  page.publicExampleHref = "/static/shared/vera/benchmark/index.html";
  page.publicExampleSourceHref = "/static/shared/vera/benchmark-2/index.html";
  const copy = {
    it: ["Due prove sulle risposte di Vera", "Risultati numerici, quesiti, risposte e confronti con le soluzioni pubblicate. I due benchmark sono consultabili separatamente.", "Legal benchmark 1 · 12 quesiti →", "Legal benchmark 2 · 10 quesiti →"],
    en: ["Two evaluations of Vera’s answers", "Numerical results, questions, answers and comparisons with published solutions. The two benchmarks are separate. Documents in Italian.", "Legal benchmark 1 · 12 questions →", "Legal benchmark 2 · 10 questions →"],
    fr: ["Deux évaluations des réponses de Vera", "Résultats chiffrés, questions, réponses et comparaisons avec les solutions publiées. Deux benchmarks distincts. Documents en italien.", "Legal benchmark 1 · 12 questions →", "Legal benchmark 2 · 10 questions →"],
    de: ["Zwei Bewertungen der Antworten von Vera", "Kennzahlen, Fragen, Antworten und Vergleiche mit veröffentlichten Lösungen. Zwei separate Benchmarks. Dokumente auf Italienisch.", "Legal benchmark 1 · 12 Fragen →", "Legal benchmark 2 · 10 Fragen →"],
    es: ["Dos evaluaciones de las respuestas de Vera", "Resultados numéricos, preguntas, respuestas y comparaciones con las soluciones publicadas. Dos benchmarks separados. Documentos en italiano.", "Legal benchmark 1 · 12 preguntas →", "Legal benchmark 2 · 10 preguntas →"]
  };
  for (const [language, values] of Object.entries(copy)) {
    Object.assign(page.copy[language], {publicExampleLabel: "Benchmark", publicExampleTitle: values[0], publicExampleSummary: values[1], publicExampleLinkLabel: values[2], publicExampleSourceLabel: values[3]});
  }
})();
