"""Retraction of a confidential field: batch registration, immediate access stop and resumable purge."""
from pathlib import Path
from sqlalchemy import select,func
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException
from src.models.entities import Relation,Dependency,Report,Withdrawal,WithdrawalMember,Audit
from src.config.settings import ARTIFACTS_DIR
from src.utils.serialization import record

BLOCKED_REPORT_STATES=('withdrawing','withdrawn')

def _norm(value): return (value or '').strip()
def _same(a,b): return _norm(a)==_norm(b) or _norm(a).casefold()==_norm(b).casefold()

def snapshot_contains_field(snapshot,field):
    """Only a report's own frozen snapshot counts; other drafts are never scanned."""
    snapshot=snapshot or {}
    relation=snapshot.get('relation') or {}
    if any(_same(x,field) for x in (relation.get('attributes') or [])):return True
    for dependency in snapshot.get('dependencies') or []:
        if any(_same(x,field) for x in (dependency.get('lhs') or [])+(dependency.get('rhs') or [])):return True
    return False

def _artifact(report_id): return Path(ARTIFACTS_DIR)/f'report-{int(report_id)}.json'

def links(db,report_ids):
    """Map report id -> withdrawal summaries for redaction and status display."""
    if not report_ids:return {}
    rows=db.execute(
        select(WithdrawalMember.report_id,Withdrawal)
        .join(Withdrawal,Withdrawal.id==WithdrawalMember.withdrawal_id)
        .where(WithdrawalMember.report_id.in_(list(report_ids)))
        .order_by(Withdrawal.id)
    ).all()
    result={}
    for report_id,withdrawal in rows:
        result.setdefault(report_id,[]).append({'id':withdrawal.id,'relation_id':withdrawal.relation_id,'field':withdrawal.field,'status':withdrawal.status,'phase':withdrawal.phase})
    return result

def _summary(db,withdrawal):
    item=record(withdrawal)
    item['report_count']=db.scalar(select(func.count()).select_from(WithdrawalMember).where(WithdrawalMember.withdrawal_id==withdrawal.id)) or 0
    item['withdrawn_count']=db.scalar(
        select(func.count()).select_from(WithdrawalMember)
        .join(Report,Report.id==WithdrawalMember.report_id)
        .where(WithdrawalMember.withdrawal_id==withdrawal.id,Report.status=='withdrawn')
    ) or 0
    return item

def listing(db):
    return [_summary(db,x) for x in db.scalars(select(Withdrawal).order_by(Withdrawal.id.desc()))]

def detail(db,ident):
    obj=db.get(Withdrawal,ident)
    if not obj:raise HTTPException(404,'撤回批次不存在')
    return _summary(db,obj)

def blocking_withdrawal(db,relation):
    """A retraction for this draft pauses new reports that would include the same field."""
    deps=list(db.scalars(select(Dependency).where(Dependency.relation_id==relation.id)))
    fields=set(relation.attributes or [])
    for dependency in deps:fields.update(dependency.lhs or []);fields.update(dependency.rhs or [])
    withdrawals=list(db.scalars(select(Withdrawal).where(Withdrawal.relation_id==relation.id)))
    for withdrawal in withdrawals:
        if any(_same(withdrawal.field,field) for field in fields):return withdrawal
    return None

def _field_known(db,relation,field):
    deps=list(db.scalars(select(Dependency).where(Dependency.relation_id==relation.id)))
    fields=set(relation.attributes or [])
    for dependency in deps:fields.update(dependency.lhs or []);fields.update(dependency.rhs or [])
    if any(_same(field,x) for x in fields):return True
    if any(snapshot_contains_field(x.input_snapshot,field) for x in db.scalars(select(Report).where(Report.relation_id==relation.id))):return True
    return False

def _affected_reports(db,relation_id,field):
    reports=list(db.scalars(select(Report).where(Report.relation_id==relation_id).with_for_update()))
    return [report for report in reports if snapshot_contains_field(report.input_snapshot,field)]

