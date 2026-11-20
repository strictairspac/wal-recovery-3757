from sqlalchemy import select
from fastapi import HTTPException
from src.models.entities import LogSet
from src.services.wal_engine import validate,readings,handovers
from src.utils.serialize import record

def list_log_sets(db):return [record(x) for x in db.scalars(select(LogSet).order_by(LogSet.id))]

def get_log_set(db,ident):
    obj=db.get(LogSet,ident)
    if obj is None:raise HTTPException(404,'日志集不存在')
    return obj

def _validated(initial,records,sample_times):
    try:validate(initial,records,sample_times)
    except ValueError as exc:raise HTTPException(422,str(exc))

def create_log_set(db,data):
    values=data.model_dump()
    values['records']=[{k:v for k,v in r.items() if v is not None} for r in values['records']]
    _validated(values['initial'],values['records'],values['sample_times'])
    obj=LogSet(**values);db.add(obj);db.flush();return record(obj)

def log_set_readings(db,ident,at=None,commit_lsn=None,key=None,include_corrections=True,compare=False):
    obj=get_log_set(db,ident)
    try:return readings(obj.initial,obj.records,obj.sample_times,at,commit_lsn,key,include_corrections,compare)
    except ValueError as exc:raise HTTPException(422,str(exc))

def log_set_handovers(db,ident,commit_lsn=None):
    obj=get_log_set(db,ident)
    try:return handovers(obj.initial,obj.records,obj.sample_times,commit_lsn)
    except ValueError as exc:raise HTTPException(422,str(exc))

def add_corrections(db,ident,data):
    """Derive a new log set by appending one correction transaction to the parent's log.

    Every item is written inside the same transaction, so all of them become visible at the
    same commit position — a single submission spanning several sampling instants takes effect
    together.  ``commit=False`` leaves the transaction open, which keeps the corrections out
    of the ledger for the uncommitted case.
    """
    parent=get_log_set(db,ident)
    used={r.get('tx') for r in parent.records if r.get('op')=='begin'}
    if data.tx in used:raise HTTPException(422,f'事务标识{data.tx}已在该日志集中使用')
    if not parent.sample_times:
        raise HTTPException(422,'该日志集未声明采样时刻，无法把校正补进原采样时段')
    appended=[{'op':'begin','tx':data.tx}]
    for item in data.corrections:
        appended.append({'op':'correct','tx':data.tx,'key':item.key,'value':item.value,'start':item.start,'end':item.end})
    if data.commit:appended.append({'op':'commit','tx':data.tx})
    records=list(parent.records)+appended
    _validated(parent.initial,records,parent.sample_times)
    if db.scalar(select(LogSet).where(LogSet.name==data.name)) is not None:raise HTTPException(409,'日志集名称已存在')
    obj=LogSet(name=data.name,description=data.description or f'{parent.name}的迟到校正',initial=parent.initial,
               records=records,sample_times=parent.sample_times,parent_log_set_id=parent.id)
    db.add(obj);db.flush();return record(obj)
