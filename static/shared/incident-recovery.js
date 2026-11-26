"use strict";

const form = document.getElementById("recovery-form");
const status = document.getElementById("status");
const output = document.getElementById("response");
const product = document.body.dataset.product;
const patchReport = document.getElementById("patch-report-id");

function submitRecovery(operation, body) {
  return fetch(`/api/${product}/incident-recovery/${operation}`, {
    method: "POST", credentials: "same-origin", redirect: "error",
    headers: { "Content-Type": "application/json", "X-Mparanza-Recovery": "1" }, body,
  });
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = form.querySelector("button");
  const input = document.getElementById("arguments");
  let body;
  try {
    body = JSON.stringify(JSON.parse(input.value));
  } catch {
    status.textContent = "Correggere il JSON prima dell’invio.";
    return;
  }
  button.disabled = true;
  output.textContent = "";
  status.textContent = "Invio in corso…";
  try {
    const operation = document.getElementById("operation").value;
    const response = await submitRecovery(operation, body);
    const result = await response.json();
    output.textContent = JSON.stringify(result, null, 2);
    status.textContent = response.ok ? "Risposta ricevuta. Verificare la ricevuta prima di considerare consegnati i dati." : `Richiesta non accettata (${response.status}).`;
    if (response.ok) {
      input.value = "{}";
      if (operation === "report" && result.report_id && !patchReport.value) {
        patchReport.value = result.report_id;
      }
    }
  } catch {
    status.textContent = "Consegna non verificata. Conservare la stessa richiesta e gli stessi identificativi per il tentativo successivo.";
  } finally {
    button.disabled = false;
  }
});

const patchForm = document.getElementById("patch-form");
const patchStatus = document.getElementById("patch-status");
const patchFile = document.getElementById("patch-file");
const patchResult = document.getElementById("patch-result");
patchForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = patchForm.querySelector("button");
  const file = patchFile.files[0];
  if (!file || file.size > 256 * 1024 || !patchResult.value.trim()) {
    patchStatus.textContent = "Seleziona un diff di massimo 256 KiB e indica il risultato della prova.";
    return;
  }
  button.disabled = true;
  patchStatus.textContent = "Invio della patch in corso…";
  try {
    const bytes = await file.arrayBuffer();
    const diff = new TextDecoder("utf-8", { fatal: true, ignoreBOM: true }).decode(bytes);
    const digest = await crypto.subtle.digest("SHA-256", bytes);
    const sha256 = Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, "0")).join("");
    const report_id = patchReport.value.trim();
    const response = await submitRecovery("patch", JSON.stringify({
      patch: { report_id, sha256, diff, result: patchResult.value.trim() },
    }));
    const receipt = await response.json();
    if (response.ok && receipt.status === "received" && receipt.sha256 === sha256 && receipt.report_id === report_id.toLowerCase()) {
      patchStatus.textContent = `Patch ricevuta. SHA-256 ${receipt.sha256}`;
      patchFile.value = "";
      patchResult.value = "";
    } else if ([401, 404].includes(response.status)) {
      patchStatus.textContent = "Verifica l’ID della segnalazione e recupera l’identità originale se necessario.";
    } else {
      patchStatus.textContent = `Ricevuta della patch non confermata (${response.status}).`;
    }
  } catch (error) {
    patchStatus.textContent = error instanceof TypeError
      ? "Consegna non verificata. Controlla che il file sia un diff UTF-8 e riprova."
      : "Consegna non verificata. Conserva il file per riprovare.";
  } finally {
    button.disabled = false;
  }
});
