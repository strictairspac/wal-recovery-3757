from sqlalchemy import select
from fastapi import HTTPException
from src.models.entities import Recovery,CrashCase,LogSet
from src.services.wal_engine import readings,handovers
from src.utils.serialize import record

def list_recoveries(db):return [record(x) for x in db.scalars(select(Recovery).order_by(Recovery.id.desc()).limit(100))]
def get_recovery(db,ident):
    obj=db.get(Recovery,ident)
    if obj is None:raise HTTPException(404,'恢复记录不存在')
    return obj
def create_recovery(db,data):
    case=db.get(CrashCase,data.crash_case_id)
    if case is None:raise HTTPException(404,'故障场景不存在')
    if len(db.scalars(select(Recovery.id).where(Recovery.status.in_(['queued','running']))).all())>=20:raise HTTPException(429,'待处理配额20已满')
    logs=db.get(LogSet,case.log_set_id)
    obj=Recovery(**data.model_dump(),status='queued',snapshot={'log_set':record(logs),'case':record(case)})
    db.add(obj);db.flush();return obj
def _point(job,commit_lsn):
    """The drill only shows log positions that were durable at its crash point."""
    crash=job.snapshot['case']['crash_after']
    if commit_lsn is None:return crash
    if isinstance(commit_lsn,bool) or not isinstance(commit_lsn,int) or not 0<=commit_lsn<=crash:
        raise HTTPException(422,'提交位置超出该演练的断电点')
    return commit_lsn
def recovery_readings(db,ident,at=None,commit_lsn=None,key=None,compare=True):
    """Query the drill's frozen snapshot by sampling instant and commit position."""
    job=get_recovery(db,ident);logs=job.snapshot['log_set']
    try:return readings(logs['initial'],logs['records'],logs.get('sample_times'),at,_point(job,commit_lsn),key,True,compare)
    except ValueError as exc:raise HTTPException(422,str(exc))
def recovery_handovers(db,ident,commit_lsn=None):
    """Handover ledgers from the frozen snapshot, including the ones older than its latest checkpoint."""
    job=get_recovery(db,ident);logs=job.snapshot['log_set']
    try:return handovers(logs['initial'],logs['records'],logs.get('sample_times'),_point(job,commit_lsn))
    except ValueError as exc:raise HTTPException(422,str(exc))
