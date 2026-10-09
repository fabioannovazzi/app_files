"use strict";
/* Literal fields and receipt checks preserve decisions; they do not infer accounting meaning. */
globalThis.VeraOpenItemsIntake = Object.freeze({create(api) {
  const {node,button,call,say,confirmation}=api;
  const prefix="vera_workspace_open_items_intake_";
  const roles={open_items:"Elenco delle partite aperte",counterparty_open_items:"Elenco della controparte",ledger:"Mastrino",journal:"Giornale contabile",bank_statement:"Estratto conto bancario",payment_order:"Disposizione di pagamento",factoring_statement:"Prospetto factoring",compensation_support:"Documento di compensazione"};
  const languages=[["it","Italiano"],["en","English"],["fr","Français"],["de","Deutsch"],["es","Español"]];
  let context,timer,queue=Promise.resolve();const urls=new Set();
  const signed=p=>({work_ref:p.work_ref,revision:p.revision,review_ticket:p.review_ticket});
  const write=local=>({...signed(local.page),expected_draft_revision:local.stamp});
  function dispose(){clearTimeout(timer);context=null;for(const url of urls)URL.revokeObjectURL(url);urls.clear();}
  async function persist(){
    const local=context;if(!local?.editable)return queue;
    const fields=structuredClone(local.fields),serialized=JSON.stringify(fields);
    queue=queue.then(async()=>{
      if(local.saved===serialized)return;
      const saved=await call(prefix+"draft_save",{...write(local),fields});
      local.stamp=saved.draft_revision;local.saved=serialized;local.error=null;
      if(context===local&&JSON.stringify(local.fields)===serialized)api.setDirty(false);
      say("Scelte incomplete conservate. Il calcolo richiede una nuova conferma.");
    }).catch(error=>{local.error=error;api.setDirty(true);say("Scelte non conservate: "+error.message,true);});return queue;
  }
  async function flush(){clearTimeout(timer);await persist();if(context?.error)throw context.error;}
  function changed(local){local.submission=null;if(local.confirm)local.confirm.checked=false;api.setDirty(true);clearTimeout(timer);timer=setTimeout(persist,450);}
  function valueAt(fields,path){return path.reduce((value,key)=>value?.[key],fields);}
  function assign(local,path,value){
    if(!local.editable)return;
    let parent=local.fields;for(const key of path.slice(0,-1))parent=parent[key]??= {};
    parent[path.at(-1)]=value;changed(local);
  }
  function field(parent,local,path,label,{choices,kind="text",decode=value=>value,encode=value=>value}={}){
    const wrap=node("label",undefined,"field"),control=node(choices?"select":kind==="long"||kind==="lines"?"textarea":"input"),value=valueAt(local.fields,path);
    if(choices){const blank=node("option","Scegli…");blank.value="";control.append(blank);for(const [key,text] of choices){const option=node("option",text);option.value=key;control.append(option);}}
    if(control.tagName==="INPUT")control.type=kind==="date"?"date":"text";
    control.value=value===undefined?"":encode(kind==="lines"?value.join("\n"):String(value));
    control.setAttribute("aria-label",label);control.disabled=!local.editable;control.maxLength=path.length>1?1000:8000;
    wrap.append(node("span",label),control);parent.append(wrap);local.controls.push(control);
    control.addEventListener(choices?"change":"input",()=>{
      if(choices&&control.value===""){if(valueAt(local.fields,path)!==undefined){let target=local.fields;for(const key of path.slice(0,-1))target=target[key];delete target[path.at(-1)];changed(local);}return;}
      assign(local,path,kind==="lines"?control.value.split("\n").filter(value=>value!==""):decode(control.value));
    });return control;
  }
  function group(parent,title){const result=node("fieldset",undefined,"open-items-fields");result.append(node("legend",title));parent.append(result);return result;}
  function scopeFields(main,local){
    const scope=group(main,"Perimetro del confronto");
    for(const [key,label,kind] of [["scope_year","Anno del perimetro","text"],["cutoff_date","Data dell’elenco aperto","date"],["currency","Valuta del confronto","text"],["reviewer_ref","Riferimento dichiarato del revisore","text"],["reviewed_on","Data del riesame delle fonti","date"]])field(scope,local,[key],label,{kind});
    field(scope,local,["jurisdiction"],"Giurisdizione dichiarata",{choices:[["IT","Italia"],["CH-GE","Svizzera · Ginevra"]]});
    field(scope,local,["document_language"],"Lingua dei documenti",{choices:languages});field(scope,local,["language"],"Lingua degli elaborati",{choices:languages});
    main.append(node("p","Il riferimento del revisore è una dichiarazione locale. Non autentica una persona né approva gli esiti della riconciliazione.","caption"));
    const policy=group(main,"Criteri da riesaminare sulle evidenze");
    for(const [key,label] of [["post_cutoff_events_excluded","Escludere gli eventi successivi alla data dell’elenco"],["payment_orders_are_bank_evidence","Trattare una disposizione di pagamento come evidenza bancaria"],["factoring_pro_soluto_closes_item","Trattare il factoring pro soluto come chiusura della partita"],["compensation_requires_bank","Richiedere evidenza bancaria anche per una compensazione"]])field(policy,local,[key],label,{choices:[["true","Sì"],["false","No"]],decode:value=>value==="true"});
    field(main,local,["counterparty_keywords"],"Riferimenti letterali della controparte · uno per riga",{kind:"lines"});
    field(main,local,["factoring_operator_keywords"],"Riferimenti letterali dell’operatore factoring · uno per riga",{kind:"lines"});
    field(main,local,["title"],"Titolo degli elaborati");field(main,local,["narrative"],"Nota da conservare negli elaborati",{kind:"long"});
  }
  async function original(parent,local,row){
    const result=await call(prefix+"source",{...signed(local.page),input_id:row.id});
    const bytes=Uint8Array.from(atob(result.content),value=>value.charCodeAt(0));
    const hash=Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256",bytes)),byte=>byte.toString(16).padStart(2,"0")).join("");
    if(result.input_id!==row.id||hash!==result.sha256||bytes.byteLength!==result.byte_count)throw new Error("Il documento ricevuto non corrisponde alla sua ricevuta.");
    if(context!==local)return;
    const url=URL.createObjectURL(new Blob([bytes],{type:result.mime_type}));urls.add(url);
    parent.replaceChildren();const link=node("a",result.mime_type==="application/pdf"?"Apri il PDF originale":"Scarica il documento originale");
    link.href=url;link.target="_blank";link.rel="noopener";link.download=result.name;parent.append(link,node("p","Originale importato, con impronta verificata. Consultarlo non assegna un ruolo né qualifica la fonte.","caption"));
  }
  function sourceFields(parent,local,row){
    const section=node("details",undefined,"open-items-source");section.append(node("summary",row.title),node("p","Documento importato · "+row.kind,"caption"));parent.append(section);
    const preview=node("div",undefined,"open-items-original");section.append(button("Consulta questo originale",()=>original(preview,local,row)),preview);
    const base=["sources",row.id],selection=group(section,"Ruolo e formato riesaminati");
    field(selection,local,[...base,"role"],"Ruolo del documento · "+row.title,{choices:local.page.roles.map(value=>[value,roles[value]||value])});
    field(selection,local,[...base,"adapter_family"],"Formato supportato · "+row.title,{choices:local.page.adapters.map(value=>[value,value])});
    const perimeter=group(section,"Perimetro di questa fonte");
    for(const [key,label] of [["entity_ref","Riferimento dell’entità"],["party_ref","Riferimento della controparte"],["currency","Valuta della fonte"],["unit","Unità degli importi"],["direction_policy","Direzione dichiarata"],["allocation_policy","Relazione dichiarata fra partite ed evidenze"]])field(perimeter,local,[...base,"perimeter",key],label+" · "+row.title);
    const money=group(section,"Convenzioni monetarie della fonte");
    field(money,local,[...base,"money","decimal_separator"],"Separatore decimale · "+row.title,{choices:[[",","Virgola"],[".","Punto"]]});
    field(money,local,[...base,"money","thousands_separator"],"Separatore delle migliaia · "+row.title,{choices:[["none","Assente"],[".","Punto"],[",","Virgola"],[" ","Spazio"]],decode:value=>value==="none"?"":value,encode:value=>value===""?"none":value});
    field(money,local,[...base,"money","reported_unit"],"Unità monetaria riportata · "+row.title);
    field(money,local,[...base,"money","reported_increment"],"Incremento monetario dichiarato · "+row.title);
    section.append(node("p","Il produttore supporta importi esatti al centesimo: incremento 0.01. Precisioni diverse vengono segnalate senza arrotondarle per superare i controlli.","caption"));
    field(section,local,[...base,"date","order"],"Ordine delle date · "+row.title,{choices:[["day_first","Giorno prima del mese"],["month_first","Mese prima del giorno"]]});
  }
  function sources(main,local,offset=0){
    const holder=local.sources||node("section",undefined,"open-items-sources");local.sources=holder;holder.replaceChildren();if(!holder.parentElement)main.append(holder);
    holder.append(node("h2","Documenti da riesaminare"),node("p",`${local.items.length} documenti importati. Ogni fonte richiede scelte esplicite; il nome non decide il contenuto.`,"sub"),node("p","Il pannello apre originali fino a 4 MiB. Consulta i documenti più grandi nella cartella registrata di Studio Archive prima di dichiararne le convenzioni.","caption"));
    for(const row of local.items.slice(offset,offset+30))sourceFields(holder,local,row);
    const nav=node("div",undefined,"pagination");holder.append(nav);
    if(offset>0)nav.append(button("← Documenti precedenti",()=>sources(main,local,Math.max(0,offset-30))));
    if(offset+30<local.items.length)nav.append(button("Altri documenti →",()=>sources(main,local,offset+30)));
  }
  async function open(workRef){
    await flush();api.leaveDraft();const generation=api.enter();
    const page=await call(prefix+"setup",{work_ref:workRef}),items=[...page.items];let cursor=items.length,more=page.has_more;
    while(more){const next=await call(prefix+"setup",{work_ref:workRef,offset:cursor});if(next.revision!==page.revision||next.total!==page.total||next.draft.draft_revision!==page.draft.draft_revision||!next.items.length)throw new Error("I documenti o la bozza sono cambiati. Riapri la preparazione.");items.push(...next.items);cursor=items.length;more=next.has_more;}
    if(items.length!==page.total||new Set(items.map(row=>row.id)).size!==items.length)throw new Error("L’inventario dei documenti non è completo.");
    if(!api.isCurrent(generation))return;
    const {nav,main}=api.shell();nav.append(button("← Lavori dello studio",api.openWorks));
    main.append(node("p","Partite aperte","eyebrow"),node("h1","Prepara il confronto delle partite aperte"),node("p","Riesamina i documenti importati in Studio Archive, poi dichiara il perimetro e le convenzioni per ogni fonte.","intro"));
    const local={page,items,fields:structuredClone(page.draft.fields),stamp:page.draft.draft_revision,saved:JSON.stringify(page.draft.fields),editable:page.can_prepare&&!page.draft.stale,controls:[]};context=local;api.setDirty(false);
    if(page.status==="recovery_required")main.append(node("p","Ci sono output o un’operazione interrotta da recuperare nel workflow specialistico. Il pannello conserva le scelte e non ripete il calcolo.","notice"));
    else if(page.status==="prepared")main.append(node("p","Gli elaborati sono già conservati. Apri la revisione per leggere gli esiti e i rilievi; il lavoro resta in corso in Studio Archive.","notice"),button("Apri la revisione delle partite",()=>api.openReview(workRef)));
    else if(!page.can_prepare)main.append(node("p","Consultazione soltanto. Per preparare gli elaborati serve un lavoro avviato e autorità di revisore.","notice"));
    if(page.draft.stale)main.append(node("p","Il perimetro è cambiato. Confronta le scelte precedenti con i documenti correnti prima di scartare soltanto la bozza privata.","notice"));
    scopeFields(main,local);sources(main,local);
    const save=button("Conserva le scelte incomplete",flush);save.disabled=!local.editable;main.append(save);
    local.confirm=confirmation(main,"Ho riesaminato tutti i documenti, le convenzioni e i criteri. Prepara gli elaborati da rivedere");local.confirm.disabled=!local.editable;
    local.submit=button("Prepara gli elaborati delle partite",async()=>{
      if(!local.editable||!local.confirm.checked)throw new Error("Conferma nuovamente il riesame delle scelte e di tutte le fonti.");
      await flush();local.submission??=crypto.randomUUID();let result;
      try{result=await call(prefix+"prepare",{...write(local),human_reviewed:true,idempotency_key:local.submission});}
      catch(error){local.editable=false;local.submit.disabled=true;local.confirm.checked=false;local.confirm.disabled=true;save.disabled=true;for(const control of local.controls)control.disabled=true;throw new Error("Verifica lo stato salvato prima di riprovare: "+error.message);}
      local.editable=false;local.submit.disabled=true;local.confirm.checked=false;local.confirm.disabled=true;save.disabled=true;for(const control of local.controls)control.disabled=true;
      main.append(node("p",result.report_ready?"Gli output sono conservati; la decisione professionale e la chiusura del lavoro restano separate.":"Gli output e i controlli sono conservati. Restano rilievi o verifiche da completare nella revisione.","notice"),button("Apri la revisione delle partite",()=>api.openReview(workRef)));say("Elaborati conservati e assurance riletta. Apri la revisione.");
    },"primary");local.submit.disabled=!local.editable;main.append(local.submit);
    const clear=confirmation(main,"Scarta soltanto le mie scelte incomplete dopo il confronto con i documenti correnti"),discard=button("Scarta le scelte incomplete",async()=>{
      if(!clear.checked)throw new Error("Conferma lo scarto della sola bozza privata.");
      clearTimeout(timer);await queue;
      await call(prefix+"draft_clear",write(local));api.setDirty(false);dispose();await open(workRef);
    },"",false);clear.disabled=!page.can_discard;discard.disabled=!page.can_discard;main.append(discard);
    const data=node("section",undefined,"model-data-report");data.append(node("h2","Quali dati arrivano al modello"),node("p","Questi strumenti mostrano gli originali, le scelte incomplete e gli esiti nel pannello, senza inviarli come contesto al modello né avviare una chiamata al modello. Si applicano comunque il runtime e l’account Codex scelti dallo studio; questo non garantisce un trattamento soltanto locale. La revisione successiva può inviare alla chat l’elemento scelto esplicitamente con la richiesta di spiegazione; il suo perimetro viene mostrato in quella vista."));main.append(data);
  }
  return {open,flush,dispose,active:()=>Boolean(context),refresh:async()=>{const workRef=context?.page.work_ref;if(workRef)await open(workRef);}};
}});
