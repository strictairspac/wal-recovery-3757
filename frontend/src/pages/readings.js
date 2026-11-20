import {store} from '../stores/entities.js';
import {session} from '../stores/session.js';
import {logSetsAPI,crashCasesAPI,recoveriesAPI} from '../api/entities.js';
import {table} from '../components/common/table.js';
import {esc,formObject} from '../utils/html.js';
import {action,message} from '../hooks/action.js';

/* Sampling ledger view: bitemporal readings (sample instant x commit position),
   late-correction entry, and the shift-handover ledgers frozen at each checkpoint. */
let state={source:'log',id:'',at:'',commit_lsn:'',key:'',corrections:true,compare:true,data:null,handovers:null,correctionCount:1};
let mountToken=0,loadedToken=0;

const SOURCES={log:'日志集',case:'故障场景',recovery:'恢复快照'};
function items(kind){return kind==='log'?store.logs:kind==='case'?store.cases:store.runs;}
function label(kind,item){return kind==='log'||kind==='case'?item.name:item.label;}
function ensureSource(){
 if(state.id&&items(state.source).some(x=>String(x.id)===String(state.id)))return;
 const kind=['log','case','recovery'].find(k=>items(k).length);
 state.id=kind?items(kind)[0].id:'';
 if(kind)state.source=kind;
}
function sourceOptions(){
 return Object.entries(SOURCES).map(([kind,text])=>`<optgroup label="${text}">${items(kind).map(item=>`<option value="${kind}:${item.id}" ${state.source===kind&&String(state.id)===String(item.id)?'selected':''}>#${item.id} ${esc(label(kind,item))}</option>`).join('')}</optgroup>`).join('');
}
async function loadReadings(){
 if(!state.id)return null;
 const params={at:state.at,commit_lsn:state.commit_lsn,key:state.key};
 if(state.source==='recovery')return recoveriesAPI.readings(state.id,{...params,compare:state.compare});
 if(state.source==='case')return crashCasesAPI.readings(state.id,{...params,compare:state.compare,corrections:state.corrections});
 return logSetsAPI.readings(state.id,{...params,compare:state.compare,corrections:state.corrections});
}
async function loadHandovers(){
 if(!state.id)return null;
 if(state.source==='recovery')return recoveriesAPI.handovers(state.id,{});
 if(state.source==='case')return crashCasesAPI.handovers(state.id,{});
 return logSetsAPI.handovers(state.id,{});
}
function readingTable(data){
 if(data.comparison)return table(['采样时刻','账本键','补录前','补录后','来源变化','结果'],
  data.comparison.map(row=>[esc(row.sample_at),esc(row.key),row.before??'—',row.after??'—',`${esc(row.source_before||'—')} → ${esc(row.source_after||'—')}`,row.changed?'<b>已补录</b>':'—']));
 const rows=data.readings||data.after_backfill||[];
 return table(['采样时刻','账本键','读数','来源','提交位置','事务'],
  rows.map(row=>[esc(row.sample_at),esc(row.key),row.value,esc(row.source_op),row.commit_lsn,esc(row.tx||'—')]));
}
function handoverTable(){
 const h=state.handovers;if(!h)return '';
 return `<div class="section-title"><h2>交班账（检查点快照）</h2><span>更早的检查点仍然可查</span></div>${table(['检查点LSN','交班账本','读数格数'],
  h.handovers.map(item=>[item.checkpoint_lsn,esc(JSON.stringify(item.ledger)),(item.readings||[]).length]))}`;
}
function correctionFields(){
 return Array.from({length:state.correctionCount},(_,i)=>`<div class="fields"><label>账本键<input name="key_${i}" value="sample_A" required></label><label>校正值<input name="value_${i}" type="number" value="0" required></label><label>时段起点<input name="start_${i}" placeholder="2026-11-17T08:00" required></label><label>时段终点<input name="end_${i}" placeholder="2026-11-17T16:00" required></label></div>`).join('');
}
function sourceSummary(){
 const item=items(state.source).find(x=>String(x.id)===String(state.id));
 return item?`${SOURCES[state.source]} #${item.id} ${label(state.source,item)}`:'';
}
export function readingsPage(){
 ensureSource();
 const data=state.data;const isLog=state.source==='log';
 const selected=sourceSummary();
 return `<div class="section-title"><h2>采样读数查询</h2><span>采样时刻 × 提交位置</span></div>
 <p class="notice">读数是一格“账本键 × 采样时刻”，只包含查询提交位置之前已提交的事务。迟到校正补进它所属的原采样时段，重叠处以后提交的为准；同一笔校正跨多个时段的改动在同一个提交位置一起生效。未提交的校正不入账。</p>
 <section class="split"><div><h2>查询条件</h2><form id="reading-form">
 <label>数据来源<select name="source">${sourceOptions()}</select></label>
 <div class="fields"><label>采样时刻<input name="at" value="${esc(state.at)}" placeholder="留空为全部"></label><label>提交位置 / 断电位置<input name="commit_lsn" type="number" min="0" value="${esc(state.commit_lsn)}" placeholder="故障场景默认断电点，其余为末尾"></label></div>
 <label>账本键<input name="key" value="${esc(state.key)}" placeholder="留空为全部"></label>
 <label class="check"><input type="checkbox" name="corrections" ${state.corrections?'checked':''}> 计入校正</label>
 <label class="check"><input type="checkbox" name="compare" ${state.compare?'checked':''}> 对照补录前后</label>
 <button type="submit">查询 / 切换来源</button></form>
 <p class="big-note">原时段不动，读数可回查。</p>
 <p class="checksum">提交位置留空时，故障场景取该场景的断电点，其余取日志末尾。</p></div>
 <div><h2>读数 · ${esc(selected||'未选择来源')}</h2>${data?`<p class="checksum">提交位置 ${data.commit_lsn}${data.at?' · 采样时刻 '+esc(data.at):''}${data.key?' · 键 '+esc(data.key):''}</p>${readingTable(data)}`:'<p class="readonly">选择来源后点击“切换来源”，即可按采样时刻与提交位置查看读数。</p>'}</div></section>
 ${handoverTable()}
 <section class="split"><div><h2>录入迟到校正</h2><p>一次提交包含一个事务的多条校正，整笔在同一个提交位置一起生效。时段左闭右开 [起点, 终点)，只改自己时段内的读数；重叠时以提交位置更晚者为准。保存会生成新的派生日志集，原日志集不变。</p></div>${session.role!=='viewer'&&isLog?`<form id="correction-form"><label>派生日志集名<input name="name" value="late-correction" required></label><label>事务标识<input name="tx" value="C1" required></label>${correctionFields()}<label class="check"><input type="checkbox" name="commit" checked> 立即提交（取消则保持未提交，不入账）</label><div class="toolbar"><button type="button" class="secondary" id="add-correction">再加一条</button></div><button type="submit">保存校正</button></form>`:`<p class="readonly">${isLog?'观察员仅可查询读数。':'请先在数据来源中选择日志集，再录入校正。'}</p>`}</section>`;
}
export function bindReadings(render){
 const form=document.querySelector('#reading-form');
 form?.addEventListener('submit',async e=>{
  e.preventDefault();const d=formObject(form);const [kind,id]=(d.source||'').split(':');
  Object.assign(state,{source:kind,id:Number(id),at:d.at,commit_lsn:d.commit_lsn,key:d.key,
   corrections:form.querySelector('[name=corrections]').checked,compare:form.querySelector('[name=compare]').checked});
  try{state.data=await loadReadings();state.handovers=await loadHandovers();await render();}
  catch(err){message(err.message,true);}
 });
 document.querySelector('#add-correction')?.addEventListener('click',async()=>{state.correctionCount+=1;await render();});
 action(document.querySelector('#correction-form'),async f=>{
  const d=formObject(f);
  const corrections=Array.from({length:state.correctionCount},(_,i)=>({key:d['key_'+i],value:Number(d['value_'+i]),start:d['start_'+i],end:d['end_'+i]}));
  const created=await logSetsAPI.correct(state.id,{name:d.name,tx:d.tx,corrections,commit:f.querySelector('[name=commit]').checked});
  Object.assign(state,{source:'log',id:created.id,data:null,handovers:null,correctionCount:1,at:'',commit_lsn:'',key:''});
  await store.refresh();
  await render();
 });
 // Load the selected source once so the first visit already shows readings; later renders
 // (e.g. adding a correction row) reuse the cached result instead of refetching.
 const token=++mountToken;
 if(state.id&&!state.data&&loadedToken!==token){
  loadedToken=token;
  loadReadings().then(async data=>{if(token!==mountToken)return;state.data=data;state.handovers=await loadHandovers();await render();}).catch(err=>message(err.message,true));
 }
}

