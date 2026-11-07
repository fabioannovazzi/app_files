(() => {
  const names = { vera: "Vera", lucia: "Lucia", clara: "Clara", codex: "Codex", cowork: "Cowork", antigravity: "Antigravity" };
  const labels = {
    "lucia:controllo-documento": "Trova errori e incoerenze nel documento",
    "vera:journal-bank-reconciliation": "Riconciliazione banca e giornale",
  };
  const status = document.getElementById("status");
  let latest = null;
  let pending = false;

  function row(label, counts, product) {
    const tr = document.createElement("tr");
    const heading = document.createElement("th");
    heading.scope = "row";
    if (product) {
      const name = document.createElement("span");
      name.className = "product-name";
      name.textContent = names[product];
      heading.append(name);
    }
    heading.append(document.createTextNode(label));
    tr.append(heading);
    for (const key of ["started", "completed", "failed"]) {
      const td = document.createElement("td");
      td.textContent = counts[key].toLocaleString("it-IT");
      tr.append(td);
    }
    return tr;
  }

  function render(data) {
    document.getElementById("functions").replaceChildren(...data.functions
      .filter(item => item.started > 0)
      .map(item => row(labels[`${item.product}:${item.pipeline}`] || item.label, item, item.product)));
    document.getElementById("apps").replaceChildren(...data.apps
      .filter(item => item.started > 0)
      .map(item => row(names[item.app], item)));
    document.querySelectorAll("[data-total]").forEach(cell => {
      cell.textContent = data.totals[cell.dataset.total].toLocaleString("it-IT");
    });
    const releaseDate = new Intl.DateTimeFormat("it-IT", { dateStyle: "long", timeZone: "UTC" });
    document.getElementById("versions").textContent = "Versioni minime incluse (senza MCP remoto) e date di rilascio:\n" +
      ["vera", "lucia", "clara"].map(product =>
        `${names[product]} ${data.minimum_versions[product]} — ${releaseDate.format(new Date(data.minimum_version_release_dates[product] + "T00:00:00Z"))}`
      ).join("\n") + "\nSono incluse anche le versioni successive.";
    document.getElementById("empty").hidden = data.totals.started > 0;
    document.getElementById("coverage").hidden = data.identity_complete;
    document.getElementById("results").hidden = false;
    status.textContent = "Aggiornato il " + new Intl.DateTimeFormat("it-IT", {
      dateStyle: "long", timeStyle: "short", timeZone: "Europe/Rome",
    }).format(new Date(data.updated_at)) + " · Aggiornamento automatico ogni minuto.";
  }

  async function refresh() {
    if (pending || document.hidden) return;
    pending = true;
    try {
      const response = await fetch("/api/usage-summary", { cache: "no-store", credentials: "omit" });
      if (!response.ok) throw new Error("Usage unavailable");
      const data = await response.json();
      render(data);
      latest = data;
    } catch {
      status.textContent = latest
        ? "Aggiornamento temporaneamente non disponibile. Sono visibili gli ultimi dati ricevuti."
        : "Dati temporaneamente non disponibili. La pagina riproverà automaticamente.";
    } finally {
      pending = false;
    }
  }
  refresh();
  setInterval(refresh, 60000);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) refresh(); });
})();
