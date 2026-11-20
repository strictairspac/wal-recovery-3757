from fastapi import APIRouter, Depends, HTTPException
from src.config.database import get_db
from src.middlewares.auth import current_user,writable
from src.schemas.log_set import LogSetInput,CorrectionInput
from src.services.log_set_service import list_log_sets,create_log_set,log_set_readings,log_set_handovers,add_corrections
from src.controllers.actions import audit
router=APIRouter()

@router.get('/log-sets')
def listing(db=Depends(get_db),user=Depends(current_user)):return list_log_sets(db)

@router.post('/log-sets',status_code=201)
def create(data:LogSetInput,db=Depends(get_db),user=Depends(writable)):
    out=create_log_set(db,data)
    audit(db,user,'log_set:create');db.commit();return out

@router.get('/log-sets/{ident}/readings')
def readings(ident:int,at:str|None=None,commit_lsn:int|None=None,key:str|None=None,corrections:bool=True,compare:bool=False,
             db=Depends(get_db),user=Depends(current_user)):
    return log_set_readings(db,ident,at,commit_lsn,key,corrections,compare)

@router.get('/log-sets/{ident}/handovers')
def handover_ledgers(ident:int,commit_lsn:int|None=None,db=Depends(get_db),user=Depends(current_user)):
    return log_set_handovers(db,ident,commit_lsn)

@router.post('/log-sets/{ident}/corrections',status_code=201)
def correct(ident:int,data:CorrectionInput,db=Depends(get_db),user=Depends(writable)):
    out=add_corrections(db,ident,data)
    audit(db,user,f'log_set:correction:{out["id"]}:{data.tx}');db.commit();return out
