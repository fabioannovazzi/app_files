"use strict";
/* Typed literal edits preserve the producer's shapes; they never choose fiscal meaning. */
globalThis.VeraPatentBox = Object.freeze({create(api) {
  const {node,button,call,say,confirmation}=api;
  const labels={initialize:"Apertura",import_ledger:"CSV già mappato",inspect_ledger:"Selezione del registro",normalize_ledger:"Normalizzazione dei costi",propose:"Caso e controlli proposti",review:"Riesame locale",calculate:"Calcolo ed elaborati",prepare_professional_review:"Richiesta da firmare",accept_professional_review:"Verifica della firma e del mandato",verify_formalities:"Formalità documentali"};
  const words={case:"Caso",rules:"Regole proposte",controls:"Controlli",narratives:"Testi A/B",casebook:"Fatti e approfondimenti",normalization_digest:"Normalizzazione collegata",ips:"Beni immateriali",costs:"Costi",allocations:"Quote attribuite",evidence:"Registro delle evidenze",sources:"Fonti",periods:"Periodi",claim_period_id:"Periodo richiesto",ledger_control_total:"Totale contabile",book_amount:"Importo contabile",income_amount:"Base redditi",irap_amount:"Base IRAP",income_max:"Base redditi proposta",irap_max:"Base IRAP proposta",status:"Esito proposto",conclusion:"Conclusione e limiti",evidence_ids:"Evidenze citate",source_ids:"Fonti citate",section:"Sezione",text:"Testo",locator:"Pagina, riga o sezione",mappings:"Mappature",control_totals:"Totali delle fonti",fx_rates:"Cambi documentati",excluded_rows:"Righe escluse",non_data_rows:"Righe non contabili",duplicate_reviews:"Riesame dei duplicati",population_duplicate_review:"Riesame della popolazione",purpose:"Scopo",rationale:"Motivazione",account:"Conto",category:"Categoria proposta",currency:"Valuta",allocation_method:"Criterio di attribuzione",name:"Nome",description:"Descrizione",type:"Tipo dichiarato",value:"Valore",row_ref:"Riga della fonte",table_id:"Tabella della fonte",mapping_rationale:"Motivazione della mappatura",reason:"Motivo",reviewed_on:"Data del riesame",sources_checked_on:"Data di verifica delle fonti",enhancement_rate:"Maggiorazione proposta",premial_periods:"Periodi premiali",key:"Controllo",as_of:"Data del caso",demo:"Caso sintetico"};
  let context,timer,queue=Promise.resolve(); const urls=new Set();
  const authorPanel=globalThis.VeraPatentBoxAuthoring?.create({...api,openProducer:(workRef,operation)=>open(workRef,operation)});
  const scope=p=>({work_ref:p.work_ref,operation:p.operation,revision:p.revision,source_ref:p.source_ref});
  const signed=p=>({...scope(p),review_ticket:p.review_ticket});
  function dispose(){clearTimeout(timer);context=null;authorPanel?.dispose();for(const url of urls)URL.revokeObjectURL(url);urls.clear();}
  async function persist(){
    const local=context;if(!local?.editable)return queue;
    const fields=structuredClone(local.fields),serialized=JSON.stringify(fields);
    queue=queue.then(async()=>{
      if(local.saved===serialized)return;
      const saved=await call("vera_workspace_patent_box_draft_save",{...signed(local.page),expected_draft_revision:local.stamp,fields});
      local.saved=serialized;local.stamp=saved.draft_revision;local.error=null;
      if(context===local&&JSON.stringify(local.fields)===serialized)api.setDirty(false);
      say("Campi incompleti conservati. Nessuna decisione o calcolo eseguito.");
    }).catch(error=>{local.error=error;api.setDirty(true);say("Campi non conservati: "+error.message,true);});return queue;
  }
  async function flush(){clearTimeout(timer);await persist();await authorPanel?.flush();if(context?.error)throw context.error;}
  function changed(local){local.submission=null;if(local.confirm)local.confirm.checked=false;api.setDirty(true);clearTimeout(timer);timer=setTimeout(persist,450);}
  function valueAt(local,path){return path.reduce((value,key)=>value[key],local.fields);}
  function assign(local,path,value){const parent=path.slice(0,-1).reduce((item,key)=>item[key],local.fields);parent[path.at(-1)]=value;if(path.length===1&&path[0]==="digest"){local.previewDigest=null;if(local.confirm&&["review","calculate"].includes(local.page.operation))local.confirm.disabled=true;}changed(local);}
  function input(parent,local,path,label,{choices,kind="text",nullable=false,readonly=false}={}){
    const wrap=node("label",undefined,"field"),control=node(choices?"select":kind==="long"?"textarea":"input"),value=valueAt(local,path);
    if(choices)for(const [key,text] of choices){const option=node("option",text);option.value=key;control.append(option);}
    if(control.tagName==="INPUT")control.type=kind==="integer"?"number":kind==="date"?"date":"text";
    control.value=value===null||value===undefined?"":typeof value==="boolean"?String(value):String(value);
    control.setAttribute("aria-label",label);control.disabled=readonly||!local.editable;
    if(!choices)control.maxLength=kind==="long"?10000:4000;
    wrap.append(node("span",label),control);parent.append(wrap);
    control.addEventListener(choices?"change":"input",()=>{
      let next=control.value;
      if(nullable&&next==="")next=null;
      else if(kind==="integer"&&next!==""&&Number.isSafeInteger(Number(next)))next=Number(next);
      else if(kind==="boolean")next=next==="true"?true:next==="false"?false:null;
      assign(local,path,next);
    });return control;
  }
  function structured(parent,local,path,readonly=false){
    const value=valueAt(local,path),name=words[path.at(-1)]||String(path.at(-1));
    const frozen=readonly||path.join(".")==="proposal.case.case_id"||path.join(".")==="proposal.case.demo"||path.join(".")==="proposal.rules.demo"||path.join(".")==="proposal.case.evidence"||path.join(".")==="proposal.normalization_digest"||Boolean(local.fields.proposal?.normalization_digest)&&["proposal.case.costs","proposal.case.ledger_control_total"].includes(path.join("."));
    if(value!==null&&typeof value==="object"){
      const details=node("details",undefined,"patent-fields");details.append(node("summary",name+(Array.isArray(value)?" · "+value.length+" voci":"")));parent.append(details);
      for(const key of Object.keys(value))structured(details,local,[...path,key],frozen);return;
    }
    input(parent,local,path,name+" · "+path.join(" / "),{kind:typeof value==="boolean"?"boolean":typeof value==="number"?"integer":["text","conclusion","rationale","reason","description"].includes(path.at(-1))?"long":"text",nullable:value===null,readonly:frozen,choices:typeof value==="boolean"?[["","Da chiarire"],["true","Sì"],["false","No"]]:undefined});
  }
  function readable(parent,value,title="Contenuto completo"){
    const section=node("details",undefined,"patent-record");section.append(node("summary",title));parent.append(section);
    function render(target,item){
      if(item!==null&&typeof item==="object"){
        for(const [key,part] of Object.entries(item)){const group=node("section");group.append(node("h4",words[key]||key));target.append(group);render(group,part);}
      }else target.append(node("p",item===null?"Non indicato":String(item),"source-excerpt"));
    }render(section,value);return section;
  }
  const evidenceChoices=p=>[["","Scegli il documento"],...(p.session?.inputs||[]).map(row=>[row.evidence_id,row.description+" · "+row.evidence_id])];
  const digestChoices=p=>[["","Scegli la versione"],...p.proposals.map(row=>[row.digest,row.claim_period_id+" · "+row.digest])];
  function defaults(operation,page){
    if(operation==="initialize")return {as_of:"",demo:null};
    if(operation==="import_ledger")return {evidence_id:""};
    if(operation==="inspect_ledger")return {evidence_id:"",options:{format:"",sheet:null,header_row:null,first_row:null,last_row:null,delimiter:null,encoding:null,pdf_extraction:null}};
    if(operation==="review")return {digest:"",reviewer:"",confirmation_ref:"",synthetic:page.session?.demo??null};
    if(operation==="calculate")return {digest:""};
    if(operation==="prepare_professional_review")return {digest:"",source_scan_ref:"",action:"",previous_digest:null,reason:null};
    if(operation==="accept_professional_review")return {digest:"",request_digest:"",signature_ref:"",mandate_ref:"",mandate_signature_ref:""};
    if(operation==="verify_formalities")return {plan:{schema_version:"1.0",format:"",document_evidence_id:"",signature_evidence_id:null},trust_basis:null};
    return {};
  }
  async function read(page,file_ref){return call("vera_workspace_patent_box_read",{...scope(page),file_ref});}
  async function loadVersion(main,local,kind){
    const prefix=kind==="proposal"?"proposal_":"normalization_",candidates=Object.keys(local.page.files).filter(name=>name.startsWith(prefix)&&name.endsWith(".json")&&!name.includes("/"));
    let selected="";const wrapper=node("label",undefined,"field"),select=node("select");select.setAttribute("aria-label",kind==="proposal"?"Versione da usare per la modifica":"Normalizzazione da usare per la modifica");
    for(const name of ["",...candidates]){const option=node("option",name||"Scegli il record conservato");option.value=name;select.append(option);}select.disabled=!local.editable;select.addEventListener("change",()=>{selected=select.value;});wrapper.append(node("span","Parti da una versione conservata"),select);main.append(wrapper);
    main.append(node("p","Il contenuto viene copiato soltanto nei tuoi campi incompleti. La versione precedente e le sue decisioni restano conservate. Le righe nuove o mancanti vanno preparate con il workflow specialistico; il pannello non inventa una struttura o una valutazione.","caption"));
    const load=button("Copia questa versione nei campi",async()=>{
      if(!selected)throw new Error("Scegli una versione esatta.");
      const retained=JSON.parse((await read(local.page,selected)).content);
      if(kind==="proposal"){
        const proposal=structuredClone(retained);delete proposal.normalization_record;
        local.fields={proposal};
      }else local.fields={plan:structuredClone(retained.plan)};
      changed(local);await flush();await open(local.page.work_ref,local.page.operation);
    });load.disabled=!local.editable;main.append(load);
    if(local.fields[kind])structured(main,local,[kind]);
    else if(kind==="plan"&&local.fields.plan)structured(main,local,["plan"]);
    else main.append(node("p","Non è presente una proposta completa in bozza. Usa Preparazione con Vera per descrivere il lavoro e scegliere i documenti; la proposta completa verrà confrontata prima di caricarla nei campi.","notice"));
  }
  async function operationFields(main,local){
    const p=local.page,op=p.operation;
    if(op==="initialize"){
      input(main,local,["as_of"],"Data del caso",{kind:"date"});
      input(main,local,["demo"],"Natura effettiva del caso",{kind:"boolean",choices:[["","Scegli"],["false","Pratica reale"],["true","Esempio sintetico"]]});
    }else if(op==="import_ledger"||op==="inspect_ledger"){
      input(main,local,["evidence_id"],"Documento contabile selezionato",{choices:evidenceChoices(p)});
      if(op==="import_ledger")main.append(node("p","Questo passo legge soltanto un CSV con le colonne canoniche già mappate. Per un registro da interpretare scegli Selezione del registro e Normalizzazione dei costi.","notice"));
      else {
        input(main,local,["options","format"],"Formato dichiarato",{choices:[["","Scegli"],["CSV","CSV"],["XLSX","Excel"],["PDF","PDF con testo"]]});
        input(main,local,["options","sheet"],"Foglio Excel esatto",{nullable:true});
        for(const [key,label] of [["header_row","Riga intestazioni"],["first_row","Prima riga selezionata"],["last_row","Ultima riga selezionata"]])input(main,local,["options",key],label,{kind:"integer",nullable:true});
        input(main,local,["options","delimiter"],"Separatore CSV",{nullable:true,choices:[["","Non indicato"],[",","Virgola"],[";","Punto e virgola"],["\t","Tabulazione"]]});
        input(main,local,["options","encoding"],"Codifica CSV",{nullable:true,choices:[["","Non indicata"],["utf-8","UTF-8"],["utf-8-sig","UTF-8 con BOM"],["cp1252","Windows 1252"]]});
        if(local.fields.options.pdf_extraction)structured(main,local,["options","pdf_extraction"]);
        main.append(node("p","Indica un intervallo chiuso. Formule Excel non diventano importi; l’estrazione di un PDF richiede righe e passaggi citati preparati dal workflow specialistico. Nessun OCR viene installato.","caption"));
      }
    }else if(op==="normalize_ledger"||op==="propose")await loadVersion(main,local,op==="propose"?"proposal":"plan");
    else if(op==="review"||op==="calculate"){
      input(main,local,["digest"],"Versione esatta del caso",{choices:digestChoices(p)});
      main.append(button("Leggi caso e riesame completi",async()=>{
        const digest=local.fields.digest;if(!digest)throw new Error("Scegli una versione.");
        const record=JSON.parse((await read(p,"proposal_"+digest+".json")).content);
        const memo=await read(p,"review_"+digest+".md");
        local.confirm.checked=false;local.submission=null;
        local.preview.replaceChildren(node("h2","Versione scelta"),node("p",digest,"caption"),node("pre",memo.content,"source-excerpt"));readable(local.preview,record,"Caso, fonti, controlli e testi completi");
        local.previewDigest=digest;local.confirm.disabled=!local.editable;
      }));
      if(op==="review"){
        input(main,local,["reviewer"],"Nome dichiarato del revisore");input(main,local,["confirmation_ref"],"Riferimento effettivo della conferma");
        main.append(node("p",local.fields.synthetic===true?"Questo riesame resta un’accettazione sintetica, senza valore di decisione professionale reale.":"Il nome e il riferimento sono dichiarati localmente. Non costituiscono autenticazione professionale e non autorizzano un calcolo reale.","notice"));
      }
    }else if(op==="prepare_professional_review"){
      input(main,local,["digest"],"Versione esatta del caso",{choices:digestChoices(p)});
      input(main,local,["action"],"Decisione da sottoporre a firma",{choices:[["","Scegli"],["REVIEW_CONTROLS","Riesame di controlli e regole"],["APPROVE_DOSSIER","Approvazione degli elaborati esatti"],["REOPEN_CASE","Riapertura di una versione approvata"]]});
      const directories=[...new Set(Object.keys(p.files).filter(name=>name.includes("/")).map(name=>name.slice(0,name.lastIndexOf("/"))))];
      input(main,local,["source_scan_ref"],"Scansione delle fonti già conservata",{choices:[["","Scegli il percorso conservato"],...directories.map(name=>[name,name])]});
      input(main,local,["previous_digest"],"Versione precedente per la riapertura",{choices:digestChoices(p),nullable:true});input(main,local,["reason"],"Motivo effettivo della riapertura",{nullable:true,kind:"long"});
      main.append(node("p","Il produttore verifica popolazione, impronte e freschezza della scansione. Il pannello prepara la richiesta; la firma deve avvenire presso il servizio scelto dal professionista. Non crea fonti o approvazioni.","notice"));
    }else if(op==="accept_professional_review"){
      input(main,local,["digest"],"Versione esatta del caso",{choices:digestChoices(p)});
      const requests=Object.keys(p.files).filter(name=>/^professional_request_[a-f0-9]{64}\/request\.json$/.test(name)).map(name=>name.split("/")[0].slice("professional_request_".length));
      input(main,local,["request_digest"],"Richiesta effettivamente firmata",{choices:[["","Scegli"],...requests.map(value=>[value,value])]});
      for(const [key,label] of [["signature_ref","Firma CMS della richiesta"],["mandate_ref","Mandato firmato dello studio"],["mandate_signature_ref","Firma CMS del mandato"]])input(main,local,[key],label,{choices:[["","Scegli il file conservato"],...Object.keys(p.files).map(name=>[name,name])]});
      main.append(node("p","Il produttore usa la configurazione esterna dell’amministratore e verifica firme, catena, revoche e perimetro. Nessuna policy, chiave o firma viene creata per sbloccare il caso. L’importazione nativa dei file esterni selezionati resta da qualificare.","notice"));
    }else if(op==="verify_formalities"){
      input(main,local,["plan","format"],"Formato della prova crittografica",{choices:[["","Scegli"],...["CMS_DETACHED","CMS_ATTACHED","PDF","RFC3161_RESPONSE","RFC3161_TOKEN"].map(value=>[value,value])]});
      input(main,local,["plan","document_evidence_id"],"Documento esatto selezionato",{choices:evidenceChoices(p)});
      input(main,local,["plan","signature_evidence_id"],"Firma separata selezionata, se applicabile",{choices:evidenceChoices(p),nullable:true});input(main,local,["trust_basis"],"Base di fiducia effettivamente riesaminata",{nullable:true,kind:"long"});
      main.append(node("p","Questo controllo usa la configurazione di fiducia già scelta dall’amministratore. Firma qualificata, poteri, termini, conservazione e tutela sanzionatoria restano esiti distinti.","notice"));
    }
  }
  async function artifacts(main,page){
    const files=Object.keys(page.files);if(!files.length)return;
    const section=node("details",undefined,"patent-artifacts");section.append(node("summary","Elaborati conservati · "+files.length+" file"));main.append(section);
    for(const name of files){
      const row=node("div",undefined,"patent-artifact");row.append(node("span",name));section.append(row);
      if(/\.(json|md|csv|txt)$/.test(name))row.append(button("Leggi contenuto completo",async()=>{
        const record=await read(page,name),details=node("details");details.open=true;details.append(node("summary",name),node("pre",record.content,"source-excerpt"));row.append(details);
      }));
      else if(/\.(pdf|docx)$/.test(name))row.append(button(name.endsWith(".pdf")?"Prepara PDF da aprire o scaricare":"Prepara Word da scaricare",async()=>{
        const retained=await call("vera_workspace_patent_box_artifact",{...scope(page),file_ref:name});
        const binary=Uint8Array.from(atob(retained.content),char=>char.charCodeAt(0));
        const hash=Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256",binary)),byte=>byte.toString(16).padStart(2,"0")).join("");
        if(hash!==retained.sha256||binary.byteLength!==retained.byte_count)throw new Error("Gli elaborati ricevuti non corrispondono alle impronte conservate.");
        const url=URL.createObjectURL(new Blob([binary],{type:retained.mime_type}));urls.add(url);
        const link=node("a",name.endsWith(".pdf")?"Apri la bozza PDF":"Scarica la bozza Word");link.href=url;link.download=name.split("/").at(-1);link.target="_blank";link.rel="noopener";row.append(link,node("p","Bozza conservata con impronta verificata. Firma e approvazione professionale restano separate.","caption"));
      }));
    }
  }
  async function open(workRef,operation="initialize"){
    await authorPanel?.flush();authorPanel?.dispose();
    api.leaveDraft();const generation=api.enter();
    const page=await call("vera_workspace_patent_box_setup",{work_ref:workRef,operation});if(!api.isCurrent(generation))return;
    const {nav,main}=api.shell();nav.append(button("← Lavori dello studio",api.openWorks));
    for(const [value,label] of Object.entries(labels))nav.append(button(label,()=>open(workRef,value)));
    if(authorPanel)nav.append(button("Preparazione con Vera",async()=>{await flush();dispose();await authorPanel.open(workRef);}));
    main.append(node("p","Patent Box","eyebrow"),node("h1",labels[operation]),node("p",page.label,"intro"));
    main.append(node("p","Preparazione in sviluppo. Il calcolo reale richiede fonti e regole riesaminate e una decisione firmata con mandato dello studio. I documenti prodotti restano bozze da rivedere.","notice"));
    const local={page,fields:{...defaults(operation,page),...structuredClone(page.fields)},stamp:page.draft_revision,saved:JSON.stringify(page.fields),editable:page.can_write&&!page.draft_stale};context=local;api.setDirty(false);
    readable(main,page.session?.inputs||page.selected_sources,"Documenti esatti di questo lavoro");
    if(!page.can_write)main.append(node("p",page.recovery_required?"Un’operazione richiede recupero ordinario. Le scritture e la chiusura restano bloccate.":"Consultazione soltanto: serve un lavoro in corso e autorità di revisore.","notice"));
    if(page.draft_stale){
      main.append(node("p","Il perimetro è cambiato. Confronta i campi precedenti con fonti e versioni correnti prima di scartare soltanto la bozza privata.","notice"));readable(main,page.fields,"Campi precedenti da confrontare");
      const clear=confirmation(main,"Scarta soltanto questi campi incompleti dopo il confronto con il perimetro corrente"),reset=button("Scarta la bozza privata",async()=>{if(!clear.checked)throw new Error("Conferma lo scarto dei soli campi privati.");await call("vera_workspace_patent_box_draft_clear",{...signed(page),expected_draft_revision:local.stamp,confirmed:true});api.setDirty(false);await open(workRef,operation);});clear.disabled=reset.disabled=!page.can_write;main.append(reset);
    }else {
      local.preview=node("section",undefined,"patent-preview");
      await operationFields(main,local);main.append(local.preview);
      local.confirm=confirmation(main,"Ho riesaminato questa versione e questi campi completi. Confermo soltanto l’operazione scelta, mantenendo aperti gli esiti professionali distinti");local.confirm.disabled=!local.editable||["review","calculate"].includes(operation);
      const save=button("Conserva campi incompleti",flush),execute=button("Esegui e conserva questo passaggio",async()=>{
        await flush();if(!local.confirm.checked)throw new Error("Riesamina e conferma nuovamente l’operazione esatta.");
        if(["review","calculate"].includes(operation)&&local.previewDigest!==local.fields.digest)throw new Error("Leggi il caso e il riesame completi della versione scelta prima di confermare.");
        local.submission||={...signed(page),expected_draft_revision:local.stamp,fields:structuredClone(local.fields),confirmed:true,idempotency_key:crypto.randomUUID()};
        const result=await call("vera_workspace_patent_box_execute",local.submission);
        if(result.status==="refused"){local.confirm.checked=false;local.submission=null;main.append(node("p",result.error,"notice"));say("Il produttore ha rifiutato il passaggio; i file precedenti sono conservati.",true);return;}
        api.setDirty(false);await open(workRef,operation);say("Passaggio conservato con la sua ricevuta. Nessuna accettazione professionale finale o chiusura del lavoro attestata.");
      },"primary");save.disabled=execute.disabled=!local.editable;main.append(save,execute);
    }
    await artifacts(main,page);
    main.append(node("h2","Quali dati arrivano al modello"),node("p","Questi controlli leggono documenti ed elaborati del run selezionato e conservano campi e ricevute sul computer. Le route di esecuzione restano riservate all’app. Il separato mandato di Preparazione con Vera autorizza contesto, record e originali selezionati per la sessione del modello; le ricevute distinguono testo restituito e identità dei binari. Letture ulteriori dell’host e telemetria del provider richiedono evidenza distinta. I documenti, le celle, i fatti, i costi, le fonti e i testi effettivamente letti possono entrare nel contesto del modello, senza anonimizzazione automatica o promessa di trattamento esclusivamente locale.","caption"));
  }
  return Object.freeze({open,flush,dispose,refresh:async()=>{if(authorPanel?.active())return authorPanel.refresh();if(context){const {work_ref,operation}=context.page;await flush();await open(work_ref,operation);}},active:()=>Boolean(context)||Boolean(authorPanel?.active())});
}});
