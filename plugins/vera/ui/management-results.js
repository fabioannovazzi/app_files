/* Read-only professional presentation of the already bounded calculation. */
(() => {
  const words = {...(globalThis.VeraManagementCopy || {}), "Net cash movement":"Movimento netto di cassa", "Top customer revenue share":"Quota dei ricavi del primo cliente", "Top five customer revenue share":"Quota dei ricavi dei primi cinque clienti", "Service gross margin":"Margine lordo dei servizi", receivables:"Crediti", payables:"Debiti", bank:"Banca", sales_lines:"Vendite dettagliate","accounting_profit_bridge": "Raccordo al risultato contabile", "Source totals are reviewed input assertions; arithmetic does not prove source completeness.": "I totali delle fonti sono dati dichiarati e riscontrati; la quadratura aritmetica non prova che le fonti siano complete.", "Consumed operating costs only: no automatic statutory or tax inventory valuation.": "Sono considerati i soli costi operativi consumati; non viene effettuata una valutazione automatica delle rimanenze ai fini civilistici o fiscali.", "Allocations do not establish avoidability, savings or a decision to discontinue an activity.": "Le allocazioni non provano che i costi siano evitabili, che esistano risparmi o che un’attività debba essere interrotta.", "Each view contains non-overlapping objects of one dimension; different views must not be added together.": "Ogni vista contiene oggetti distinti di una sola dimensione; i risultati di viste diverse non devono essere sommati.", "ERP connectors, food/recipe costing and production optimization are outside this implemented path.": "Questo percorso non comprende collegamenti ai gestionali, costi di alimenti e ricette o ottimizzazione della produzione.", "No accounting-profit bridge supplied: reconciliation is limited to the reviewed costing source totals.": "Non è stato fornito un raccordo al risultato contabile: la riconciliazione riguarda soltanto i totali delle fonti di costo riscontrate.", "Synthetic demonstration: these results are not client or market evidence.": "Dimostrazione sintetica: questi risultati non costituiscono evidenza di clienti o di mercato.", direct_costing:"Direct costing",direct_costing_evoluto:"Direct costing evoluto",full_costing:"Full costing",abc:"Activity based costing",costing:"Costi e margini", costing_decisions:"Effetto delle decisioni", reviewed_source_revenue:"Ricavi delle fonti riscontrate", reviewed_source_costs:"Costi delle fonti riscontrate", "Operating revenue":"Ricavi operativi", "Consumed operating costs":"Costi operativi consumati", "Operating profit within reviewed perimeter":"Risultato operativo nel perimetro riscontrato", ratio:"Rapporto", count:"Numero", days:"Giorni"};
  const text = value => words[String(value)] || String(value ?? "Non disponibile");
  const el = (tag, value, className) => {
    const node = document.createElement(tag);
    if (value !== undefined) node.textContent = String(value);
    if (className) node.className = className;
    return node;
  };
  const amount = value => {
    const raw = String(value ?? "Non disponibile");
    if (!/^-?\d+(\.\d+)?$/.test(raw)) return raw;
    const [whole, decimal] = raw.split(".");
    return whole.replace(/\B(?=(\d{3})+(?!\d))/g, ".") + (decimal === undefined ? "" : "," + decimal);
  };
  function table(parent, title, headings, rows) {
    parent.append(el("h3", title));
    if (!rows.length) { parent.append(el("p", "Nessuna voce conservata.", "caption")); return; }
    const wrap = el("div", undefined, "prepared-table"), grid = el("table"), head = el("thead"), line = el("tr"), body = el("tbody");
    wrap.tabIndex = 0; wrap.setAttribute("aria-label", title);
    for (const caption of headings) { const cell = el("th", caption); cell.scope = "col"; line.append(cell); }
    head.append(line);
    for (const values of rows) { const row = el("tr"); for (const value of values) row.append(el("td", value)); body.append(row); }
    grid.append(head, body); wrap.append(grid); parent.append(wrap);
  }
  function metricName(metric) {
    const names = {"ap.total.outstanding":"Debiti aperti", "ap.total.overdue":"Debiti scaduti", "ar.total.outstanding":"Crediti aperti", "ar.total.overdue":"Crediti scaduti", "cash.latest.reported_balance":"Ultimo saldo dichiarato"};
    const id = metric.metric_id || metric.id || "";
    if (names[id]) return names[id];
    if (/^(pnl|budget)\./.test(id)) {
      const key = id.split(".").at(-1), variance = key.endsWith("_variance"), item = key.replace(/_variance$/, "");
      const name = words[item];
      if (name) {
        const period = id.match(/\d{4}-\d{2}/)?.[0];
        const scope = period ? " · " + period : id.includes(".forecast.") ? " · previsionale" : id.includes(".total.") ? " · totale" : "";
        return name + (variance ? " · scostamento dal budget" : "") + scope;
      }
    }
    const methods={direct_costing:"Direct costing",direct_costing_evoluto:"Direct costing evoluto",full_costing:"Full costing",abc:"Activity based costing"};
    const method=id.match(/^costing\.([^.]+)\.[^.]+\.margin$/)?.[1];
    if (method && methods[method]) return String(metric.label).replace(new RegExp(" · " + method + "$"), " · " + methods[method]);
    return text(metric.label || "Indicatore senza descrizione");
  }
  function overview(parent, rows) {
    const data = Object.fromEntries(rows.filter(row => typeof row.field === "string").map(row => [row.field, row.value]));
    const period = data.reporting_period || {}, facts = el("dl");
    for (const [caption, value] of [["Impresa",data.entity],["Periodo",period.start && period.end ? period.start + " → " + period.end : null],["Data di riferimento",period.cutoff],["Valuta",data.currency],["Stato del calcolo",data.status ? text(data.status) : null]])
      if (value !== null && value !== undefined) facts.append(el("dt",caption),el("dd",value));
    parent.append(facts,el("p","Risultati sintetici delle fonti mappate. Le voci mancanti non attestano saldi pari a zero o la completezza del risultato economico.","notice"));
    const metrics = Array.isArray(data.metrics) ? data.metrics : Object.values(data.metrics || {}), groups = new Map();
    for (const metric of metrics) { const key = metric.section || "Indicatori"; if (!groups.has(key)) groups.set(key,[]); groups.get(key).push([metricName(metric),amount(metric.value),text(metric.unit || "")]); }
    for (const [name, values] of groups) table(parent,text(name),["Indicatore","Valore","Unità"],values);
    table(parent,"Copertura dei dati",["Analisi","Disponibilità","Motivo"],(data.coverage || []).map(row=>[text(row.section),text(row.status),row.reason ? text(row.reason) : ""]));
    table(parent,"Controlli sui totali",["Fonte","Esito","Totale riscontrato","Totale atteso","Differenza","Tolleranza"],(data.controls || []).map(row=>[text(row.role || "Controllo"),text(row.status),amount(row.actual),amount(row.expected),amount(row.difference),amount(row.tolerance)]));
    if (data.limitations?.length) { parent.append(el("h3","Limiti da considerare")); const list=el("ul"); for(const value of data.limitations)list.append(el("li",text(value))); parent.append(list); }
  }
  const clean = value => String(value).replace(/\*\*/g, "").replace(/`/g, "");
  const cells = line => line.trim().replace(/^\|/, "").replace(/\|$/, "").split(/(?<!\\)\|/).map(value=>clean(value.trim().replace(/\\\|/g,"|")));
  function documentView(parent, content) {
    const lines=String(content).split(/\r?\n/);
    for(let i=0;i<lines.length;i++) {
      const line=lines[i]; if(!line.trim())continue;
      if(line.trim().startsWith("|") && lines[i+1] && cells(lines[i+1]).every(value=>/^:?-+:?$/.test(value))) {
        const headings=cells(line), values=[];i+=2;
        while(i<lines.length && lines[i].trim().startsWith("|")){values.push(cells(lines[i]));i++;}i--;
        table(parent,"Prospetto conservato",headings,values);continue;
      }
      const heading=line.match(/^(#{1,6})\s+(.*)$/);
      if(heading)parent.append(el("h"+Math.min(4,heading[1].length+1),clean(heading[2])));
      else if(/^[-*]\s/.test(line)){const list=el("ul");list.append(el("li",clean(line.slice(2))));parent.append(list);}
      else parent.append(el("p",clean(line.replace(/^>\s?/,""))));
    }
  }
  globalThis.VeraManagementResults = {overview,documentView};
})();
