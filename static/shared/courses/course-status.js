/* Only concluded Vera lessons feed this catalogue and its language editions. */
(() => {
  const icons = [...document.querySelectorAll("[data-vera-course]")];
  if (!icons.length) return;
  const copy = {
    it: ["Stato del corso non disponibile", "Nessun completamento registrato", "Corso completato; computer non classificato", "Corso completato dal computer di test", "Corso completato su uno o due computer di professionisti", "Corso completato su almeno tre computer di professionisti"],
    en: ["Course status unavailable", "No recorded completion", "Course completed; computer not classified", "Course completed on the test computer", "Course completed on one or two professional computers", "Course completed on at least three professional computers"],
    fr: ["État du cours indisponible", "Aucun achèvement enregistré", "Cours terminé ; ordinateur non classé", "Cours terminé sur l’ordinateur de test", "Cours terminé sur un ou deux ordinateurs de professionnels", "Cours terminé sur au moins trois ordinateurs de professionnels"],
    de: ["Kursstatus nicht verfügbar", "Kein Abschluss erfasst", "Kurs abgeschlossen; Rechner nicht zugeordnet", "Kurs auf dem Testrechner abgeschlossen", "Kurs auf einem oder zwei beruflich genutzten Rechnern abgeschlossen", "Kurs auf mindestens drei beruflich genutzten Rechnern abgeschlossen"],
    es: ["Estado del curso no disponible", "Ninguna finalización registrada", "Curso completado; equipo sin clasificar", "Curso completado en el equipo de prueba", "Curso completado en uno o dos equipos de profesionales", "Curso completado en al menos tres equipos de profesionales"]
  };
  const labels = copy[document.documentElement.lang] || copy.it;
  const states = ["unknown", "untried", "completed", "agent", "tried", "repeated"];
  function paint(icon, state) {
    icon.dataset.level = state;
    icon.title = labels[states.indexOf(state)];
    icon.setAttribute("aria-label", icon.title);
  }
  icons.forEach(icon => paint(icon, "unknown"));
  let busy = false;
  async function refresh() {
    if (busy || document.hidden) return;
    busy = true;
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 10000);
    try {
      const response = await fetch("/api/vera/course-status", {credentials: "omit", cache: "no-store", signal: controller.signal});
      if (!response.ok) throw new Error("Unavailable");
      const {courses} = await response.json();
      for (const icon of icons) {
        const level = courses?.[icon.dataset.veraCourse];
        paint(icon, states.includes(level) ? level : "unknown");
      }
    } catch {
      icons.forEach(icon => paint(icon, "unknown"));
    } finally {
      clearTimeout(timeout);
      busy = false;
    }
  }
  refresh();
  setInterval(refresh, 60000);
  document.addEventListener("visibilitychange", refresh);
})();
