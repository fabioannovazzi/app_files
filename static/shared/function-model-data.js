(() => {
  "use strict";
  const currentScript = document.currentScript;
  if (!currentScript || window.MPARANZA_PRIVACY_RENDERER_LOADED) return;
  window.MPARANZA_PRIVACY_RENDERER_LOADED = true;

  const copy = {
    it: {
      label: "Trattamento dei dati",
      title: "Quali dati arrivano al modello",
      placeholder: "Informazioni specifiche per questa funzione in preparazione.",
      report: "Alla fine di ogni esecuzione sostanziale, {product} mostra un breve report con ciò che è stato elaborato localmente, ciò che è stato visibile al modello e gli eventuali limiti di verifica.",
      reportLink: "Come leggere il report →",
    },
    en: {
      label: "Data handling",
      title: "What data reaches the model",
      placeholder: "Function-specific information is being prepared.",
      report: "At the end of every substantive run, {product} shows a short report separating what was processed locally, what was visible to the model, and any limits to verification.",
      reportLink: "How to read the report →",
    },
    fr: {
      label: "Traitement des données",
      title: "Quelles données parviennent au modèle",
      placeholder: "Les informations spécifiques à cette fonction sont en préparation.",
      report: "À la fin de chaque exécution substantielle, {product} affiche un bref rapport distinguant ce qui a été traité localement, ce qui a été visible par le modèle et les limites éventuelles de vérification.",
      reportLink: "Comprendre le rapport →",
    },
    de: {
      label: "Datenverarbeitung",
      title: "Welche Daten das Modell erhält",
      placeholder: "Funktionsspezifische Informationen werden derzeit vorbereitet.",
      report: "Am Ende jeder substanziellen Ausführung zeigt {product} einen kurzen Bericht darüber, was lokal verarbeitet wurde, was für das Modell sichtbar war und welche Prüfgrenzen bestehen.",
      reportLink: "Bericht verstehen →",
    },
    es: {
      label: "Tratamiento de datos",
      title: "Qué datos recibe el modelo",
      placeholder: "Se está preparando la información específica de esta función.",
      report: "Al final de cada ejecución sustancial, {product} muestra un breve informe que separa lo procesado localmente, lo visible para el modelo y los límites de verificación.",
      reportLink: "Cómo leer el informe →",
    },
    ar: {
      label: "معالجة البيانات",
      title: "ما البيانات التي تصل إلى النموذج",
      placeholder: "يجري إعداد المعلومات الخاصة بهذه الوظيفة.",
      report: "في نهاية كل عملية فعلية، يعرض {product} تقريرًا موجزًا يوضح ما عولج محليًا، وما كان ظاهرًا للنموذج، وحدود التحقق.",
      reportLink: "كيفية قراءة التقرير ←",
    },
  };

  const params = new URLSearchParams(window.location.search);
  const basePath = new URL(".", currentScript.src).pathname;
  const pageId = document.body.dataset.functionPage || window.location.pathname.replace(basePath, "").replace(/\/index\.html$|\/$/g, "");
  const runtimeAliases = { codex: "openai-codex", cowork: "anthropic-cowork", chatgpt: "openai-chatgpt", antigravity: "google-antigravity" };
  const requestedRuntime = params.get("runtime") || params.get("host");
  const runtime = runtimeAliases[requestedRuntime] || requestedRuntime;
  const getLanguage = () => {
    const value = (document.documentElement.lang || params.get("lang") || "en").slice(0, 2).toLowerCase();
    return Object.hasOwn(copy, value) ? value : "en";
  };
  const unavailable = {
    it: "La descrizione specifica di questa funzione non è disponibile in questo momento.",
    en: "The description for this function is currently unavailable.",
    fr: "La description de cette fonction est actuellement indisponible.",
    de: "Die Beschreibung dieser Funktion ist derzeit nicht verfügbar.",
    es: "La descripción de esta función no está disponible en este momento.",
    ar: "وصف هذه الوظيفة غير متاح حاليًا.",
  };
  let selectedProduct = null;
  let contract = null;
  let failed = false;

  function render() {
    const main = document.querySelector("main");
    if (!main) return;
    let section = document.querySelector("[data-model-data-status]");
    if (!section) {
      section = document.createElement("section");
      section.id = `${pageId}-model-data`;
    }
    section.className = "function-model-data";
    section.dataset.modelDataWorkflow = pageId;
    const language = getLanguage();
    const labels = copy[language];
    const available = contract && contract.status !== "placeholder" && (!runtime || contract.runtime_profiles.includes(runtime)) && contract.copy[language];
    section.dataset.modelDataStatus = available ? contract.status : "placeholder";
    if (available) {
      section.dataset.privacyProduct = selectedProduct;
      section.dataset.privacyContract = contract.contract_sha256;
      section.dataset.privacyRuntime = runtime || "reviewed-profiles";
    } else {
      delete section.dataset.privacyProduct;
      delete section.dataset.privacyContract;
      delete section.dataset.privacyRuntime;
    }
    const heading = document.createElement("div");
    heading.className = "function-model-data__heading";
    const label = document.createElement("p");
    label.className = "function-model-data__label";
    label.textContent = labels.label;
    const title = document.createElement("h2");
    title.id = `${pageId}-model-data-title`;
    title.textContent = labels.title;
    heading.append(label, title);
    const body = document.createElement("div");
    body.className = "function-model-data__body function-model-data__paragraphs";
    const paragraphs = available ? contract.copy[language] : [failed ? unavailable[language] : labels.placeholder];
    for (const text of paragraphs.flatMap((paragraph) => paragraph.split(/\n\s*\n/).filter(Boolean))) {
      const paragraph = document.createElement("p");
      paragraph.className = "function-model-data__copy";
      paragraph.textContent = text;
      body.append(paragraph);
    }
    // Vera's selected workflows explain reporting in their reviewed page copy.
    // Its other functions must not inherit the generic all-runs promise.
    if (available && selectedProduct !== "vera" && contract.role === "workflow" && labels.report) {
      const paragraph = document.createElement("p");
      paragraph.className = "function-model-data__report-note";
      paragraph.dataset.modelDataReportNote = "";
      const name = selectedProduct.charAt(0).toUpperCase() + selectedProduct.slice(1);
      const link = document.createElement("a");
      link.href = `/data-handling?lang=${language}#run-evidence`;
      link.textContent = labels.reportLink;
      paragraph.append(document.createTextNode(`${labels.report.replace("{product}", name)} `), link);
      body.append(paragraph);
    }
    const head = document.createElement("div");
    head.className = "function-model-data__head";
    head.append(heading, body);
    section.setAttribute("aria-labelledby", title.id);
    section.replaceChildren(head);
    main.append(section);
  }

  async function initialize() {
    render();
    const languageObserver = new MutationObserver(render);
    languageObserver.observe(document.documentElement, { attributes: true, attributeFilter: ["lang"] });
    try {
      const indexResponse = await fetch(new URL("privacy-contracts/index.json", currentScript.src), { credentials: "omit", cache: "no-cache" });
      if (!indexResponse.ok) throw new Error("Privacy index unavailable");
      const index = await indexResponse.json();
      const products = index.pages[pageId];
      if (index.schema_version !== 1 || !Array.isArray(products) || !products.every((product) => ["vera", "clara", "lucia"].includes(product))) throw new Error("Invalid privacy page index");
      const requestedProduct = params.get("from") || params.get("product");
      selectedProduct = requestedProduct || products?.[0];
      if (!products?.includes(selectedProduct)) throw new Error("No privacy contract for this product and page");
      const response = await fetch(new URL(`privacy-contracts/${selectedProduct}.json`, currentScript.src), { credentials: "omit", cache: "no-cache" });
      if (!response.ok) throw new Error("Privacy catalog unavailable");
      const catalog = await response.json();
      if (catalog.schema_version !== 1 || catalog.product !== selectedProduct) throw new Error("Foreign privacy catalog");
      contract = catalog.pages[pageId];
      if (!contract || !/^[0-9a-f]{64}$/.test(contract.contract_sha256)) throw new Error("Missing privacy contract binding");
      if (!Array.isArray(contract.runtime_profiles) || !["relevant", "not-relevant", "placeholder"].includes(contract.status) || !contract.copy || typeof contract.copy !== "object" || !Object.values(contract.copy).every((paragraphs) => Array.isArray(paragraphs) && (contract.status === "placeholder" || paragraphs.length) && paragraphs.every((paragraph) => typeof paragraph === "string" && paragraph.trim()))) throw new Error("Invalid privacy explanation");
    } catch (error) {
      failed = true;
      contract = null;
    }
    render();
    document.dispatchEvent(new CustomEvent("mparanza:privacy-ready"));
  }

  if (!document.querySelector("link[data-function-model-data-style]")) {
    const stylesheet = document.createElement("link");
    stylesheet.rel = "stylesheet";
    stylesheet.href = new URL("function-model-data.css", currentScript.src).href;
    stylesheet.dataset.functionModelDataStyle = "";
    document.head.append(stylesheet);
  }
  if (!document.querySelector("script[data-function-page-navigation]") && !window.MPARANZA_FUNCTION_NAVIGATION) {
    const script = document.createElement("script");
    script.src = new URL("function-page-navigation.js", currentScript.src).href;
    script.dataset.functionPageNavigation = "";
    document.head.append(script);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", initialize, { once: true });
  else initialize();
})();
