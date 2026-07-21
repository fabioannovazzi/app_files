(() => {
  "use strict";

  const MODULE_SCOPE = Object.freeze({
    "new-client": "mixed",
    "journal-sampling": "core",
    "check-entries": "mixed",
    "journal-bank-reconciliation": "core",
    "riconciliazione-partite": "core",
    "report-builder": "mixed",
    "prompt-optimizer": "core",
    "deep-research-validator": "core",
    "concordato-plan-review": "italy",
    "previdenza-inps": "italy",
    "registro-imprese-sari": "italy"
  });

  const COPY = Object.freeze({
    it: {
      core: {
        kind: "Workflow core",
        title: "Metodo riutilizzabile, in quattro lingue.",
        body: "Questo lavoro resta lo stesso in italiano, inglese, francese e tedesco. Il perimetro nazionale entra solo quando cambiano regole, enti, fonti o formati."
      },
      mixed: {
        kind: "Core + pacchetto paese",
        title: "Un workflow, con il livello nazionale separato.",
        body: "Il metodo di base resta riutilizzabile; il pacchetto paese aggiunge regole, fonti e formati locali senza cambiare la lingua dell’interfaccia."
      },
      italy: {
        kind: "Pacchetto paese · Italia",
        title: "Regole, enti e formati italiani.",
        body: "Questo percorso applica un perimetro italiano. Puoi leggerlo in tutte e quattro le lingue: la lingua cambia, il paese resta Italia."
      },
      modules: {
        "new-client": "Il fascicolo e il rapporto professionale formano un solo percorso. Documenti, controlli e regole seguono il paese selezionato.",
        "report-builder": "Il motore di reporting è riutilizzabile. Il profilo FPV, FCDE e PNRR per enti locali appartiene al pacchetto Italia.",
        "check-entries": "Il collegamento tra scrittura, supporto ed eccezione forma il core. FatturaPA è l’adattatore italiano."
      },
      coreLink: "Workflow core",
      italyLink: "Pacchetto Italia"
    },
    en: {
      core: {
        kind: "Core workflow",
        title: "A reusable method, in four languages.",
        body: "The work stays the same in Italian, English, French and German. National scope enters only when rules, institutions, sources or formats change."
      },
      mixed: {
        kind: "Core + country pack",
        title: "One workflow, with the national layer kept separate.",
        body: "The underlying method remains reusable; the country pack adds local rules, sources and formats without changing the interface language."
      },
      italy: {
        kind: "Country pack · Italy",
        title: "Italian rules, institutions and formats.",
        body: "This workflow applies an Italian scope. Read it in any of the four languages: the language changes, the country remains Italy."
      },
      modules: {
        "new-client": "The client file and professional relationship form one workflow. Documents, checks and rules follow the selected country.",
        "report-builder": "The reporting engine is reusable. The FPV, FCDE and PNRR local-government profile belongs to the Italy pack.",
        "check-entries": "Connecting an entry, its support and its exceptions makes up the core. FatturaPA is the Italian adapter."
      },
      coreLink: "Core workflows",
      italyLink: "Italy pack"
    },
    fr: {
      core: {
        kind: "Workflow commun",
        title: "Une méthode réutilisable, en quatre langues.",
        body: "Le travail reste identique en italien, anglais, français et allemand. Le périmètre national intervient lorsque les règles, organismes, sources ou formats changent."
      },
      mixed: {
        kind: "Socle + pack pays",
        title: "Un workflow, avec le niveau national séparé.",
        body: "La méthode reste réutilisable ; le pack pays ajoute les règles, sources et formats locaux sans modifier la langue de l’interface."
      },
      italy: {
        kind: "Pack pays · Italie",
        title: "Règles, organismes et formats italiens.",
        body: "Ce workflow applique un périmètre italien. Consultez-le dans les quatre langues : la langue change, le pays reste l’Italie."
      },
      modules: {
        "new-client": "Le dossier client et la relation professionnelle forment un seul parcours. Documents, contrôles et règles suivent le pays sélectionné.",
        "report-builder": "Le moteur de reporting est réutilisable. Le profil FPV, FCDE et PNRR pour les collectivités relève du pack Italie.",
        "check-entries": "Le lien entre écriture, justificatif et exception constitue le socle. FatturaPA est l’adaptateur italien."
      },
      coreLink: "Workflows communs",
      italyLink: "Pack Italie"
    },
    de: {
      core: {
        kind: "Kern-Workflow",
        title: "Eine wiederverwendbare Methode in vier Sprachen.",
        body: "Die Arbeit bleibt auf Italienisch, Englisch, Französisch und Deutsch dieselbe. Der nationale Rahmen kommt erst hinzu, wenn sich Regeln, Institutionen, Quellen oder Formate ändern."
      },
      mixed: {
        kind: "Kern + Länderpaket",
        title: "Ein Workflow mit getrenntem nationalem Baustein.",
        body: "Die Grundmethode bleibt wiederverwendbar; das Länderpaket ergänzt lokale Regeln, Quellen und Formate, unabhängig von der Sprache der Oberfläche."
      },
      italy: {
        kind: "Länderpaket · Italien",
        title: "Italienische Regeln, Institutionen und Formate.",
        body: "Dieser Workflow hat einen italienischen Geltungsbereich. Lesen Sie ihn in allen vier Sprachen: Die Sprache wechselt, das Land bleibt Italien."
      },
      modules: {
        "new-client": "Mandantenakte und Auftragsbeziehung bilden einen Ablauf. Dokumente, Prüfungen und Regeln richten sich nach dem gewählten Land.",
        "report-builder": "Die Reporting-Engine ist wiederverwendbar. Das Kommunalprofil für FPV, FCDE und PNRR gehört zum Italien-Paket.",
        "check-entries": "Die Verbindung von Buchung, Beleg und Ausnahme bildet den Kern. FatturaPA ist der italienische Adapter."
      },
      coreLink: "Kern-Workflows",
      italyLink: "Italien-Paket"
    }
  });

  function language() {
    const value = document.documentElement.lang.slice(0, 2).toLowerCase();
    return COPY[value] ? value : "it";
  }

  function hubLink(anchor, lang) {
    return `../vera/index.html?lang=${lang}#${anchor}`;
  }

  function findInsertionPoint() {
    const main = document.querySelector("main");
    if (!main) return null;
    const breadcrumb = main.querySelector(":scope > .breadcrumb, :scope > .journey-breadcrumb, :scope > .jurisdiction-breadcrumb");
    return { main, breadcrumb };
  }

  function render() {
    const module = document.body.dataset.veraModule;
    if (!module || !MODULE_SCOPE[module]) return;
    const lang = language();
    const strings = COPY[lang];
    const scope = document.body.dataset.veraScope || MODULE_SCOPE[module];
    const base = strings[scope] || strings[MODULE_SCOPE[module]];
    const detail = strings.modules[module] || base.body;
    let panel = document.querySelector("[data-vera-scope-panel]");

    if (!panel) {
      const point = findInsertionPoint();
      if (!point) return;
      panel = document.createElement("aside");
      panel.className = "vera-scope-panel";
      panel.dataset.veraScopePanel = "";
      if (point.breadcrumb) point.breadcrumb.insertAdjacentElement("afterend", panel);
      else point.main.prepend(panel);
    }

    panel.dataset.scope = scope;
    panel.setAttribute("aria-label", base.kind);
    panel.innerHTML = `
      <span class="vera-scope-panel__kind">${base.kind}</span>
      <span class="vera-scope-panel__body">
        <strong>${base.title}</strong>
        <p>${detail}</p>
      </span>
      <span class="vera-scope-panel__links">
        <a href="${hubLink("core", lang)}">${strings.coreLink}</a>
        <a href="${hubLink("italia", lang)}">${strings.italyLink}</a>
      </span>`;
  }

  function start() {
    render();
    const observer = new MutationObserver((records) => {
      if (records.some((record) => record.attributeName === "lang")) render();
    });
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["lang"] });
    window.addEventListener("popstate", render);
    document.addEventListener("click", (event) => {
      if (event.target.closest("[data-lang]")) window.setTimeout(render, 0);
    });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})();
