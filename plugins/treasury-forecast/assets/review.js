'use strict';
const token = new URLSearchParams(location.hash.slice(1)).get('token') || '';
const $ = id => document.getElementById(id);
const euro = value => new Intl.NumberFormat('it-IT',{style:'currency',currency:'EUR'}).format(Number(value));
let state = null;
let offset = 0;
let dirty = false;
const edits = new Map();
async function api(path, body) {
  const response = await fetch(path,{method:body ? 'POST':'GET',headers:{'X-Treasury-Token':token,'Content-Type':'application/json'},body:body ? JSON.stringify(body):undefined});
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || 'Operazione non riuscita');
  return result;
}
function message(text,error=false){$('status').textContent=text;$('status').classList.toggle('error',error);}
function guard(fn){return async()=>{try{await fn();}catch(error){message(error.message,true);}};}
function changed(){dirty=true;$('accept').disabled=true;$('scenario').disabled=true;$('previous').disabled=true;$('next').disabled=true;}
function textCell(row,text){const cell=document.createElement('td');cell.textContent=text;row.append(cell);return cell;}
function chart(){
  const svg=$('cash-chart');svg.replaceChildren();
  if(!state.daily.length){$('chart-caption').textContent='Completa le date per visualizzare il saldo previsto.';return;}
  const values=state.daily.map(row=>Number(row.closing_cash)),low=Math.min(0,...values),high=Math.max(0,...values),span=high-low||1;
  const x=i=>105+i*770/Math.max(values.length-1,1),y=v=>205-(v-low)*185/span;
  const add=(tag,attrs,text)=>{const element=document.createElementNS('http://www.w3.org/2000/svg',tag);for(const [key,value] of Object.entries(attrs))element.setAttribute(key,value);if(text)element.textContent=text;svg.append(element);return element;};
  for(const value of new Set([low,0,high])){add('line',{x1:105,x2:875,y1:y(value),y2:y(value),stroke:value===0?'#8296ad':'#dce4ed'});add('text',{x:95,y:y(value)+4,'text-anchor':'end','font-size':13,fill:'#42617d'},euro(value));}
  add('polyline',{points:values.map((value,i)=>x(i)+','+y(value)).join(' '),fill:'none',stroke:'#006fa9','stroke-width':3});
  add('text',{x:105,y:231,'font-size':13,fill:'#42617d'},state.daily[0].date);add('text',{x:875,y:231,'text-anchor':'end','font-size':13,fill:'#42617d'},state.daily.at(-1).date);
  $('chart-caption').textContent='Chiusure giornaliere in EUR. I dettagli per giorno e settimana sono nel prospetto Excel.';
}
function render(){
  $('company').textContent=state.company_name;
  $('period').textContent='Situazione al '+state.as_of+' · Previsione fino al '+state.horizon_end;
  $('coverage').textContent=state.coverage;
  if(state.review){$('reviewer').value=state.review.reviewer_ref;$('review-date').value=state.review.reviewed_at;$('conclusion').value=state.review.conclusion;}
  for(const id of ['reviewer','review-date','conclusion'])$(id).disabled=state.status==='accepted';
  message(state.status==='accepted'?'Previsione accettata. Per modificarla, apri un nuovo aggiornamento della pratica.':state.calculation_complete?'Bozza da rivedere. Le date attese restano ipotesi.':'Previsione incompleta: '+state.issue_count+' date da definire.');
  $('summary').replaceChildren();
  const facts=[['Cassa iniziale',euro(state.opening_cash)],['Minimo giornaliero',state.calculation_complete?euro(state.minimum_daily_cash):'Da completare'],['Prima data negativa',state.calculation_complete?(state.first_negative_day||'Nessuna'):'Da completare']];
  for(const [label,value] of facts){const box=document.createElement('div'),caption=document.createElement('span'),number=document.createElement('strong');caption.textContent=label;number.textContent=value;if(label==='Minimo giornaliero'&&Number(state.minimum_daily_cash)<0&&state.calculation_complete)number.className='negative';box.append(caption,number);$('summary').append(box);}
  $('events').replaceChildren();
  const selected=$('scenario-id').value;$('scenario-id').replaceChildren();
  for(const event of state.events){const option=document.createElement('option');option.value=event.event_id;option.textContent=event.description+' · '+euro(event.cash_amount);$('scenario-id').append(option);}
  if(state.events.some(event=>event.event_id===selected))$('scenario-id').value=selected;
  $('scenario').disabled=dirty||!state.calculation_complete||!state.total_events;
  chart();
  const query=$('search').value.toLowerCase();
  for(const event of state.events){
    if(!(event.event_id+' '+event.description).toLowerCase().includes(query))continue;
    const row=document.createElement('tr'),name=textCell(row,event.description),ref=document.createElement('small');ref.textContent=event.event_id;name.append(ref);
    textCell(row,euro(event.cash_amount));
    const date=document.createElement('input');date.type='date';date.value=edits.get(event.event_id)?.expected_date ?? event.expected_date ?? '';date.disabled=state.status==='accepted';date.setAttribute('aria-label','Data '+event.event_id);
    const basis=document.createElement('textarea');basis.value=edits.get(event.event_id)?.basis ?? event.basis;basis.disabled=state.status==='accepted';basis.setAttribute('aria-label','Base '+event.event_id);
    const capture=()=>{edits.set(event.event_id,{expected_date:date.value,basis:basis.value});changed();};date.addEventListener('input',capture);basis.addEventListener('input',capture);
    const dateCell=document.createElement('td'),basisCell=document.createElement('td');dateCell.append(date);basisCell.append(basis);row.append(dateCell,basisCell);$('events').append(row);
  }
  $('page').textContent=(state.total_events ? offset+1:0)+'–'+Math.min(offset+100,state.total_events)+' di '+state.total_events;
  $('previous').disabled=dirty||offset===0;$('next').disabled=dirty||offset+100>=state.total_events;
  $('save').disabled=state.status==='accepted';$('accept').disabled=dirty||!state.calculation_complete||state.status==='accepted';
  $('issues').replaceChildren();
  for(const item of [...state.issues,...state.evidence_notes]){const li=document.createElement('li');li.textContent=(item.event_id||item.id)+': '+item.detail;$('issues').append(li);}
  const comparison=state.comparison;
  $('comparison').textContent=comparison.through?'Variazione al '+comparison.through+': '+euro(comparison.closing_variance)+'. Differenza iniziale tra cassa effettiva e previsione precedente: '+euro(comparison.opening_variance)+'.':'Nessun periodo precedente comparabile.';
  $('changes').replaceChildren();
  for(const change of state.changes){const li=document.createElement('li');const label=value=>value?euro(value.cash_amount)+' il '+value.expected_date:'assente';li.textContent=change.event_id+': '+label(change.previous)+' → '+label(change.current);$('changes').append(li);}
}
async function load(){state=await api('/api/state?offset='+offset);edits.clear();dirty=false;render();}
$('save').onclick=guard(async()=>{await api('/api/review',{record_sha256:state.record_sha256,decisions:Object.fromEntries(edits)});await load();message('Modifiche salvate e saldi ricalcolati.');});
$('reload').onclick=guard(load);
$('previous').onclick=guard(async()=>{offset=Math.max(0,offset-100);await load();});
$('next').onclick=guard(async()=>{offset+=100;await load();});
$('search').oninput=render;
$('review-date').value=new Date().toISOString().slice(0,10);
$('accept').onclick=guard(async()=>{await api('/api/review',{record_sha256:state.record_sha256,review:{proposal_sha256:state.proposal_sha256,reviewer_ref:$('reviewer').value,reviewed_at:$('review-date').value,conclusion:$('conclusion').value}});await load();});
async function download(route,name,preview=false){const response=await fetch(route,{headers:{'X-Treasury-Token':token}});if(!response.ok)throw new Error((await response.json()).error);const url=URL.createObjectURL(await response.blob());if(preview)window.open(url,'_blank','noopener');else{const link=document.createElement('a');link.href=url;link.download=name;link.click();}setTimeout(()=>URL.revokeObjectURL(url),60000);}
$('workbook').onclick=guard(()=>download('/api/workbook','tesoreria.xlsx'));
$('report').onclick=guard(()=>download('/api/report','report.html',true));
$('scenario').onclick=guard(async()=>{const result=await api('/api/scenario',{record_sha256:state.record_sha256,dates:{[$('scenario-id').value]:$('scenario-date').value}});$('scenario-result').textContent='Alternativa: minimo giornaliero '+euro(result.minimum_daily_cash)+'. Previsione di base invariata.';});
window.addEventListener('beforeunload',event=>{if(dirty){event.preventDefault();event.returnValue='';}});
guard(load)();
