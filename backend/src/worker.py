import traceback,json
from pathlib import Path
from sqlalchemy import select
from src.config.database import Session
from src.models.entities import Report
from src.services.reports import queue
from src.services.normalization import analyze
from src.config.settings import ARTIFACTS_DIR
BLOCKED=('withdrawing','withdrawn')

def process(ident):
    try:
        with Session() as db:
            obj=db.execute(select(Report).where(Report.id==ident).with_for_update()).scalar_one_or_none()
            if not obj or obj.status in BLOCKED or obj.status!='queued':return
            obj.status='running';db.commit();snapshot=obj.input_snapshot
        result=analyze(snapshot['relation']['attributes'],snapshot['dependencies'])
        artifact=Path(ARTIFACTS_DIR)/f'report-{ident}.json'
        with Session() as db:
            # Hold the row lock across the file write so a concurrent purge cannot interleave.
            obj=db.execute(select(Report).where(Report.id==ident).with_for_update()).scalar_one_or_none()
            if not obj or obj.status in BLOCKED:
                # A withdrawal won the race: never write stale results back.
                artifact.unlink(missing_ok=True);db.rollback();return
            obj.result=result;obj.status='completed'
            artifact.write_text(json.dumps(result,ensure_ascii=False,indent=2))
            db.commit()
    except Exception as e:
        traceback.print_exc()
        with Session() as db:
            obj=db.execute(select(Report).where(Report.id==ident).with_for_update()).scalar_one_or_none()
            if obj and obj.status not in BLOCKED:obj.status='failed';obj.error=str(e);db.commit()

def main():
    while True:
        Path('/tmp/worker-heartbeat').touch()
        item=queue.blpop('schemaworkbook:queue',timeout=2)
        if not item:continue
        process(int(item[1]))

if __name__=='__main__':main()
