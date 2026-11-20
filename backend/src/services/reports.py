from sqlalchemy import select
from redis import Redis
from fastapi import HTTPException
from src.models.entities import Relation,Dependency,Report
from src.config.settings import REDIS_URL
from src.constants.enums import RUN_STATES
from src.utils.serialization import record
from .common import save
from . import withdrawals
queue=Redis.from_url(REDIS_URL,decode_responses=True)

def _view(db,obj,links):
    item=record(obj);summaries=links.get(obj.id) or []
    item['withdrawal']=summaries[-1] if summaries else None
    if obj.status in withdrawals.BLOCKED_REPORT_STATES:
        # Access stops immediately: no snapshot, result or error leaves the database.
        item['input_snapshot']=None;item['result']=None;item['error']=None
    return item

def listing(db):
    items=list(db.scalars(select(Report).order_by(Report.id.desc())))
    links=withdrawals.links(db,[x.id for x in items])
    return [_view(db,obj,links) for obj in items]

def detail(db,ident):
    obj=db.get(Report,ident)
    if not obj:raise HTTPException(404,'报告不存在')
    return _view(db,obj,withdrawals.links(db,[obj.id]))

def create(db,data,user):
    relation=db.execute(select(Relation).where(Relation.id==data.relation_id).with_for_update()).scalar_one_or_none()
    if not relation:raise HTTPException(404,'关系不存在')
    blocked=withdrawals.blocking_withdrawal(db,relation)
    if blocked:
        raise HTTPException(409,f'草案 {relation.code} 的字段「{blocked.field}」已发起撤回，含该字段的新报告暂停受理')
    deps=list(db.scalars(select(Dependency).where(Dependency.relation_id==relation.id)))
    snapshot={'relation':record(relation),'dependencies':[{'lhs':x.lhs,'rhs':x.rhs} for x in deps]}
    obj=Report(**data.model_dump(),input_snapshot=snapshot,status=RUN_STATES[0]);save(db,obj,user,'范式分解入队 '+data.name)
    try:queue.rpush('schemaworkbook:queue',str(obj.id))
    except Exception:
        obj.status='failed';obj.error='队列暂时不可用，请重新创建';db.commit();raise HTTPException(503,obj.error)
    return detail(db,obj.id)
