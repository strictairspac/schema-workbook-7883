from fastapi import APIRouter,Depends
from src.config.database import db_session
from src.utils.security import current,writer
from src.schemas.withdrawal import WithdrawalInput
from src.services import withdrawals as service
router=APIRouter()
@router.get('/withdrawals')
def listing(db=Depends(db_session),user=Depends(current)):return service.listing(db)
@router.get('/withdrawals/{ident}')
def detail(ident:int,db=Depends(db_session),user=Depends(current)):return service.detail(db,ident)
@router.post('/withdrawals',status_code=201)
def create(data:WithdrawalInput,db=Depends(db_session),user=Depends(writer)):return service.create(db,data,user)
@router.post('/withdrawals/{ident}/resume')
def resume(ident:int,db=Depends(db_session),user=Depends(writer)):return service.resume(db,ident,user)
