"""Quiescent-checkpoint WAL teaching model with strict write locks, redo/undo
and late sampling corrections backfilled into their original sampling periods.

Two timelines are kept apart:

* transaction time — where a change sits in the log and when it committed
  (``commit_lsn``); it decides "later submission wins" and the crash prefix that
  recovery is allowed to replay;
* valid time — the original sampling instant (``sample_at``) a reading belongs to;
  it is what a late correction is backfilled into.

A reading is a ``(key, sample_at)`` cell resolved by commit position.  A correction
covers ``[start, end)`` only — it never rewrites the page value outside its own
period — and only transactions committed at or before the queried position are
visible, so uncommitted or aborted corrections never reach the ledger.  Because
visibility is decided by the single commit position, every change of a transaction
(even across several sampling instants) takes effect together.
"""
import copy,hashlib,json,re
from datetime import datetime,timezone

def parse_time(value):
    """Parse an ISO-8601 sampling time; aware values are normalised to naive UTC."""
    if not isinstance(value,str) or not value.strip() or len(value)>40:raise ValueError('采样时刻必须是ISO 8601文本')
    try:parsed=datetime.fromisoformat(value.strip().replace('Z','+00:00'))
    except ValueError:raise ValueError(f'采样时刻不是合法的ISO 8601: {value}')
    if parsed.tzinfo is not None:parsed=parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed

def _normalise_times(sample_times):
    """Accept ``{key: iso}`` or ``{key: [iso, ...]}`` and return ``{key: sorted naive-UTC list}``."""
    out={}
    for key,value in (sample_times or {}).items():
        raw=value if isinstance(value,list) else [value]
        out[key]=sorted({parse_time(item) for item in raw})
    return out

def _check_sample_times(initial,sample_times):
    if sample_times is None:return
    if not isinstance(sample_times,dict):raise ValueError('采样时刻必须是键到ISO 8601文本或文本数组的映射')
    if len(sample_times)>30:raise ValueError('采样时刻最多30个键')
    for key,value in sample_times.items():
        if key not in initial:raise ValueError('采样时刻的键必须存在于初始账本')
        items=value if isinstance(value,list) else [value]
        if not items:raise ValueError('每个键至少需要一个采样时刻')
        if len(items)>200:raise ValueError('每个键最多200个采样时刻')
        for item in items:
            try:parse_time(item)
            except ValueError as exc:raise ValueError(str(exc))

def validate(initial,records,sample_times=None):
    if not initial or len(initial)>30 or not records or len(records)>200: raise ValueError('需1—30个键及1—200条日志')
    for key,value in initial.items():
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,50}',key) or isinstance(value,bool) or not isinstance(value,int) or abs(value)>1000000000:
            raise ValueError('初始键为字母数字下划线短横线，值为绝对值不超过10亿的整数')
    _check_sample_times(initial,sample_times)
    state=copy.deepcopy(initial); active={};used=set();locks={}
    for lsn,r in enumerate(records,1):
        op=r.get('op');tx=r.get('tx')
        if op=='checkpoint':
            if active:raise ValueError(f'LSN {lsn}: 仅支持无活动事务的静止检查点')
            continue
        if not tx:raise ValueError(f'LSN {lsn}: 需要事务标识')
        if op=='begin':
            if tx in used:raise ValueError(f'LSN {lsn}: 事务标识不得重复')
            active[tx]=[];used.add(tx)
        elif op in ('write','correct'):
            if tx not in active:raise ValueError(f'LSN {lsn}: 写入事务尚未begin')
            key=r.get('key');value=r.get('value')
            if key not in initial:raise ValueError(f'LSN {lsn}: 写入键必须存在于初始账本')
            if isinstance(value,bool) or not isinstance(value,int) or abs(value)>1000000000:raise ValueError(f'LSN {lsn}: 数值超限')
            if op=='correct':
                start=r.get('start');end=r.get('end')
                if not start or not end:raise ValueError(f'LSN {lsn}: 校正需要时段起点与终点')
                try:
                    start_at=parse_time(start);end_at=parse_time(end)
                except ValueError as exc:raise ValueError(f'LSN {lsn}: {exc}')
                if start_at>=end_at:raise ValueError(f'LSN {lsn}: 校正时段起点须早于终点')
            elif r.get('at') is not None:
                try:parse_time(r['at'])
                except ValueError as exc:raise ValueError(f'LSN {lsn}: {exc}')
            if key in locks and locks[key]!=tx:raise ValueError(f'LSN {lsn}: 违反严格写锁，活动事务持有同键')
            locks[key]=tx;active[tx].append((key,None if op=='correct' else state[key]))
            if op=='write':state[key]=value
        elif op in ('commit','abort'):
            if tx not in active:raise ValueError(f'LSN {lsn}: 事务未开启或已结束')
            if op=='abort':
                for key,before in reversed(active[tx]):
                    if before is not None:state[key]=before
            del active[tx]
            locks={k:v for k,v in locks.items() if v!=tx}
        else:raise ValueError(f'LSN {lsn}: 未知操作')
    return True

