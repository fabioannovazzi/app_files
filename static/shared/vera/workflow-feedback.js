"use strict";
(() => {
  const form = document.querySelector("#feedback");
  const status = document.querySelector("#status");
  const button = form.querySelector("button");
  const runId = location.pathname.split("/").pop();
  const storageKey = `vera-feedback:${runId}`;
  let saved = {};
  try { saved = JSON.parse(sessionStorage.getItem(storageKey) || "{}"); } catch { /* Storage can be unavailable. */ }
  const key = location.hash.slice(1) || saved.key || "";
  // Keep the capability out of referrers, logs and subsequent copied URLs.
  history.replaceState(null, "", location.pathname);
  let pending = saved.pending || null;
  const retain = () => {
    try { sessionStorage.setItem(storageKey, JSON.stringify({ key, pending })); } catch { /* Keep the in-page answer. */ }
  };
  retain();
  if (pending && Number.isInteger(pending.stars) && pending.stars >= 1 && pending.stars <= 5) {
    form.querySelector(`input[value="${pending.stars}"]`).checked = true;
    form.querySelector("textarea").value = pending.comment || "";
  }
  if (!/^[A-Za-z0-9_-]{32,128}$/.test(key)) {
    button.disabled = true;
    status.textContent = "Apri il link completo ricevuto da Vera per valutare questo risultato.";
  }
  const updateLabel = () => {
    const rating = Number(new FormData(form).get("stars"));
    form.querySelectorAll(".stars label").forEach((label, index) => label.classList.toggle("filled", index < rating));
    document.querySelector("#comment-label").textContent = rating > 0 && rating <= 2
      ? "Cosa non ha funzionato o cosa ti aspettavi di diverso? (facoltativo)"
      : "Vuoi aggiungere qualcosa? (facoltativo)";
  };
  form.addEventListener("change", updateLabel);
  updateLabel();
  if (pending) status.textContent = "Risposta conservata: puoi riprovare l’invio.";
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!form.reportValidity() || !key) return;
    const data = new FormData(form);
    const stars = Number(data.get("stars"));
    const comment = String(data.get("comment") || "").trim() || null;
    // Preserve the UUID and original answer on an ambiguous network failure.
    if (pending && (pending.stars !== stars || pending.comment !== comment)) {
      status.textContent = "Prima ritenta l’invio della risposta precedente: l’esito non è ancora noto.";
      return;
    }
    pending ||= { key, event_id: crypto.randomUUID(), stars, comment };
    retain();
    button.disabled = true;
    status.textContent = "Invio in corso…";
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 15000);
    try {
      const response = await fetch(`/api/vera/workflow-feedback/${runId}`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(pending), credentials: "omit", redirect: "error",
        signal: controller.signal
      });
      const result = await response.json();
      if (!response.ok || result.recorded !== true || result.event_id !== pending.event_id) throw new Error("unconfirmed");
      status.textContent = "Valutazione ricevuta. Grazie.";
      form.querySelectorAll("input, textarea").forEach(element => { element.disabled = true; });
      button.textContent = "Inviata";
      try { sessionStorage.removeItem(storageKey); } catch { /* Acknowledged in this page. */ }
    } catch {
      status.textContent = "Invio non confermato. La risposta è ancora qui: puoi riprovare.";
      button.disabled = false;
    } finally {
      clearTimeout(timeout);
    }
  });
})();
