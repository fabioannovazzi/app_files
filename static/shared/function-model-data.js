(() => {
  "use strict";

  const currentScript = document.currentScript;
  if (!currentScript) return;

  const copy = {
    it: {
      label: "Trattamento dei dati",
      title: "Quali dati arrivano al modello",
      placeholder: "Informazioni specifiche per questa funzione in preparazione.",
    },
    en: {
      label: "Data handling",
      title: "What data reaches the model",
      placeholder: "Function-specific information is being prepared.",
    },
    fr: {
      label: "Traitement des données",
      title: "Quelles données parviennent au modèle",
      placeholder: "Les informations spécifiques à cette fonction sont en préparation.",
    },
    de: {
      label: "Datenverarbeitung",
      title: "Welche Daten das Modell erhält",
      placeholder: "Funktionsspezifische Informationen werden derzeit vorbereitet.",
    },
    es: {
      label: "Tratamiento de datos",
      title: "Qué datos recibe el modelo",
      placeholder: "Se está preparando la información específica de esta función.",
    },
  };

  const params = new URLSearchParams(window.location.search);
  const requestedLanguage = (params.get("lang") || document.documentElement.lang || "en")
    .slice(0, 2)
    .toLowerCase();
  const language = Object.hasOwn(copy, requestedLanguage) ? requestedLanguage : "en";

  if (!document.querySelector('link[data-function-model-data-style]')) {
    const stylesheet = document.createElement("link");
    stylesheet.rel = "stylesheet";
    stylesheet.href = new URL("function-model-data.css", currentScript.src).href;
    stylesheet.dataset.functionModelDataStyle = "";
    document.head.append(stylesheet);
  }

  const appendPlaceholder = () => {
    if (document.querySelector("[data-model-data-status]")) return;

    const main = document.querySelector("main");
    if (!main) return;

    const pathParts = window.location.pathname.split("/").filter(Boolean);
    const workflow = pathParts.at(-2) || "unknown";
    const text = copy[language];
    const section = document.createElement("section");
    section.className = "function-model-data";
    section.dataset.modelDataWorkflow = workflow;
    section.dataset.modelDataStatus = "placeholder";
    section.setAttribute("aria-labelledby", "function-model-data-title");

    const label = document.createElement("p");
    label.className = "function-model-data__label";
    label.textContent = text.label;

    const title = document.createElement("h2");
    title.id = "function-model-data-title";
    title.textContent = text.title;

    const paragraph = document.createElement("p");
    paragraph.className = "function-model-data__copy";
    paragraph.textContent = text.placeholder;

    section.append(label, title, paragraph);
    main.append(section);
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", appendPlaceholder, { once: true });
  } else {
    appendPlaceholder();
  }
})();
