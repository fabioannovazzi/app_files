
const VOCABULARY=__LABELS__;
let EDITABLE=false,appSession,saveAttempt,busy=false,dirty=false;
const esc=value=>String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let review=null,reviewHash='',language='en',evidenceNames={},partyNames={};
const base=location.pathname.replace(/\/$/,'');
const words=()=>VOCABULARY[language]||VOCABULARY.en;
const t=key=>words()[key]||String(key).replace(/_/g,' ');
function itemTitle(item){
 const description=item.data?.description,translated=words()[description];
 return translated&&typeof description==='string'&&item.title.endsWith(description)
  ? item.title.slice(0,-description.length)+translated : item.title;
}
function caption(key){return words()[key]||String(key).replace(/_/g,' ');}
function stateText(value){return words()[String(value)]||String(value);}
const technicalFields=new Set(['party_id','scope_id','item_id','candidate_id','deadline_id']);
const codedFields=new Set(['status','identity_status','relationship_status','party_type','roles','opening_mode','urgency','register_scope','authority_status','fee_terms_status','engagement_document_status','classification','external_disclosure_status','applicability','separate_assessment_status','notice_status','kind']);
function valueHtml(value,key){
 if(value==null||value==='')return esc(t('missing'));
 if(Array.isArray(value))return value.length?value.map(entry=>`<div class="record">${valueHtml(entry,key)}</div>`).join(''):esc(t('none'));
 if(typeof value==='object'){
  const priority=['display_name','title','objective','requested_work','summary','description','roles','identity_status'];
  const rank=field=>priority.includes(field)?priority.indexOf(field):priority.length;
  const entries=Object.entries(value).sort(([a],[b])=>rank(a)-rank(b)),regular=entries.filter(([field])=>!technicalFields.has(field)),technical=entries.filter(([field])=>technicalFields.has(field));
  const fields=rows=>`<dl class="facts">${rows.map(([field,entry])=>`<dt>${esc(caption(field))}</dt><dd>${valueHtml(entry,field)}</dd>`).join('')}</dl>`;
  return fields(regular);
 }
 if(key==='evidence_ids'||key==='source_evidence_ids')return esc(evidenceNames[value]||value);
 if(key==='searched_party_ids'||key==='party_ids')return esc(partyNames[value]||value);
 if(typeof value==='boolean')return esc(t(String(value)));
 if(codedFields.has(key))return esc(stateText(value));
 if(['basis','handling_notes','search_method','description','assessment_basis','purpose'].includes(key))return esc(words()[String(value)]||value);
 return esc(value);
}
function render(value){
 dirty=false;appSession=value?.session;EDITABLE=!!appSession;
 const payload=value?.review_payload||value?.review||value;
 if(!payload||!Array.isArray(payload.items)){document.querySelector('#items').innerHTML=`<p>${esc(t('no_payload'))}</p>`;return;}
 review=payload;reviewHash=value?.review_payload_sha256||'';language=VOCABULARY[payload.language]?payload.language:'en';document.documentElement.lang=language;
 document.querySelector('#title').textContent=t('page_title');document.title=`Lucia · ${t('page_title')}`;
 document.querySelector('#intro').textContent=t(EDITABLE?'review_intro':'read_only');
 document.querySelector('#toolbar').hidden=!EDITABLE;
 document.querySelector('#reviewer-label').textContent=t('reviewer');document.querySelector('#save').textContent=t('save');
 evidenceNames=Object.fromEntries((payload.evidence_sources||[]).map(row=>[row.evidence_id,row.name]));
 const parties=payload.items.find(item=>item.item_type==='party_map')?.data?.parties||[];
 partyNames=Object.fromEntries(parties.map(p=>[p.party_id,p.display_name]));
 const order=['matter_request','party_map','engagement','conflict_scope','conflict_candidate','deadline_posture','deadline_candidate','missing_item','confidentiality','aml_applicability','privacy_retention','folder_plan'];
 const index=type=>order.includes(type)?order.indexOf(type):order.length;
 const items=[...payload.items].sort((a,b)=>index(a.item_type)-index(b.item_type));
 document.querySelector('#items').innerHTML=items.map((item,i)=>`<details class="review-item" data-id="${esc(item.id)}" ${i===0?'open':''}><summary><h2>${esc(itemTitle(item))}</h2><span class="state">${esc(stateText(item.status))}</span></summary><div class="content">${valueHtml(item.data||{},'')}${item.evidence_ids?.length?`<p class="evidence">${esc(t('sources'))}: ${item.evidence_ids.map(id=>esc(evidenceNames[id]||id)).join(' · ')}</p>`:''}${EDITABLE?`<div class="decision-controls"><label>${esc(t('decision'))}<select aria-label="${esc(t('decision'))}"><option value="">${esc(t('review_first'))}</option>${item.allowed_actions.map(action=>`<option value="${esc(action)}">${esc(stateText(action))}</option>`).join('')}</select><small class="notice">${esc(t('proposal'))}: ${esc(stateText(item.recommended_action))}</small></label><label>${esc(t('note'))}<textarea maxlength="5000"></textarea></label></div>`:''}</div></details>`).join('');
 if(EDITABLE){
  const pending=value?.pending_review;const status=document.querySelector('#status');
  document.querySelector('#reviewer').value='';status.textContent='';status.className='';
  if(value?.pending_review_status==='current'&&pending){
   document.querySelector('#reviewer').value=pending.reviewer;
   const saved=new Map(pending.decisions.map(item=>[item.item_id,item]));
   for(const item of document.querySelectorAll('.review-item')){
    const decision=saved.get(item.dataset.id);if(!decision)continue;
    item.querySelector('select').value=decision.action;
    item.querySelector('textarea').value=decision.note;item.open=true;
   }
   status.className='good';status.textContent=t('restored');
  }else if(value?.pending_review_status==='unavailable'){
   status.className='bad';status.textContent=t('saved_unavailable');
  }
 }
 document.querySelector('#save').disabled=false;
}
let nextRequest=0;
const pendingRequests=new Map();
function request(method,params){return new Promise((resolve,reject)=>{
 const id=++nextRequest,timer=setTimeout(()=>{pendingRequests.delete(id);reject(new Error(t('saved_unavailable')));},30000);
 pendingRequests.set(id,{resolve,reject,timer});parent.postMessage({jsonrpc:'2.0',id,method,params},'*');
});}
function accept(result){
 if(result?.isError)throw new Error(result.content?.find(item=>item.type==='text')?.text || t('saved_unavailable'));
 render(result?._meta?.matter || result?.structuredContent || result);
}
document.querySelector('#save').addEventListener('click',async()=>{
 if(busy || !appSession)return;
 const reviewer=document.querySelector('#reviewer').value.trim(),status=document.querySelector('#status');
 if(!reviewer){status.className='bad';status.textContent=t('reviewer_required');return;}
 const decisions=[...document.querySelectorAll('.review-item')].map(item=>({item_id:item.dataset.id,action:item.querySelector('select').value,note:item.querySelector('textarea').value.trim()})).filter(item=>item.action);
 saveAttempt ||= {session:appSession,request_id:crypto.randomUUID(),reviewer,decisions};
 busy=true;document.querySelectorAll('input,textarea,select,button').forEach(node=>node.disabled=true);
 try{accept(await request('tools/call',{name:'lucia_matter_save',arguments:saveAttempt}));saveAttempt=null;status.className='good';status.textContent=t('saved');}
 catch(error){status.className='bad';status.textContent=error.message;}
 finally{busy=false;document.querySelectorAll('input,textarea,select,button').forEach(node=>node.disabled=false);}
});
document.querySelector('#toolbar').hidden=true;
document.querySelector('main').addEventListener('input',()=>{if(!busy){saveAttempt=null;dirty=true;}});
window.addEventListener('message',event=>{
 if(event.source!==parent || event.data?.jsonrpc!=='2.0')return;
 const message=event.data,item=pendingRequests.get(message.id);
 if(item){clearTimeout(item.timer);pendingRequests.delete(message.id);message.error?item.reject(new Error(message.error.message)):item.resolve(message.result);return;}
 if(message.method==='ui/notifications/tool-result'){
  if(busy || dirty)return;
  try{accept(message.params);}catch(error){document.querySelector('#status').textContent=error.message;}
 }
 if(message.method==='ui/resource-teardown')parent.postMessage({jsonrpc:'2.0',id:message.id,result:{}},'*');
});
request('ui/initialize',{protocolVersion:'2026-01-26',appInfo:{name:'Lucia matter opening',version:'1.0.0'},appCapabilities:{availableDisplayModes:['inline','fullscreen']}})
.then(()=>parent.postMessage({jsonrpc:'2.0',method:'ui/notifications/initialized'},'*'))
.catch(()=>{document.querySelector('#status').textContent=t('no_payload');});
