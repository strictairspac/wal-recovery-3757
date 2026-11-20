from sqlalchemy import select
from fastapi import HTTPException
from src.models.entities import CrashCase,LogSet
from src.services.wal_engine import readings,handovers
from src.utils.serialize import record

def list_crash_cases(db):return [record(x) for x in db.scalars(select(CrashCase).order_by(CrashCase.id))]
def get_crash_case(db,ident):
    obj=db.get(CrashCase,ident)
    if obj is None:raise HTTPException(404,'故障场景不存在')
    return obj
def create_crash_case(db,data):
    logs=db.get(LogSet,data.log_set_id)
    if logs is None:raise HTTPException(404,'日志集不存在')
    if data.crash_after>len(logs.records):raise HTTPException(422,'崩溃点超过日志条数')
    obj=CrashCase(**data.model_dump());db.add(obj);db.flush();return record(obj)
def crash_case_readings(db,ident,at=None,commit_lsn=None,key=None,include_corrections=True,compare=False):
    """Read the scenario's ledger by sampling instant and commit position (default: the crash point)."""
    case=get_crash_case(db,ident);logs=db.get(LogSet,case.log_set_id)
    try:return readings(logs.initial,logs.records,logs.sample_times,at,
                        case.crash_after if commit_lsn is None else commit_lsn,key,include_corrections,compare)
    except ValueError as exc:raise HTTPException(422,str(exc))
def crash_case_handovers(db,ident,commit_lsn=None):
    """Handover ledgers up to the scenario's crash point, including checkpoints before the latest."""
    case=get_crash_case(db,ident);logs=db.get(LogSet,case.log_set_id)
    try:return handovers(logs.initial,logs.records,logs.sample_times,
                         case.crash_after if commit_lsn is None else commit_lsn)
    except ValueError as exc:raise HTTPException(422,str(exc))