def _commit_positions(prefix):
    positions={}
    for lsn,r in enumerate(prefix,1):
        if r['op']=='commit':positions[r['tx']]=lsn
    return positions

def _pick(candidates,slot,candidate):
    """Later submission wins: compare commit position first, then log position."""
    current=candidates.get(slot)
    if current is None or (candidate[0],candidate[1])>=(current[0],current[1]):candidates[slot]=candidate

def _schedule(prefix,times,commits):
    """Sampling instants known at this position: declared sample times plus committed ``at`` marks.

    Instants announced only by an uncommitted write are not part of the schedule, because an
    uncommitted change never reaches the ledger.
    """
    moments={key:set(value) for key,value in times.items()}
    for r in prefix:
        if r.get('op')=='write' and r.get('at') and r['tx'] in commits:
            moments.setdefault(r['key'],set()).add(parse_time(r['at']))
    return moments

def has_schedule(records,times):
    return bool(times) or any(r.get('op')=='write' and r.get('at') for r in records)

def reading_candidates(initial,records,times,upto,include_corrections=True):
    """Resolve every visible ``(key, sample instant)`` cell at the commit position ``upto``."""
    prefix=records[:upto];commits=_commit_positions(prefix)
    moments=_schedule(prefix,times,commits)
    candidates={}
    for key,value in initial.items():
        for sample in moments.get(key,()):candidates[(key,sample)]=(0,0,'initial',None,value)
    for lsn,r in enumerate(prefix,1):
        if r.get('op')!='write' or r['tx'] not in commits:continue
        key=r['key'];instants=[parse_time(r['at'])] if r.get('at') else sorted(moments.get(key,()))
        for sample in instants:_pick(candidates,(key,sample),(commits[r['tx']],lsn,'write',r['tx'],r['value']))
    if include_corrections:
        for lsn,r in enumerate(prefix,1):
            if r.get('op')!='correct' or r['tx'] not in commits:continue
            start=parse_time(r['start']);end=parse_time(r['end'])
            for sample in sorted(moments.get(r['key'],())):
                # A correction rewrites only the instants inside its own [start, end) period.
                if start<=sample<end:_pick(candidates,(r['key'],sample),(commits[r['tx']],lsn,'correct',r['tx'],r['value']))
    rows=[]
    for (key,sample),(commit,lsn,source,tx,value) in candidates.items():
        rows.append({'key':key,'sample_at':sample.isoformat(),'value':value,'source_op':source,
                     'source_lsn':lsn,'commit_lsn':commit,'tx':tx})
    rows.sort(key=lambda row:(row['sample_at'],row['key']))
    return rows

def compare_readings(before,after):
    """Pair the pre-backfill and post-backfill readings by ``(key, sample_at)`` cell."""
    before_map={(row['key'],row['sample_at']):row for row in before}
    after_map={(row['key'],row['sample_at']):row for row in after}
    rows=[]
    for slot in sorted(set(before_map)|set(after_map)):
        left=before_map.get(slot);right=after_map.get(slot)
        rows.append({'key':slot[0],'sample_at':slot[1],
                     'before':left['value'] if left else None,'after':right['value'] if right else None,
                     'source_before':left['source_op'] if left else None,'source_after':right['source_op'] if right else None,
                     'changed':bool(left and right and left['value']!=right['value'])})
    return rows

