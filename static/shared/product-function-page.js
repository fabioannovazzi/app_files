(() => {
  "use strict";

  const currentScript = document.currentScript;
  const root = document.getElementById("function-page-root");
  const pages = window.MPARANZA_FUNCTION_PAGES;
  const pageKey = document.body.dataset.functionPage;
  const page = pages && pages[pageKey];
  if (!root || !page) return;

  const labels = {
    it: {
      skip: "Vai al contenuto",
      function: "Funzione",
      input: "Fornisci",
      work: "La funzione esegue",
      output: "Ricevi",
      responsibilitiesLabel: "Responsabilità",
      responsibilitiesTitle: "Chi fa che cosa",
      productRole: (product) => `${product} prepara`,
      sharedRole: "La funzione prepara",
      professionalRole: "Il professionista decide",
      promptLabel: "Per iniziare",
      promptTitle: "Prompt iniziale",
      modelDataLabel: "Trattamento dei dati",
      modelDataTitle: "Quali dati arrivano al modello",
      source: "Codice sorgente",
      dataPolicy: "Gestione dei dati",
      language: "Lingua",
    },
    en: {
      skip: "Skip to content",
      function: "Function",
      input: "Provide",
      work: "The function performs",
      output: "Receive",
      responsibilitiesLabel: "Responsibilities",
      responsibilitiesTitle: "Who does what",
      productRole: (product) => `${product} prepares`,
      sharedRole: "The function prepares",
      professionalRole: "The professional decides",
      promptLabel: "To begin",
      promptTitle: "Starting prompt",
      modelDataLabel: "Data handling",
      modelDataTitle: "What data reaches the model",
      source: "Source code",
      dataPolicy: "Data handling",
      language: "Language",
    },
    fr: {
      skip: "Aller au contenu",
      function: "Fonction",
      input: "Vous fournissez",
      work: "La fonction exécute",
      output: "Vous recevez",
      responsibilitiesLabel: "Responsabilités",
      responsibilitiesTitle: "Qui fait quoi",
      productRole: (product) => `${product} prépare`,
      sharedRole: "La fonction prépare",
      professionalRole: "Le professionnel décide",
      promptLabel: "Pour commencer",
      promptTitle: "Prompt initial",
      modelDataLabel: "Traitement des données",
      modelDataTitle: "Quelles données parviennent au modèle",
      source: "Code source",
      dataPolicy: "Traitement des données",
      language: "Langue",
    },
    de: {
      skip: "Zum Inhalt",
      function: "Funktion",
      input: "Sie stellen bereit",
      work: "Die Funktion führt aus",
      output: "Sie erhalten",
      responsibilitiesLabel: "Verantwortung",
      responsibilitiesTitle: "Wer was übernimmt",
      productRole: (product) => `${product} bereitet vor`,
      sharedRole: "Die Funktion bereitet vor",
      professionalRole: "Der Berufsträger entscheidet",
      promptLabel: "Zum Start",
      promptTitle: "Startprompt",
      modelDataLabel: "Datenverarbeitung",
      modelDataTitle: "Welche Daten das Modell erhält",
      source: "Quellcode",
      dataPolicy: "Datenverarbeitung",
      language: "Sprache",
    },
    es: {
      skip: "Ir al contenido",
      function: "Función",
      input: "Proporcionas",
      work: "La función ejecuta",
      output: "Recibes",
      responsibilitiesLabel: "Responsabilidades",
      responsibilitiesTitle: "Quién hace qué",
      productRole: (product) => `${product} prepara`,
      sharedRole: "La función prepara",
      professionalRole: "El profesional decide",
      promptLabel: "Para empezar",
      promptTitle: "Prompt inicial",
      modelDataLabel: "Tratamiento de datos",
      modelDataTitle: "Qué datos recibe el modelo",
      source: "Código fuente",
      dataPolicy: "Tratamiento de datos",
      language: "Idioma",
    },
  };

  const params = new URLSearchParams(window.location.search);
  const requestedLanguage = (params.get("lang") || page.defaultLanguage || "en").toLowerCase();
  const language = Object.hasOwn(labels, requestedLanguage) ? requestedLanguage : page.defaultLanguage;
  const text = page.copy[language] || page.copy[page.defaultLanguage];
  const ui = labels[language];
  const isShared = page.shared === true;
  const homeUrl = `/?lang=${language}`;

  document.documentElement.lang = language;
  document.title = `${text.name} | ${isShared ? "Mparanza" : page.product}`;
  const description = document.querySelector('meta[name="description"]');
  if (description) description.setAttribute("content", text.summary);
  const canonical = document.querySelector('link[rel="canonical"]');
  if (canonical) canonical.setAttribute("href", window.location.href.split("?")[0].split("#")[0]);

  const languageButtons = Object.keys(labels)
    .map(
      (code) =>
        `<button type="button" data-language="${code}" aria-pressed="${code === language}">${code.toUpperCase()}</button>`,
    )
    .join("");

  root.innerHTML = `
    <a class="skip-link" href="#main-content">${ui.skip}</a>
    <header class="pf-nav">
      <div class="pf-nav__inner">
        <div class="pf-identity">
          <a class="pf-brand" href="${homeUrl}" aria-label="Mparanza">
            <img src="https://mparanza.com/images/MPARANZA-HORIZONTAL.png" alt="Mparanza">
          </a>
        </div>
        <div class="pf-languages" role="group" aria-label="${ui.language}">${languageButtons}</div>
      </div>
    </header>
    <main class="pf-main" id="main-content" data-function-name="${text.name}">
      <section class="pf-hero">
        <div>
          <p class="pf-label">${ui.function}</p>
          <h1>${text.name}</h1>
          <p class="pf-summary">${text.summary}</p>
        </div>
        <div class="pf-hero__aside"><p>${text.useWhen}</p></div>
      </section>
      <section class="pf-facts" aria-label="${text.name}">
        <article class="pf-fact"><h2>${ui.input}</h2><p>${text.input}</p></article>
        <article class="pf-fact"><h2>${ui.work}</h2><p>${text.work}</p></article>
        <article class="pf-fact"><h2>${ui.output}</h2><p>${text.output}</p></article>
      </section>
      <section class="pf-section">
        <div class="pf-section__head">
          <div><p class="pf-section__label">${ui.responsibilitiesLabel}</p><h2>${ui.responsibilitiesTitle}</h2></div>
          <p class="pf-section__copy">${text.responsibilityIntro}</p>
        </div>
        <div class="pf-responsibilities">
          <article class="pf-responsibility"><h3>${isShared ? ui.sharedRole : ui.productRole(page.product)}</h3><p>${text.productRole}</p></article>
          <article class="pf-responsibility"><h3>${ui.professionalRole}</h3><p>${text.professionalRole}</p></article>
        </div>
      </section>
      <section class="pf-section">
        <div class="pf-section__head">
          <div><p class="pf-section__label">${ui.promptLabel}</p><h2>${ui.promptTitle}</h2></div>
          <code class="pf-prompt">${text.prompt}</code>
        </div>
      </section>
      <section class="function-model-data" data-model-data-workflow="${pageKey}" data-model-data-status="${text.modelDataStatus}" aria-labelledby="${pageKey}-model-data-title">
        <div class="function-model-data__head">
          <div class="function-model-data__heading"><p class="function-model-data__label">${ui.modelDataLabel}</p><h2 id="${pageKey}-model-data-title">${ui.modelDataTitle}</h2></div>
          <p class="function-model-data__copy">${text.modelData}</p>
        </div>
      </section>
    </main>
    <footer class="pf-footer">
      <div class="pf-footer__inner">
        <span>${isShared ? text.name : `${page.product} · ${text.name}`}</span>
        <div><a href="https://github.com/fabioannovazzi/app_files">${ui.source}</a> · <a href="/data-handling?lang=${language}">${ui.dataPolicy}</a></div>
      </div>
    </footer>
  `;

  const loadNavigation = () => {
    if (window.MPARANZA_FUNCTION_NAVIGATION) {
      window.MPARANZA_FUNCTION_NAVIGATION.render();
      return;
    }
    if (!currentScript || document.querySelector("script[data-function-page-navigation]")) return;
    const script = document.createElement("script");
    script.src = new URL("function-page-navigation.js", currentScript.src).href;
    script.dataset.functionPageNavigation = "";
    document.head.append(script);
  };

  loadNavigation();

  root.querySelectorAll("[data-language]").forEach((button) => {
    button.addEventListener("click", () => {
      const nextParams = new URLSearchParams(window.location.search);
      nextParams.set("lang", button.dataset.language);
      window.location.search = nextParams.toString();
    });
  });
})();
