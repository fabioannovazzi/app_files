"use strict";

const form = document.getElementById("recovery-form");
const status = document.getElementById("status");
const output = document.getElementById("response");
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
    const response = await fetch(`/api/${document.body.dataset.product}/incident-recovery/${document.getElementById("operation").value}`, {
      method: "POST", credentials: "same-origin", redirect: "error",
      headers: { "Content-Type": "application/json", "X-Mparanza-Recovery": "1" }, body,
    });
    const result = await response.json();
    output.textContent = JSON.stringify(result, null, 2);
    status.textContent = response.ok ? "Risposta ricevuta. Verificare la ricevuta prima di considerare consegnati i dati." : `Richiesta non accettata (${response.status}).`;
    if (response.ok) input.value = "{}";
  } catch {
    status.textContent = "Consegna non verificata. Conservare la stessa richiesta e gli stessi identificativi per il tentativo successivo.";
  } finally {
    button.disabled = false;
  }
});
