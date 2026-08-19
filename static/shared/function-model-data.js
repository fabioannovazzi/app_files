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
  const paragraphSeparator = /\n\s*\n/;

  const renderParagraphs = (target) => {
    const paragraphs = target.textContent
      .split(paragraphSeparator)
      .map((value) => value.trim())
      .filter(Boolean);
    if (paragraphs.length < 2) return null;

    let container = target;
    if (target.tagName === "P") {
      container = document.createElement("div");
      for (const attribute of target.attributes) {
        if (attribute.name !== "class") {
          container.setAttribute(attribute.name, attribute.value);
        }
      }
      target.replaceWith(container);
    }
    container.className = "function-model-data__body function-model-data__paragraphs";
    const fragment = document.createDocumentFragment();
    for (const value of paragraphs) {
      const paragraph = document.createElement("p");
      paragraph.className = "function-model-data__copy";
      paragraph.textContent = value;
      fragment.append(paragraph);
    }
    container.replaceChildren(fragment);
    return container;
  };

  const initializeParagraphs = () => {
    document.querySelectorAll(".function-model-data__copy").forEach((target) => {
      const container = renderParagraphs(target);
      if (!container) return;

      const observer = new MutationObserver(() => {
        if (paragraphSeparator.test(container.textContent)) {
          renderParagraphs(container);
        }
      });
      observer.observe(container, { childList: true, characterData: true, subtree: true });
    });
  };

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
    const titleId = `${workflow}-model-data-title`;
    section.setAttribute("aria-labelledby", titleId);

    const head = document.createElement("div");
    head.className = "function-model-data__head";

    const heading = document.createElement("div");
    heading.className = "function-model-data__heading";

    const label = document.createElement("p");
    label.className = "function-model-data__label";
    label.textContent = text.label;

    const title = document.createElement("h2");
    title.id = titleId;
    title.textContent = text.title;

    const paragraph = document.createElement("p");
    paragraph.className = "function-model-data__copy";
    paragraph.textContent = text.placeholder;

    heading.append(label, title);
    head.append(heading, paragraph);
    section.append(head);
    main.append(section);
  };

  const initialize = () => {
    appendPlaceholder();
    initializeParagraphs();
  };

  const loadNavigation = () => {
    if (window.MPARANZA_FUNCTION_NAVIGATION) {
      window.MPARANZA_FUNCTION_NAVIGATION.render();
      return;
    }
    if (document.querySelector("script[data-function-page-navigation]")) return;
    const script = document.createElement("script");
    script.src = new URL("function-page-navigation.js", currentScript.src).href;
    script.dataset.functionPageNavigation = "";
    document.head.append(script);
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initialize, { once: true });
  } else {
    initialize();
  }
  loadNavigation();
})();