def readings(initial,records,sample_times=None,at=None,commit_lsn=None,key=None,include_corrections=True,compare=False):
    """Query the sampling ledger by sampling instant (valid time) and commit position."""
    validate(initial,records,sample_times)
    if commit_lsn is None:commit_lsn=len(records)
    if isinstance(commit_lsn,bool) or not isinstance(commit_lsn,int) or not 0<=commit_lsn<=len(records):
        raise ValueError('提交位置超出日志范围')
    times=_normalise_times(sample_times)
    if not has_schedule(records[:commit_lsn],times):raise ValueError('未声明采样时刻：请填写sample_times或为写入记录标注at')
    at_time=parse_time(at) if at else None
    def filtered(rows):
        out=rows
        if at_time is not None:out=[row for row in out if row['sample_at']==at_time.isoformat()]
        if key is not None:out=[row for row in out if row['key']==key]
        return out
    after=filtered(reading_candidates(initial,records,times,commit_lsn,True))
    out={'commit_lsn':commit_lsn,'at':at_time.isoformat() if at_time else None,'key':key,
         'include_corrections':bool(include_corrections),'compare':bool(compare)}
    if compare:
        before=filtered(reading_candidates(initial,records,times,commit_lsn,False))
        out['before_backfill']=before;out['after_backfill']=after;out['comparison']=compare_readings(before,after)
    elif include_corrections:out['readings']=after
    else:out['readings']=filtered(reading_candidates(initial,records,times,commit_lsn,False))
    return out

def handovers(initial,records,sample_times=None,commit_lsn=None):
    """Return every shift-handover ledger: the frozen snapshot at each quiescent checkpoint.

    Checkpoints older than the latest one stay listed, so a recovery that restarts from the
    most recent checkpoint can still look up the handover ledgers recorded before it.
    """
    validate(initial,records,sample_times)
    if commit_lsn is None:commit_lsn=len(records)
    if isinstance(commit_lsn,bool) or not isinstance(commit_lsn,int) or not 0<=commit_lsn<=len(records):
        raise ValueError('提交位置超出日志范围')
    times=_normalise_times(sample_times);can_read=has_schedule(records[:commit_lsn],times)
    prefix=records[:commit_lsn];state=copy.deepcopy(initial);active={};out=[]
    for lsn,r in enumerate(prefix,1):
        op=r['op'];tx=r.get('tx')
        if op=='begin':active[tx]=[]
        elif op in ('write','correct'):
            active[tx].append((r['key'],state[r['key']]))
            if op=='write':state[r['key']]=r['value']
        elif op=='abort':
            for key,before in reversed(active[tx]):state[key]=before
            del active[tx]
        elif op=='commit':del active[tx]
        elif op=='checkpoint':
            item={'checkpoint_lsn':lsn,'ledger':copy.deepcopy(state),'record_count':lsn}
            if can_read:
                item['readings']=reading_candidates(initial,records,times,lsn,True)
                item['readings_before_backfill']=reading_candidates(initial,records,times,lsn,False)
            out.append(item)
    return {'commit_lsn':commit_lsn,'handovers':out}

def _page_state_at(prefix,initial,stop_lsn):
    """Page ledger at ``stop_lsn`` (inclusive); quiescent checkpoints hold no active tx."""
    state=copy.deepcopy(initial);active={}
    for r in prefix[:stop_lsn]:
        op=r['op'];tx=r.get('tx')
        if op=='begin':active[tx]=[]
        elif op=='write':active[tx].append((r['key'],state[r['key']]));state[r['key']]=r['value']
        elif op=='correct':active[tx].append((r['key'],None))
        elif op=='abort':
            for key,before in reversed(active[tx]):
                if before is not None:state[key]=before
            del active[tx]
        elif op=='commit':del active[tx]
    return state

