"use strict";
// One Archive renderer, shared by all three products. Adapters own data access.
globalThis.StudioArchiveUI = function ({node, button, root, call, request, say,
  getHost, getCatalogue, loadCatalogue, renderCatalogue, archiveFormShell,
  showReviewRoute, product}) {
  function archiveLink(label, action) { return button(label, action, "archive-link"); }
  function shell() {
    root.replaceChildren();
    const wrapper=node("div",undefined,"shell"), rail=node("aside",undefined,"rail");
    rail.append(node("p","Archivio dello studio","eyebrow"),node("h2","Lavori dello studio"));
    const nav=node("nav");nav.setAttribute("aria-label","Navigazione dei lavori");rail.append(nav);
    const main=node("main",undefined,"main");wrapper.append(rail,main);root.append(wrapper);return {nav,main};
  }
  function primaryDocument(version) {
    return version.formats.find(file => file.format === version.primary_format) || version.formats[0];
  }
  function issuedDate(version) {
    const issued = new Date(version.issued_at);
    return Number.isNaN(issued.getTime()) ? version.issued_at : issued.toLocaleDateString("it-IT", {dateStyle:"medium"});
  }
  async function openIncaricoDocument(selected, reference, version) {
    const selection = getCatalogue();
    const document = await call("vera_incarico_document", {...selected,reference});
    if (getCatalogue() !== selection) return;
    const main = archiveFormShell(document.name, renderCatalogue, "← Torna all’incarico");
    if (document.preview !== null) main.append(node("pre", document.preview, "document-preview"));
    if (getHost().hostCapabilities?.experimental?.["openai/files"]) {
      const result = await request("openai/files/open", {path:document.path});
      if (result?.isError) throw new Error("Non è stato possibile aprire il documento salvato.");
    } else {
      main.append(node("p", document.path, "archive-location"));
      if (document.preview === null) main.append(node("p", "Questo host non apre i file locali. Il documento è disponibile nel percorso indicato.", "caption"));
    }
    const companions = version?.formats.filter(file => JSON.stringify(file.reference) !== JSON.stringify(reference)) || [];
    if (companions.length) {
      const files = node("section", undefined, "incarico-documents"); files.append(node("h2", "Altri file di questa versione"));
      for (const file of companions) {
        const link = archiveLink(file.name, () => openIncaricoDocument(selected, file.reference, version));
        link.disabled = !file.available; files.append(link);
      }
      main.append(files);
    }
  }
  function renderIncarico(parent, saved) {
    const selected = {client_id:saved.client_id, engagement_id:saved.engagement_id};
    if (saved.purpose) parent.append(node("p", saved.purpose, "sub"));
    if (saved.legacy_assignments?.length) {
      const mapped=node("section"); mapped.append(node("h2", "Incarichi"));
      for (const item of saved.legacy_assignments) mapped.append(archiveLink(item.label, () => loadCatalogue({client_id:saved.client_id, engagement_id:item.engagement_id})));
      parent.append(mapped);
    }
    if (saved.historical_assignments?.length) {
      const history=node("details"); history.append(node("summary", "Attività precedenti"));
      for (const item of saved.historical_assignments) history.append(archiveLink(item.label, () => loadCatalogue({client_id:saved.client_id, engagement_id:item.engagement_id, view:"history"})));
      parent.append(history);
    }
    const chats=node("section", undefined, "incarico-conversations"); chats.append(node("h2", "Conversazioni"));
    for (const conversation of saved.conversations) {
      const row=node("div", undefined, "archive-document");
      const title=conversation.title === "Chat di origine" ? "Vai alla chat" : conversation.title;
      if (conversation.url) row.append(archiveLink(title, async () => {
        try {
          const result=await request("ui/open-link", {url:conversation.url});
          if (result?.isError) throw new Error("Chat unavailable");
        } catch {
          say(`Questa chat non è accessibile. I documenti sono conservati. Puoi chiedere a ${product} in Codex di riprendere questo incarico.`);
        }
      }));
      else row.append(node("span", title), node("p", "Collegamento alla chat non disponibile.", "caption"));
      chats.append(row);
    }
    if (!saved.conversations.length) chats.append(node("p", "Nessuna conversazione associata.", "caption"));
    parent.append(chats);
    const documents=node("section", undefined, "incarico-results incarico-documents"); documents.append(node("h2", "Documenti"));
    function documentRow(parent, label, reference, caption, available=true, version) {
      const row=node("div", undefined, "archive-document");
      const open=archiveLink(label, () => openIncaricoDocument(selected, reference, version)); open.disabled=!available; row.append(open);
      if (caption) row.append(node("p", caption, "caption"));
      if (!available) row.append(node("p", "Il file non è disponibile. Il riferimento alla versione è conservato.", "notice"));
      parent.append(row); return row;
    }
    for (const item of saved.results) documentRow(documents, item.label, item.reference, "", item.available);
    for (const entry of saved.deliverables || []) {
      const latest=entry.versions.at(-1), file=primaryDocument(latest);
      const row=documentRow(documents, latest.label, file.reference, `Revisione ${latest.revision} · ${issuedDate(latest)}`, file.available, latest);
      if (entry.versions.length>1) {
        const history=node("details"); history.append(node("summary", "Storico"));
        for (const version of [...entry.versions].reverse().slice(1)) {
          const prior=primaryDocument(version);
          documentRow(history, version.label, prior.reference, `Revisione ${version.revision} · ${issuedDate(version)}`, prior.available, version);
        }
        row.append(history);
      }
    }
    if (saved.deliverable_issues?.length) documents.append(node("p", "Alcuni risultati richiedono verifica. I riferimenti restano conservati.", "notice"));
    const sources=node("div"); documents.append(sources); parent.append(documents);
    async function draw(page) {
      sources.replaceChildren();
      for (const item of page.documents) {
        const row=documentRow(sources, item.name, item.reference, "");
        if (item.origin) row.append(archiveLink(`Da: ${item.origin.label}`, () => loadCatalogue({client_id:item.origin.client_id, engagement_id:item.origin.engagement_id})));
      }
      if (!page.documents.length && !saved.results.length && !saved.deliverables?.length) sources.append(node("p", "Nessun documento salvato.", "caption"));
      if (page.document_issues.length) sources.append(node("p", "Alcuni documenti richiedono verifica. Gli altri restano disponibili.", "notice"));
      if (page.has_more || page.offset) {
        const previous=button("Precedenti", async () => draw(await call("vera_incarico_read", {...selected, offset:Math.max(0,page.offset-30)})));
        const next=button("Successivi", async () => draw(await call("vera_incarico_read", {...selected, offset:page.offset+30})));
        previous.disabled=!page.offset; next.disabled=!page.has_more; sources.append(previous,next);
      }
    }
    draw(saved);
    if (saved.work_links?.length) {
      const work=node("section", undefined, "incarico-work"); work.append(node("h2", "Lavori salvati"));
      for (const link of saved.work_links) {
        const row=node("div", undefined, "archive-document"); row.append(archiveLink(link.label, async () => {
          const route=await call("vera_incarico_open_work", {...selected, workflow_id:link.workflow_id, work_ref:link.work_ref});
          await showReviewRoute(route);
        })); work.append(row);
      }
      parent.append(work);
    }
  }
  function archiveDocumentSearch(parent, listing) {
    const scope = getCatalogue().client_id ? {client_id:getCatalogue().client_id} : {all_clients:true};
    const area=node("section",undefined,"archive-search"), label=node("label",undefined,"search"), input=node("input");
    input.type="search";
    label.append(node("span", getCatalogue().client_id ? "Cerca nei documenti di " + getCatalogue().client_label : "Cerca nei documenti dell’archivio"),input);
    const results=node("div"); results.setAttribute("aria-live","polite");
    area.append(label,results);parent.append(area);
    let timer, generation=0;
    const current = id => id===generation && area.isConnected;
    function highlighted(text, term) {
      const paragraph=node("p");paragraph.style.whiteSpace="pre-wrap";
      const content=String(text).replaceAll("[[", "").replaceAll("]]", "");
      const lower=content.toLocaleLowerCase(), needle=term.toLocaleLowerCase();let start=0,index;
      while(needle && (index=lower.indexOf(needle,start))>=0){paragraph.append(document.createTextNode(content.slice(start,index)),node("mark",content.slice(index,index+needle.length)));start=index+needle.length;}
      paragraph.append(document.createTextNode(content.slice(start)));return paragraph;
    }
    async function perform(id, term) {
      try {
        const found=await call("vera_workspace_archive_search",{...scope,query:term});
        if(!current(id))return;
        results.replaceChildren(node("h2","Risultati nei documenti"));
        if(!found.results.length)results.append(node("p","Nessun documento trovato.","empty"));
        if(found.results.length===20)results.append(node("p","Primi 20 documenti. Aggiungi parole per restringere la ricerca.","caption"));
        if(found.scan_issue_count || found.document_issue_count || found.index_requires_refresh)results.append(node("p","La ricerca copre i documenti già indicizzati. Alcune fonti richiedono verifica o aggiornamento.","notice"));
        for(const hit of found.results){
          const row=node("article",undefined,"work-row"), detail=node("div");
          row.append(node("p",hit.client_label,"eyebrow"),node("h3",hit.title),node("p",hit.locator_kind==="page" ? "Pagina " + hit.locator_value : hit.locator_value,"caption"),highlighted(hit.snippet,term));
          row.append(button("Apri passaggio",async()=>{
            detail.replaceChildren(node("p","Verifica del documento…"));
            try{
              const opened=await call("vera_workspace_archive_source",{...scope,query:term,source_id:hit.source_id});
              if(!current(id))return;
              if(opened.source_verified!==true)throw new Error("Il documento non è stato verificato.");
              detail.replaceChildren(node("p","Documento verificato","caption"));
              for(const fragment of opened.fragments){
                detail.append(node("h4",fragment.locator_kind==="page" ? "Pagina " + fragment.locator_value : fragment.locator_value),highlighted(fragment.text,term));
              }
              for(const limitation of opened.limitations||[])detail.append(node("p",limitation,"notice"));
              detail.tabIndex=-1;detail.focus();
            }catch(error){if(current(id))detail.replaceChildren(node("p",error.message,"notice"));}
          }),detail);results.append(row);
        }
      }catch(error){if(current(id))results.replaceChildren(node("p","Ricerca non disponibile: " + error.message,"notice"));}
    }
    input.addEventListener("input",()=>{
      clearTimeout(timer);const id=++generation,term=input.value.trim();
      listing.hidden=Boolean(term);results.replaceChildren();
      if(!term)return;
      results.append(node("p","Ricerca nei documenti…"));
      timer=setTimeout(()=>{if(current(id))perform(id,term);},300);
    });
  }

  function directory(view) {
    const catalogue=getCatalogue(), {nav,main}=view || shell();
    main.append(node("p",catalogue.client_label || product,"eyebrow"),node("h1",catalogue.engagement_label || catalogue.client_label || "Clienti e progetti"));
    async function chooseArchive() {
      say("Scegli la cartella nella finestra del sistema operativo.");
      const result=await call("vera_workspace_archive_setup",{confirmed:true});
      if(result.setup_status==="cancelled"){say("Scelta annullata.");return;}
      await loadCatalogue();
    }
    if(catalogue.archive_location && catalogue.level==="clients")main.append(node("p",catalogue.archive_location,"archive-location"));
    if(!catalogue.configured){main.append(node("p","Scegli la cartella da usare come Archivio dello studio.","sub"),button("Scegli cartella dello studio",chooseArchive,"primary"));return;}
    if(catalogue.level==="clients"){
      const settings=node("details",undefined,"archive-settings");settings.append(node("summary","Cartella dell’archivio"),button("Cambia cartella",chooseArchive));nav.append(settings);
    } else nav.append(button(catalogue.engagement_id?"← Incarichi":"← Clienti",()=>loadCatalogue(catalogue.engagement_id?{client_id:catalogue.client_id}:{})));
    if(catalogue.collection_issues?.length)main.append(node("p","L’elenco dei lavori è incompleto: una parte dell’archivio non è leggibile. I record conservati restano invariati.","notice"));
    if(catalogue.incarico)renderIncarico(main,catalogue.incarico);
    const list=node("div",undefined,"works");archiveDocumentSearch(main,list);main.append(list);
    if(!catalogue.incarico){
      const rows=catalogue.level === "clients" ? (catalogue.clients || []) : (catalogue.engagements || []);
      for(const item of rows){
        const row=node("section",undefined,"work-row"), title=item.display_name || item.label;
        const client=catalogue.level==="clients";
        if(client && (!item.client_id || item.registration_status!=="registered"))row.append(node("h2",title),node("p","Cartella non registrata o identità non disponibile. I file sono conservati; verifica la registrazione nella chat.","caption"));
        else if(item.status==="blocked")row.append(node("h2",title),node("p","Incarico non disponibile. I documenti e i registri originali sono conservati.","caption"));
        else row.append(archiveLink(title,()=>loadCatalogue(client?{client_id:item.client_id}:{client_id:catalogue.client_id,engagement_id:item.engagement_id})));
        list.append(row);
      }
      if(!rows.length)list.append(node("p",catalogue.level==="clients"?"Nessun cliente presente nella cartella configurata.":"Nessun incarico in questo progetto","empty"));
      if(catalogue.offset || catalogue.has_more){
        const group=node("div",undefined,"pagination"), scope=catalogue.client_id?{client_id:catalogue.client_id}:{};
        const previous=button("Precedenti",()=>loadCatalogue({...scope,offset:Math.max(0,catalogue.offset-30)})), next=button("Successivi",()=>loadCatalogue({...scope,offset:catalogue.offset+30}));
        previous.disabled=!catalogue.offset;next.disabled=!catalogue.has_more;
        group.append(previous,node("span",`${catalogue.offset+1}–${Math.min(catalogue.offset+30,catalogue.total)} di ${catalogue.total}`),next);main.append(group);
      }
    }
  }
  return {shell, directory, renderIncarico, archiveDocumentSearch, openIncaricoDocument};
};
