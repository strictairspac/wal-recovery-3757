from fastapi import APIRouter, Depends, HTTPException
from src.config.database import get_db
from src.middlewares.auth import current_user,writable
from src.schemas.crash_case import CrashCaseInput
from src.services.crash_case_service import list_crash_cases,create_crash_case,crash_case_readings,crash_case_handovers
from src.controllers.actions import audit
router=APIRouter()
@router.get('/crash-cases')
def listing(db=Depends(get_db),user=Depends(current_user)):return list_crash_cases(db)
@router.post('/crash-cases',status_code=201)
def create(data:CrashCaseInput,db=Depends(get_db),user=Depends(writable)):
    out=create_crash_case(db,data)
    audit(db,user,'crash_case:create');db.commit();return out
@router.get('/crash-cases/{ident}/readings')
def readings(ident:int,at:str|None=None,commit_lsn:int|None=None,key:str|None=None,corrections:bool=True,compare:bool=False,
             db=Depends(get_db),user=Depends(current_user)):
    return crash_case_readings(db,ident,at,commit_lsn,key,corrections,compare)
@router.get('/crash-cases/{ident}/handovers')
def handovers(ident:int,commit_lsn:int|None=None,db=Depends(get_db),user=Depends(current_user)):
    return crash_case_handovers(db,ident,commit_lsn)