def recover(initial,records,crash_after,sample_times=None):
    validate(initial,records,sample_times)
    if isinstance(crash_after,bool) or not isinstance(crash_after,int) or not 0<=crash_after<=len(records):raise ValueError('崩溃点超出日志范围')
    times=_normalise_times(sample_times)
    prefix=records[:crash_after]
    # Redo restarts at the most recent quiescent checkpoint: earlier logs are not replayed
    # because the checkpoint already holds their data pages.  Those earlier handover
    # ledgers stay listed in ``checkpoints`` so they remain auditable.
    checkpoint=max((lsn for lsn,r in enumerate(prefix,1) if r['op']=='checkpoint'),default=0)
    durable=_page_state_at(prefix,initial,checkpoint)
    checkpoints=[{'checkpoint_lsn':lsn,'ledger':_page_state_at(prefix,initial,lsn),'record_count':lsn}
                 for lsn,r in enumerate(prefix,1) if r['op']=='checkpoint']
    state=copy.deepcopy(durable);active={};winners=[];aborted=[];trace=[];writes=[]
    all_commits={};all_aborted=set();corrections=[]
    for lsn,r in enumerate(prefix,1):
        if r['op']=='correct':
            corrections.append({'lsn':lsn,'tx':r['tx'],'key':r['key'],'value':r['value'],
                                'start':r['start'],'end':r['end']})
        if lsn<=checkpoint:
            if r['op']=='commit':all_commits[r['tx']]=lsn
            elif r['op']=='abort':all_aborted.add(r['tx'])
            continue
        op=r['op'];tx=r.get('tx')
        if op=='begin':active[tx]=[]
        elif op=='write':
            row={'lsn':lsn,'tx':tx,'key':r['key'],'before':state[r['key']],'after':r['value']}
            active[tx].append(row);writes.append(row);state[r['key']]=r['value']
            trace.append(dict(row,phase='redo'))
        elif op=='correct':
            # A correction joins its transaction's undo chain but only backfills its own
            # sampling period; the live page value is never changed by a correction.
            row={'lsn':lsn,'tx':tx,'key':r['key'],'value':r['value'],'kind':'correction','op':'correct',
                 'period':{'start':r['start'],'end':r['end']}}
            active[tx].append(row);trace.append(dict(row,phase='redo_backfill'))
        elif op=='abort':
            for row in reversed(active[tx]):
                if row.get('kind')!='correction':state[row['key']]=row['before']
                trace.append(dict(row,phase='redo_abort_undo'))
            del active[tx];aborted.append(tx);all_aborted.add(tx)
        elif op=='commit':
            winners.append(tx);all_commits[tx]=lsn;del active[tx]
    # Simulated crash durable pages are exactly the last quiescent checkpoint.
    before_undo=copy.deepcopy(state);losers=sorted(active)
    undo=sorted([w for tx in active for w in active[tx]],key=lambda w:w['lsn'],reverse=True)
    for row in undo:
        if row.get('kind')!='correction':state[row['key']]=row['before']
        trace.append(dict(row,phase='undo_loser'))
    # Independent winner-only oracle from the durable checkpoint excludes aborted/unfinished work.
    oracle=copy.deepcopy(durable)
    for row in writes:
        if row['tx'] in winners:oracle[row['key']]=row['after']
    late=[dict(row,commit_lsn=all_commits[row['tx']]) for row in corrections if row['tx'] in all_commits]
    pending=[dict(row) for row in corrections if row['tx'] not in all_commits and row['tx'] not in all_aborted]
    aborted_corrections=[dict(row) for row in corrections if row['tx'] in all_aborted]
    can_read=has_schedule(prefix,times)
    readings_before=reading_candidates(initial,records,times,crash_after,False) if can_read else []
    readings_after=reading_candidates(initial,records,times,crash_after,True) if can_read else []
    comparison=compare_readings(readings_before,readings_after)
    checksum=hashlib.sha256(json.dumps(state,sort_keys=True).encode()).hexdigest()
    source_payload={'initial':initial,'records':records,'crash_after':crash_after}
    if sample_times:source_payload['sample_times']=sample_times
    source=json.dumps(source_payload,sort_keys=True)
    return {'simulation':True,'model_version':'strict-wal-quiescent-v1','crash_after':crash_after,'checkpoint_lsn':checkpoint,
            'redo_from_lsn':checkpoint+1 if checkpoint else 1,'checkpoints':checkpoints,
            'durable_checkpoint':durable,'after_redo':before_undo,'recovered':state,'oracle':oracle,'invariant_passed':state==oracle,
            'committed':winners,'aborted':aborted,'losers':losers,'redo_count':len([t for t in trace if t['phase']=='redo']),
            'undo_count':len(undo),'backfill_count':len([t for t in trace if t['phase']=='redo_backfill']),
            'trace':trace,'result_sha256':checksum,'input_sha256':hashlib.sha256(source.encode()).hexdigest(),
            'late_corrections':late,'uncommitted_corrections':pending,'aborted_corrections':aborted_corrections,
            'readings_available':can_read,
            'readings_before_backfill':readings_before,'readings_after_backfill':readings_after,'reading_comparison':comparison,
            'sampling_version':'bitemporal-sampling-v1',
            'boundary':'Python WAL教学模型；严格写锁、静止检查点、整数键值、日志前缀持久。没有注入真实PostgreSQL崩溃，未执行数据库物理恢复。'}
