"use strict";
// Shared by the Bilancio pilot and Vera's existing studio panel.
(() => {
  const views = {AREA_DASHBOARD:"Aree del bilancio", AREA_WORKPAPERS:"Carte di lavoro", AREA_CONTROLS:"Controlli", OIC_CATALOGUE:"Catalogo OIC", QUALITATIVE_EVIDENCE:"Documenti e applicabilità"};
  const states = {ACTIVE:"Attiva", EXCLUDED:"Esclusa con motivazione", OPEN:"Da completare", PASS:"Rivisto", NOT_APPLICABLE:"Non applicabile, confermato", UNDETERMINABLE:"Da chiarire", OUT_OF_SCOPE:"Fuori perimetro", REVIEW_REQUIRED:"Da riesaminare", MODEL_SUGGESTED:"Proposta da rivedere", REJECTED:"Respinta", SUPERSEDED:"Sostituita", APPLICABLE:"Applicabile", NOT_ACTIVATED:"Non attivato", NOT_APPLICABLE_WITH_EVIDENCE:"Esclusione documentata", PLAN_REQUIRED:"Piano delle aree da rivedere", REVIEWED:"Revisione registrata"};
  const scheduleLabels={FIXED_ASSETS:"immobilizzazioni",INVENTORIES:"rimanenze",RECEIVABLES:"crediti",PAYABLES:"debiti",TFR:"TFR",EQUITY:"patrimonio netto",PROVISIONS:"fondi rischi",TAXES:"imposte",CASH_FLOW:"rendiconto finanziario",GUARANTEES_COMMITMENTS:"garanzie e impegni"};
  function render(parent, {data, view, node, button, fields, open}) {
    const nav = node("nav"); nav.setAttribute("aria-label", "Revisione del bilancio per area");
    for (const [key, label] of Object.entries(views)) {const b=button(label,()=>open(key));if(key===view)b.setAttribute("aria-current","page");nav.append(b);}
    nav.append(button("Rilievi del bilancio",()=>open("ISSUES_PANEL")),button("Prepara Excel di revisione",()=>open("AREA_WORKBOOK")));
    parent.append(nav);
    if (!view?.startsWith("AREA_") && !["OIC_CATALOGUE","QUALITATIVE_EVIDENCE"].includes(view)) return false;
    const review=data.review;
    parent.append(node("h2",views[view]|| (view==="AREA_SOURCE"?"Documento da controllare":"Excel di revisione")));
    if(data.workbook){
      const w=data.workbook;
      parent.append(node("p",`Documento della revisione ${w.revision_id}. Le modifiche al file non cambiano il fascicolo.`));
      const link=node("a","Scarica il documento Excel");
      const bytes=Uint8Array.from(atob(w.content_base64),c=>c.charCodeAt(0));
      const url=URL.createObjectURL(new Blob([bytes],{type:"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}));
      link.href=url;link.download=w.file_name;link.addEventListener("click",()=>setTimeout(()=>URL.revokeObjectURL(url),60000),{once:true});parent.append(link);return true;
    }
    if(view==="AREA_SOURCE"){
      parent.append(node("h3",review.document.file_name),node("p",review.excerpt||"Questo documento richiede un’estrazione qualificata. La sua presenza non prova che il contenuto sia stato esaminato.","source-excerpt"));
      if(review.excerpt){parent.lastChild.style.whiteSpace="pre-wrap";const prev=button("Brano precedente",()=>open(view,review.document.document_id,Math.max(0,review.offset-4000)));prev.disabled=!review.offset;const next=button("Brano successivo",()=>open(view,review.document.document_id,review.offset+4000));next.disabled=!review.has_more;parent.append(prev,next);}
      return true;
    }
    parent.append(node("p",`${states[review.status]||review.status} · Percorso ${review.profile==="STREAMLINED"?"snello":review.profile==="FULL"?"completo":"da definire"}`,"sub"));
    parent.append(node("p","Il catalogo contiene riferimenti e controlli professionali parziali. Le esclusioni richiedono motivazione; l’assenza di un conto non esclude una fattispecie. Il percorso snello raggruppa gli stessi obiettivi di revisione.","caption"));
    if(review.unassigned_accounts?.length)parent.append(node("p",`${review.unassigned_accounts.length} conti attendono l’assegnazione professionale a un’area.`,"notice"));
    const rows=review.records;
    for(const item of rows?.items||[]){
      const record=node("section",undefined,"record");
      if(view==="AREA_DASHBOARD"){
        record.append(node("h3",item.title),node("p",states[item.status]||item.status),node("p",item.reason),node("p",`${item.account_count} conti · ${item.open_controls} controlli da completare su ${item.control_count}`));
        if(item.missing_schedule_types.length)record.append(node("p",`Prospetti da acquisire: ${item.missing_schedule_types.map(s=>scheduleLabels[s]||s).join(", ")}`,"notice"));
        record.append(button("Apri carta di lavoro",()=>open("AREA_WORKPAPERS",item.area_id)),button("Esamina controlli",()=>open("AREA_CONTROLS",item.area_id)));
        for(const doc of item.documents)record.append(button(`Apri ${doc.file_name}`,()=>open("AREA_SOURCE",doc.document_id)));
      }else if(view==="OIC_CATALOGUE"){
        record.append(node("h3",`${item.id.replace("_"," ")} · ${item.title}`),node("p",states[item.status]||item.status),node("p",`Fonte: ${item.source_version}. Versione da valutare rispetto all’esercizio e al pacchetto OIC selezionato.`));
        const a=node("a","Consulta la fonte OIC");a.href=item.source_url;a.target="_blank";a.rel="noopener noreferrer";record.append(a);
      }else{
        const r=item.record||item;
        if(item.record_kind==="accounts")record.append(node("h3",`${r.account_code} · ${r.account_description}`),node("p",`Saldo: ${r.closing_signed} EUR · Precedente: ${r.prior_closing_signed??"non previsto"}`));
        else if(r.objective)record.append(node("h3",r.id.replace("OIC_","OIC ")),node("p",r.objective),node("p",states[r.status]||r.status),node("p",r.review?.payload?.reason||"Conclusione professionale da registrare nel fascicolo."));
        else if(r.quote){record.append(node("h3",r.flag.replaceAll("_"," ")),node("blockquote",r.quote),node("p",`${r.period.start} — ${r.period.end} · ${states[r.status]||r.status}`),button("Apri documento",()=>open("AREA_SOURCE",r.document_id)));}
        else if(r.file_name)record.append(node("h3",r.file_name),button("Apri documento",()=>open("AREA_SOURCE",r.document_id)));
        else record.append(fields(r));
      }
      parent.append(record);
    }
    if(!rows?.items?.length)parent.append(node("p","Nessun elemento in questa vista. Riprendi in chat il piano delle aree e la revisione delle proposte.","empty"));
    if(rows){const prev=button("Precedenti",()=>open(view,review.area_id,Math.max(0,rows.page.offset-30)));prev.disabled=!rows.page.offset;const next=button("Successivi",()=>open(view,review.area_id,rows.page.offset+30));next.disabled=!rows.page.has_more;parent.append(prev,node("span",`${rows.page.total} elementi`),next);}
    parent.append(button("Aggiorna dal fascicolo",()=>open(view,review.area_id,rows?.page.offset||0)),node("p","Le fonti reimportate come nuove versioni riaprono i controlli che ne dipendono. Le decisioni precedenti restano consultabili.","caption"));
    return true;
  }
  globalThis.VeraBilancioReview={render};
})();
