import logging
import os
from concurrent.futures import ThreadPoolExecutor
from celery import Celery
from sqlalchemy import select

from .ai.provider import VERSION, provider
from .db import Analysis, Audit, Claim, Document, Inconsistency, Session
from .documents import process
from .workflow import analyze

queue = Celery("claimpilot", broker=os.getenv("REDIS_URL", "redis://redis:6379/0"))
queue.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
)
executor = ThreadPoolExecutor(max_workers=2)
log = logging.getLogger(__name__)


@queue.task(name="claimpilot.process")
def run(kind, entity, job):
    with Session() as db:
        try:
            if kind == "document":
                obj = db.scalar(select(Document).where(Document.id == entity).with_for_update())
                if not obj or obj.status != "QUEUED":
                    return
                process(db, obj)
                claim_id = obj.claim_id
            else:
                obj = db.scalar(select(Claim).where(Claim.id == entity).with_for_update())
                if not obj or obj.job_id != job or obj.status != "PROCESSING":
                    return
                ai = provider()
                result = analyze(db, obj, ai)
                db.add(
                    Analysis(
                        id=job, claim_id=entity, result=result, model=ai.model, prompt_version=VERSION
                    )
                )
                db.flush()
                for issue in result["inconsistencies"]:
                    db.add(
                        Inconsistency(
                            analysis_id=job,
                            type=issue["type"],
                            severity=issue["severity"],
                            description=issue["description"],
                            evidence=issue["values"],
                        )
                    )
                attention = result["recommendations"] or any(
                    x["status"] != "PRESENT" for x in result["required_items"]
                )
                obj.status = "NEEDS_REVIEW" if attention else "READY_FOR_REVIEW"
                claim_id = entity
            db.add(Audit(action=kind + ".processed", claim_id=claim_id, entity_id=entity))
            db.commit()
        except Exception as error:
            db.rollback()
            obj = db.get(Document if kind == "document" else Claim, entity)
            if obj and (kind == "document" or obj.job_id == job):
                obj.status = "FAILED"
                db.add(
                    Audit(
                        action=kind + ".failed",
                        entity_id=entity,
                        claim_id=obj.claim_id if kind == "document" else entity,
                        details={"error_type": type(error).__name__},
                    )
                )
                db.commit()
            log.error('{"event":"job_failed","id":"%s","error_type":"%s"}', entity, type(error).__name__)


def enqueue(kind, entity, job):
    if os.getenv("REDIS_URL"):
        run.apply_async(args=(kind, entity, job), task_id=job, retry=False)
    elif os.getenv("JOBS_INLINE") == "1":
        run(kind, entity, job)
    else:
        executor.submit(run, kind, entity, job)
