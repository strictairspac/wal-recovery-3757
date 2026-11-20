import {store} from '../stores/entities.js';
import {session} from '../stores/session.js';
import {logSetsAPI} from '../api/entities.js';
import {table} from '../components/common/table.js';
import {esc,formObject} from '../utils/html.js';
import {action} from '../hooks/action.js';
export function logsPage(){
 const sample=store.logs[0];
 return `<div class="section-title"><h2>事务日志集</h2><span>最多200条日志 / 30个键</span></div>${table(['日志集','初始账本','记录数','采样时刻','说明'],store.logs.map(s=>[esc(s.name),esc(JSON.stringify(s.initial)),s.records.length,esc(s.sample_times&&Object.keys(s.sample_times).length?JSON.stringify(s.sample_times):'—'),esc(s.description)+(s.parent_log_set_id?` <small>（校正派生自 #${s.parent_log_set_id}）</small>`:'')]))}
 <section class="split"><div><h2>录入一段可复查历史</h2><p>日志支持 begin / write / correct / commit / abort / checkpoint。写入与校正只允许初始账本已有键；检查点要求无活动事务。同一键遵守严格事务写锁。</p><p>采样时刻决定读数的“格”：write 未标注 at 时套用到该键的全部采样时刻；correct 只改写自己 [起点, 终点) 时段内的读数。迟到校正可直接在“采样读数”页录入，这里也接受手写 correct 记录。</p><p class="big-note">写入先留日志，恢复再核对。</p><details><summary>查看示例完整日志</summary><pre>${esc(JSON.stringify(sample?.records||[],null,2))}</pre></details></div>${session.role!=='viewer'?`<form id="log-form"><label>日志集名<input name="name" value="shift-20261117" required></label><label>说明<input name="description" value="晚班采样账本故障复核"></label><label>初始账本 JSON<textarea name="initial" rows="2" required>${esc(JSON.stringify(sample?.initial||{sample_A:100,sample_B:50}))}</textarea></label><label>采样时刻 JSON（键 → ISO 时刻或时刻数组，可留空）<textarea name="sample_times" rows="3">${esc(JSON.stringify(sample?.sample_times||{},null,2))}</textarea></label><label>日志 JSON 数组<textarea name="records" rows="8" required>${esc(JSON.stringify(sample?.records||[],null,2))}</textarea></label><button type="submit">校验并保存日志集</button></form>`:'<p class="readonly">观察员仅查看，新增需要操作员或管理员。</p>'}</section>`;}
export function bindLogs(render){action(document.querySelector('#log-form'),async f=>{const d=formObject(f);d.initial=JSON.parse(d.initial);d.records=JSON.parse(d.records);d.sample_times=d.sample_times&&d.sample_times.trim()?JSON.parse(d.sample_times):{};await logSetsAPI.create(d);await render();});}