def _register(db,relation,field,user):
    batch_key=f'{relation.id}:{_norm(field).casefold()}'
    withdrawal=db.scalar(select(Withdrawal).where(Withdrawal.batch_key==batch_key).with_for_update())
    if withdrawal is None:
        withdrawal=Withdrawal(relation_id=relation.id,field=_norm(field),status='pending',phase='registered',batch_key=batch_key,requested_by=user.email)
        db.add(withdrawal);db.flush()
        db.add(Audit(actor=user.email,action=f'发起撤回 {relation.code} 字段 {_norm(field)}'))
    affected=_affected_reports(db,relation.id,field)
    known=set(db.scalars(select(WithdrawalMember.report_id).where(WithdrawalMember.withdrawal_id==withdrawal.id)))
    for report in affected:
        if report.id not in known:db.add(WithdrawalMember(withdrawal_id=withdrawal.id,report_id=report.id))
        if report.status not in BLOCKED_REPORT_STATES:report.status='withdrawing'  # access stops before any purge work starts
    db.commit()
    return withdrawal

def _purge(db,withdrawal):
    withdrawal.status='purging';withdrawal.phase='purging';withdrawal.last_error=None;db.commit()
    members=list(db.scalars(select(WithdrawalMember).where(WithdrawalMember.withdrawal_id==withdrawal.id)))
    for member in members:
        report=db.execute(select(Report).where(Report.id==member.report_id).with_for_update()).scalar_one_or_none()
        if not report:continue
        try:
            _artifact(report.id).unlink(missing_ok=True)
        except OSError as exc:
            withdrawal.status='failed';withdrawal.phase='failed';withdrawal.last_error=f'留存文件未能清理：{exc}'
            db.commit();return withdrawal
        report.input_snapshot={};report.result=None;report.error=None;report.status='withdrawn'
        db.commit()
    withdrawal.status='withdrawn';withdrawal.phase='done';withdrawal.last_error=None
    db.commit()
    return withdrawal

def _finish(db,relation,field,withdrawal,user):
    # Re-scan under the same batch key so an interrupted or raced member is picked up, never duplicated.
    withdrawal=_register(db,relation,field,user)
    db.add(Audit(actor=user.email,action=f'继续撤回批次 #{withdrawal.id} 字段 {withdrawal.field}'));db.commit()
    return _summary(db,_purge(db,withdrawal))

def _safe_register(db,relation,field,user):
    try:
        return _register(db,relation,field,user)
    except IntegrityError:
        # A concurrent request registered the same (draft, field) batch first; reuse it.
        db.rollback()
        try:return _register(db,relation,field,user)
        except IntegrityError:
            db.rollback();raise HTTPException(409,'撤回批次登记冲突，请重试')

def create(db,data,user):
    relation=db.execute(select(Relation).where(Relation.id==data.relation_id).with_for_update()).scalar_one_or_none()
    if not relation:raise HTTPException(404,'关系不存在')
    field=_norm(data.field)
    if not field:raise HTTPException(422,'请指定需要撤回的保密字段')
    batch_key=f'{relation.id}:{field.casefold()}'
    existing=db.scalar(select(Withdrawal).where(Withdrawal.batch_key==batch_key))
    if not existing and not _field_known(db,relation,field):
        raise HTTPException(422,f'草案 {relation.code} 中不存在字段「{field}」，未发起撤回')
    withdrawal=_safe_register(db,relation,field,user)
    return _summary(db,_purge(db,withdrawal))

def resume(db,ident,user):
    withdrawal=db.get(Withdrawal,ident)
    if not withdrawal:raise HTTPException(404,'撤回批次不存在')
    if withdrawal.status=='withdrawn':return _summary(db,withdrawal)
    relation=db.execute(select(Relation).where(Relation.id==withdrawal.relation_id).with_for_update()).scalar_one_or_none()
    if not relation:raise HTTPException(404,'关系不存在')
    return _finish(db,relation,withdrawal.field,withdrawal,user)
