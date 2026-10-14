"use strict";
(() => {
  function create(api) {
    let current, proposal, key, activeMain;
    function changed(){key=undefined;api.setDirty(true);for(const box of activeMain?.querySelectorAll("input[type=checkbox]")||[])box.checked=false;}
    const {node,button,call,say,shell,leaveDraft} = api;
    function control(parent, label, value, onChange, type="text", choices) {
      const wrap=node("label",undefined,"field"), input=node(choices?"select":type==="textarea"?"textarea":"input");
      if(choices) for(const [value,text] of choices) {const option=node("option",text);option.value=value;input.append(option);}
      else if(type!=="textarea") input.type=type;
      input.value=value??"";input.maxLength=10000;wrap.append(node("span",label),input);parent.append(wrap);
      input.addEventListener(choices?"change":"input",()=>{onChange(input.value);changed();});
      return input;
    }
    function confirmation(parent) {
      const label=node("label",undefined,"choice"), box=node("input");box.type="checkbox";
      label.append(box,node("span","Ho verificato il contenuto e le fonti pertinenti; confermo questa operazione."));parent.append(label);return box;
    }
    function scope(){return {work_ref:current.work_ref,revision:current.revision,review_ticket:current.review_ticket,human_reviewed:true,idempotency_key:key||(key="practice-"+crypto.randomUUID())};}
    async function discuss(itemId,parent) {
      if(api.isDirty())throw new Error("Conserva la revisione prima di discuterla con Vera.");
      const openPreview=itemId.endsWith(".docx")?" Poi apri il percorso dell’esempio Word restituito nello strumento file/Word del tuo host e mostra il documento, senza modificarlo.":"";
      const text=`Usa vera_workspace_practice_context con work_ref ${current.work_ref}, item_id ${itemId} e revision ${current.revision} prima di discutere questa selezione. Leggi solo la selezione richiesta; non inferire approvazione o termini legali.${openPreview}`;
      if(api.host().hostCapabilities?.message?.text) {
        const result=await api.request("ui/message",{role:"user",content:[{type:"text",text}]});
        if(result?.isError)throw new Error("La chat non ha confermato la ricezione; verifica prima di riprovare.");
        say("Richiesta della selezione consegnata alla chat corrente.");
      } else {const copy=node("textarea",undefined,"request");copy.readOnly=true;copy.value=text;parent.append(copy);say("Copia la richiesta nella chat per discutere questa selezione.");}
    }
    async function catalogue() {
      leaveDraft();const generation=api.enter();const data=await call("vera_workspace_practice_catalogue");if(!api.isCurrent(generation))return;
      const {nav,main}=shell();current=null;nav.append(button("← Lavori dello studio",api.openWorks));main.append(node("h1","Pratiche e formato documenti"));
      for(const row of data.practices){const section=node("section",undefined,"work-row");section.append(node("p",row.kind==="tax"?"Contenzioso tributario":"Formato dei documenti","eyebrow"),node("h2",row.label),button("Apri revisione",()=>open(row.work_ref)));main.append(section);}
      if(!data.practices.length)main.append(node("p","Non ci sono pratiche o formati collegati a questo servizio. Prepara il lavoro nel percorso della funzione e collega il suo esatto registro locale.","notice"));
    }
    async function open(reference) {
      leaveDraft();const generation=api.enter();const data=await call("vera_workspace_practice_read",{work_ref:reference});if(!api.isCurrent(generation))return;
      const layout=shell();current=data;proposal=structuredClone(data.kind==="tax"?data.data.matter:data.data.proposal.profile.document.docx||{});key=undefined;
      draw(layout);say("Versione salvata e integrità rilette dal registro.");
    }
    function draw({nav,main}) {
      activeMain=main;
      nav.append(button("← Pratiche e formati",catalogue),button("Scarta modifiche e rileggi",()=>{api.setDirty(false);return open(current.work_ref);}));
      main.append(node("h1",current.label),node("p",current.kind==="tax"?"Cronologia, termini dichiarati, riscontri e stato della pratica. Il registro non calcola termini legali e non prova notifica, deposito o pagamento.":"Impostazioni del documento e due esempi Word generati dal medesimo formato. L’adozione del profilo richiede una conferma separata.","caption"));
      if(current.kind==="tax")tax(main);else format(main);
    }
    function citations(parent,event) {
      const list=node("div");parent.append(list);
      function rows(){list.replaceChildren();for(const [index,cite]of event.citations.entries()){const row=node("section",undefined,"evidence-group");row.append(node("p",cite.source_id+" · "+cite.anchor),node("pre",cite.quote,"source-excerpt"),button("Rimuovi questo riscontro",()=>{event.citations.splice(index,1);changed();rows();}));list.append(row);}}
      rows();let sourceId="",anchor="",quote="";
      const sources=current.data.sources;
      control(parent,"Fonte",sourceId,value=>{sourceId=value;anchor="";unitInput.replaceChildren();const empty=node("option","Scegli una pagina o sezione");empty.value="";unitInput.append(empty);for(const unit of sources.find(source=>source.id===sourceId)?.units||[]){const option=node("option",unit.anchor);option.value=unit.anchor;unitInput.append(option);}},"text",[["","Scegli una fonte"],...sources.map(source=>[source.id,source.original_name||source.file_name||source.id])]);
      const unitInput=control(parent,"Pagina o sezione",anchor,value=>{anchor=value;const text=sources.find(source=>source.id===sourceId)?.units.find(unit=>unit.anchor===anchor)?.text||"";preview.textContent=text;},"text",[["","Scegli prima la fonte"]]);
      const preview=node("pre",undefined,"source-excerpt");parent.append(preview);
      control(parent,"Citazione letterale da conservare",quote,value=>{quote=value;},"textarea");
      parent.append(button("Aggiungi il riscontro scelto",()=>{if(!sourceId||!anchor||!quote.trim())throw new Error("Scegli fonte, sezione e citazione letterale.");event.citations.push({source_id:sourceId,anchor,quote});changed();rows();}));
    }
    function tax(main) {
      proposal.calendar??=[];const events=node("section");main.append(events);
      function rows(){events.replaceChildren();for(const event of proposal.calendar){const section=node("section",undefined,"evidence-group");section.append(node("h2",event.event||"Nuovo evento"));
        control(section,"Evento",event.event,value=>event.event=value);
        control(section,"Data dell’evento",event.event_date,value=>event.event_date=value,"date");
        control(section,"Termine indicato",event.due_date,value=>event.due_date=value,"date");
        control(section,"Stato del termine",event.status,value=>event.status=value,"text",[["unknown","Non determinato"],["proposed","Proposto · da rivedere"],["conditional","Condizionale"],["reviewed","Riesaminato nel registro"]]);
        control(section,"Base e condizioni del calcolo",event.basis,value=>event.basis=value,"textarea");
        control(section,"Revisore dichiarato",event.reviewer_ref,value=>event.reviewer_ref=value);
        citations(section,event);section.append(button("Discuti questo evento con Vera",()=>discuss("calendar:"+event.id,section)));events.append(section);}
      }
      rows();main.append(button("Aggiungi evento o termine",()=>{proposal.calendar.push({id:"event-"+crypto.randomUUID(),event:"",event_date:"",due_date:"",status:"unknown",basis:"",reviewer_ref:"",citations:[]});changed();rows();}));
      main.append(node("h2","Domande e passaggi della pratica"));
      for(const [kind,items]of [["questions",proposal.questions],["stages",proposal.stages]])for(const item of items){const section=node("section",undefined,"work-row");section.append(node("h3",item.question||item.label),node("p",item.answer||item.note||"Da completare"),node("p",item.status,"caption"),button("Discuti questo elemento",()=>discuss(kind+":"+item.id,section)));for(const output of item.outputs||[])section.append(node("p",output,"caption"));main.append(section);}
      const confirm=confirmation(main);const save=button("Conserva la revisione nel registro",async()=>{if(!confirm.checked)throw new Error("Conferma dopo aver verificato i riscontri.");const result=await call("vera_workspace_practice_tax_save",{...scope(),review:proposal});api.setDirty(false);const layout=shell();current=result;key=undefined;proposal=structuredClone(result.data.matter);draw(layout);say("Revisione conservata dal motore, con versione precedente e riscontri. Nessun atto è stato notificato o depositato.");},"primary");save.disabled=!current.can_write;main.append(save);
    }
    function format(main) {
      const settings={};let accept,approve;const fields=node("section");main.append(fields,node("h2","Esempi Word da esaminare"));
      for(const [key,label,type]of [["font_family","Carattere del testo","text"],["body_font_size_pt","Dimensione testo · punti","number"],["line_spacing_pt","Interlinea · punti","number"],["paragraph_after_pt","Spazio dopo il paragrafo · punti","number"],["heading_1_size_pt","Titolo principale · punti","number"],["heading_2_size_pt","Titolo secondario · punti","number"],["header_text","Testo dell’intestazione","text"],["footer_text","Testo del piè di pagina","text"]]) {
        const input=control(fields,label,proposal[key],value=>{if(value==="")delete settings[key];else settings[key]=type==="number"?Number(value):value;if(accept)accept.disabled=true;if(approve)approve.checked=false;},type);input.placeholder="Mantieni l’impostazione del profilo";
      }
      for(const preview of current.data.previews){const section=node("section",undefined,"work-row");section.append(node("h3",preview.path==="preview-short.docx"?"Esempio breve":"Esempio lungo · tabelle e cambio pagina"),button("Apri questo esempio nella chat",()=>discuss(preview.path,section)));main.append(section);}
      const prepare=confirmation(fields);const generate=button("Genera due nuovi esempi",async()=>{if(!prepare.checked||!Object.keys(settings).length)throw new Error("Modifica almeno un’impostazione e conferma la preparazione.");const result=await call("vera_workspace_practice_format_prepare",{...scope(),settings});api.setDirty(false);const layout=shell();current=result;key=undefined;proposal=structuredClone(result.data.proposal.profile.document.docx||{});draw(layout);say("Nuovi esempi generati. Il formato dello studio non è stato adottato.");},"primary");generate.disabled=!current.can_write;fields.append(generate);
      const adoption=node("section",undefined,"evidence-group");main.append(adoption);let reviewer="";control(adoption,"Revisore del formato",reviewer,value=>reviewer=value);approve=confirmation(adoption);
      const already=current.data.current_profile?.approved_from?.contribution_digest===current.data.proposal.review_digest;
      adoption.append(node("p",already?"Questo formato risulta adottato nel profilo corrente.":current.data.base_current?"Esamina entrambi gli esempi prima di adottare il formato.":"Il profilo corrente è cambiato: prepara nuovi esempi prima dell’adozione.","caption"));
      accept=button("Adotta il formato esaminato",async()=>{if(!approve.checked||!reviewer.trim())throw new Error("Indica il revisore e conferma entrambi gli esempi.");const result=await call("vera_workspace_practice_format_approve",{...scope(),reviewer});api.setDirty(false);const layout=shell();current=result;key=undefined;proposal=structuredClone(result.data.proposal.profile.document.docx||{});draw(layout);say("Formato adottato dal writer dello studio; gli esempi e la revisione sono conservati.");},"primary");accept.disabled=!current.can_write||already||!current.data.base_current;adoption.append(accept);
    }
    return {catalogue,active:()=>Boolean(current),refresh:()=>open(current.work_ref),dispose(){current=null;proposal=null;key=undefined;activeMain=null;}};
  }
  globalThis.VeraPracticeReviews={create};
})();
