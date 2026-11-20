from sqlalchemy import Column,Integer,String,JSON,DateTime,ForeignKey,Text,UniqueConstraint
from datetime import datetime,timezone
from src.config.database import Base
class User(Base):
    __tablename__='users'
    id=Column(Integer,primary_key=True);email=Column(String(120),unique=True,nullable=False);password=Column(String(300),nullable=False);role=Column(String(20),nullable=False)
class Relation(Base):
    __tablename__='relations'
    id=Column(Integer,primary_key=True);code=Column(String(80),unique=True,nullable=False);title=Column(String(160),nullable=False);attributes=Column(JSON,nullable=False);note=Column(String(300),default='')
class Dependency(Base):
    __tablename__='dependencies'
    id=Column(Integer,primary_key=True);relation_id=Column(Integer,ForeignKey('relations.id'),nullable=False);lhs=Column(JSON,nullable=False);rhs=Column(JSON,nullable=False);note=Column(String(300),default='')
class Report(Base):
    __tablename__='reports'
    id=Column(Integer,primary_key=True);name=Column(String(120),nullable=False);relation_id=Column(Integer,ForeignKey('relations.id'),nullable=False)
    status=Column(String(20),nullable=False,default='queued');input_snapshot=Column(JSON,nullable=False);result=Column(JSON,nullable=True);error=Column(Text,nullable=True)
    created_at=Column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))
class Withdrawal(Base):
    """按草案与保密字段发起的撤回批次；登记幂等，清理可续跑。"""
    __tablename__='withdrawals'
    id=Column(Integer,primary_key=True)
    relation_id=Column(Integer,ForeignKey('relations.id'),nullable=False)
    field=Column(String(40),nullable=False)
    status=Column(String(20),nullable=False,default='pending')
    phase=Column(String(20),nullable=False,default='registered')
    batch_key=Column(String(200),unique=True,nullable=False)
    requested_by=Column(String(120),nullable=False,default='')
    last_error=Column(Text,nullable=True)
    created_at=Column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))
    updated_at=Column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc),onupdate=lambda:datetime.now(timezone.utc))
class WithdrawalMember(Base):
    """批次影响的报告清单，预登记保证重试不重复、不误伤其他草案。"""
    __tablename__='withdrawal_members'
    id=Column(Integer,primary_key=True)
    withdrawal_id=Column(Integer,ForeignKey('withdrawals.id'),nullable=False)
    report_id=Column(Integer,ForeignKey('reports.id'),nullable=False)
    created_at=Column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))
    __table_args__=(UniqueConstraint('withdrawal_id','report_id',name='uq_withdrawal_member'),)
class Audit(Base):
    __tablename__='audit_logs'
    id=Column(Integer,primary_key=True);actor=Column(String(120),nullable=False);action=Column(String(160),nullable=False);created_at=Column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))
