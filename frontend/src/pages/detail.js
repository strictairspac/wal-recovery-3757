import {table} from '../components/common/table.js';
import {badge} from '../components/common/status.js';
import {esc} from '../utils/html.js';
import {download} from '../api/client.js';
import {message} from '../hooks/action.js';

function correctionTable(title,rows){
 if(!rows?.length)return '';
 return `<h2>${title}</h2>${table(['LSN','事务','账本键','值','时段/提交位置'],rows.map(x=>[x.lsn,esc(x.tx),esc(x.key),x.value,
  x.start?`${esc(x.start)} → ${esc(x.end)}`:esc(x.commit_lsn??'—')]))}`;
}
function handoverSection(job){
 const points=job.result?.checkpoints||[];
 if(!points.length)return '';
 return `<h2>交班账（检查点快照）</h2><p class="checksum">恢复从检查点LSN ${job.result.checkpoint_lsn} 接着算，不重放此前的日志；更早的交班账仍可查。</p>${table(['检查点LSN','交班账本'],
  points.map(p=>[p.checkpoint_lsn,esc(JSON.stringify(p.ledger))]))}`;
}
function readingSection(job){
 const r=job.result;if(!r)return '';
 if(r.readings_available===false)return `<h2>采样读数</h2><p class="readonly">该日志集未声明采样时刻（sample_times 或写入的 at），因此没有读数对照；旧演练结果不受影响。</p>`;
 if(!r.readings_available)return '';
 const rows=r.reading_comparison||[];
 return `<h2>补录前后读数对照</h2><p class="checksum">只计入在崩溃点之前已提交的校正；未提交的校正不入账。</p>${table(['采样时刻','账本键','补录前','补录后','结果'],
  rows.map(x=>[esc(x.sample_at),esc(x.key),x.before??'—',x.after??'—',x.changed?'<b>已补录</b>':'—']))}
  ${correctionTable('已入账的迟到校正',r.late_corrections)}
  ${correctionTable('未提交（不入账）的校正',r.uncommitted_corrections)}
  ${correctionTable('已撤销的校正',r.aborted_corrections)}`;
}
export function detailPage(job){
 if(!job)return '<section class="empty"><h2>还没有恢复记录</h2><p>先选择故障场景并提交恢复任务，再逐条查看日志重做与撤销。</p><a href="#runs">进入恢复队列 →</a></section>';
 const r=job.result;
 const phase={redo:'重做',redo_backfill:'补录校正',redo_abort_undo:'撤销中止',undo_loser:'撤销未提交'};
 return `<div class="section-title"><h2>${esc(job.label)} <small>#${job.id}</small></h2>${badge(job.status)}</div>
 ${r?`<section class="verdict"><div><p>恢复账本核对</p><h2>${r.invariant_passed?'提交结果一致':'恢复失败'}</h2></div><p>检查点LSN ${r.checkpoint_lsn??'—'} · 崩溃点 ${r.crash_after??'—'}<br>重做 ${r.redo_count??0} 次 / 撤销 ${r.undo_count??0} 次${r.backfill_count?' / 补录 '+r.backfill_count+' 次':''}<br>${r.error?esc(r.error):'未提交事务 '+esc((r.losers||[]).join(', ')||'无')}</p></section>
 ${table(['账本键','检查点值','重做后','恢复后','独立提交结果'],Object.keys(r.recovered||{}).map(k=>[esc(k),r.durable_checkpoint[k],r.after_redo[k],r.recovered[k],r.oracle[k]]))}
 ${handoverSection(job)}
 ${readingSection(job)}
 <h2>日志恢复轨迹</h2>${table(['LSN','事务','阶段','键','before → after'],(r.trace||[]).map(t=>[t.lsn,esc(t.tx),esc(phase[t.phase]||t.phase),esc(t.key),t.phase==='undo_loser'||t.phase==='redo_abort_undo'?`${t.after} → ${t.before}`:`${t.before} → ${t.after}`]))}
 <p class="checksum">输入摘要 ${esc(r.input_sha256||'无')}<br>结果摘要 ${esc(r.result_sha256||'无')}</p>
 <div class="toolbar"><button id="export">导出日志与恢复证据</button><button class="secondary" id="refresh">刷新状态</button><a href="#readings">按采样时刻查读数 →</a></div>
 <details><summary>查看冻结输入</summary><pre>${esc(JSON.stringify(job.snapshot,null,2))}</pre></details>`
 :'<p class="notice">后台恢复计算中，请刷新状态。</p>'}`;
}
export function bindDetail(job,render){
 document.querySelector('#refresh')?.addEventListener('click',render);
 document.querySelector('#export')?.addEventListener('click',()=>download(job.id).catch(e=>message(e.message,true)));
}
