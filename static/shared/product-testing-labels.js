/* Shared product catalogue labels; levels still come only from received runs. */
(() => {
  "use strict";
  const labels = {
  "it": {
    "untried": "Da provare su casi concreti",
    "agent": "Provata da un agente",
    "tried": "Provata con successo da un professionista",
    "repeated": "Provata con successo da almeno tre professionisti",
    "note": "Lo stato si aggiorna dai processi conclusi. Ogni computer conta una volta; le stelle restano separate.",
    "unavailable": "Aggiornamento dello stato temporaneamente non disponibile."
  },
  "en": {
    "untried": "To be tried on real cases",
    "agent": "Tested by an agent",
    "tried": "Successfully tested by a professional",
    "repeated": "Successfully tested by at least three professionals",
    "note": "Status updates from completed processes. Each computer counts once; stars remain separate.",
    "unavailable": "Status updates are temporarily unavailable."
  },
  "fr": {
    "untried": "À essayer sur des cas concrets",
    "agent": "Testée par un agent",
    "tried": "Testée avec succès par un professionnel",
    "repeated": "Testée avec succès par au moins trois professionnels",
    "note": "Le statut se met à jour à partir des processus terminés. Chaque ordinateur compte une fois ; les étoiles restent distinctes.",
    "unavailable": "La mise à jour du statut est temporairement indisponible."
  },
  "de": {
    "untried": "An konkreten Fällen zu erproben",
    "agent": "Von einem Agenten erprobt",
    "tried": "Von einer Fachperson erfolgreich erprobt",
    "repeated": "Von mindestens drei Fachleuten erfolgreich erprobt",
    "note": "Der Status wird anhand abgeschlossener Prozesse aktualisiert. Jeder Computer zählt einmal; Sterne bleiben getrennt.",
    "unavailable": "Statusaktualisierungen sind vorübergehend nicht verfügbar."
  },
  "es": {
    "untried": "Por probar en casos concretos",
    "agent": "Probada por un agente",
    "tried": "Probada con éxito por un profesional",
    "repeated": "Probada con éxito por al menos tres profesionales",
    "note": "El estado se actualiza con los procesos terminados. Cada ordenador cuenta una vez; las estrellas se mantienen separadas.",
    "unavailable": "La actualización del estado no está disponible temporalmente."
  }
};
  function render() {
    const copy = labels[document.documentElement.lang] || labels.it;
    document.querySelectorAll("[data-testing-label]").forEach(node => {
      node.textContent = copy[node.dataset.testingLabel];
    });
    document.querySelectorAll('.function-test-indicator[role="img"]').forEach(node => {
      node.setAttribute("aria-label", copy[node.dataset.testStatus]);
      node.title = copy[node.dataset.testStatus];
    });
  }
  document.addEventListener("vera-testing-status-updated", render);
  new MutationObserver(render).observe(document.documentElement, { attributes: true, attributeFilter: ["lang"] });
  render();
})();
