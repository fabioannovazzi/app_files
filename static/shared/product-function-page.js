(() => {
  "use strict";

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
  const productSlug = page.product.toLowerCase();
  const productUrl = `../${productSlug}/index.html?lang=${language}`;
  const homeUrl = `/?lang=${language}`;

  document.documentElement.lang = language;
  document.title = `${text.name} | ${page.product}`;
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
          <a class="pf-product" href="${productUrl}">${page.product}</a>
        </div>
        <div class="pf-languages" role="group" aria-label="${ui.language}">${languageButtons}</div>
      </div>
    </header>
    <main class="pf-main" id="main-content">
      <p class="pf-breadcrumb"><a href="${productUrl}">${page.product}</a><span aria-hidden="true">/</span>${text.name}</p>
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
          <article class="pf-responsibility"><h3>${ui.productRole(page.product)}</h3><p>${text.productRole}</p></article>
          <article class="pf-responsibility"><h3>${ui.professionalRole}</h3><p>${text.professionalRole}</p></article>
        </div>
      </section>
      <section class="pf-section">
        <div class="pf-section__head">
          <div><p class="pf-section__label">${ui.promptLabel}</p><h2>${ui.promptTitle}</h2></div>
          <code class="pf-prompt">${text.prompt}</code>
        </div>
      </section>
      <section class="pf-section pf-model-data" data-model-data-workflow="${pageKey}" data-model-data-status="${text.modelDataStatus}">
        <div class="pf-section__head">
          <div><p class="pf-section__label">${ui.modelDataLabel}</p><h2>${ui.modelDataTitle}</h2></div>
          <p class="pf-section__copy">${text.modelData}</p>
        </div>
      </section>
    </main>
    <footer class="pf-footer">
      <div class="pf-footer__inner">
        <span>${page.product} · ${text.name}</span>
        <div><a href="https://github.com/fabioannovazzi/app_files">${ui.source}</a> · <a href="/data-handling?lang=${language}">${ui.dataPolicy}</a></div>
      </div>
    </footer>
  `;

  root.querySelectorAll("[data-language]").forEach((button) => {
    button.addEventListener("click", () => {
      const nextParams = new URLSearchParams(window.location.search);
      nextParams.set("lang", button.dataset.language);
      window.location.search = nextParams.toString();
    });
  });
})();
