"""Create an owned case from the same fictional PDFs shipped with the demo."""

from pathlib import Path
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from app.db import Audit, Claim, User, session
from app.documents import path_for
from app.jobs import enqueue
from app.schemas import ClaimInput
from app.security import identity
from app.workflow import row
from .access import CLAIM, audit
from .documents import stage_document

api = APIRouter(tags=["samples"])
ROOT = Path(__file__).resolve().parents[2] / "demo"


class SampleInput(BaseModel):
    scenario: Literal["01-complete", "02-date-mismatch", "03-missing-evidence"]
    request_id: UUID


@api.post("/samples", status_code=201)
def import_sample(body: SampleInput, auth=Depends(identity), db=Depends(session)):
    user = auth[0]
    if user.role not in ("handler", "admin"):
        raise HTTPException(403)
    db.execute(select(User.id).where(User.id == user.id).with_for_update())
    key = body.request_id.hex
    existing = db.get(Claim, key)
    if existing:
        recorded = db.scalar(
            select(Audit).where(
                Audit.claim_id == key, Audit.action == "sample.import", Audit.user_id == user.id
            )
        )
        if (
            existing.created_by != user.id
            or not recorded
            or recorded.details.get("scenario") != body.scenario
        ):
            raise HTTPException(409, "Import identifier already used")
        return row(existing, CLAIM)
    folder = ROOT / body.scenario
    values = ClaimInput.model_validate_json((folder / "claim.json").read_bytes())
    claim = Claim(id=key, created_by=user.id, **values.model_dump())
    db.add(claim)
    db.flush()
    docs = []
    try:
        for file in sorted(folder.glob("*.pdf")):
            docs.append(stage_document(db, claim, user, file.name, "application/pdf", file.read_bytes()))
        audit(db, user, "sample.import", claim.id, details={"scenario": body.scenario})
        db.commit()
    except Exception:
        db.rollback()
        for doc in docs:
            path_for(doc).unlink(missing_ok=True)
        raise
    for doc in docs:
        try:
            enqueue("document", doc.id, doc.id)
        except Exception:
            db.refresh(doc, with_for_update=True)
            if doc.status == "QUEUED":
                doc.status = "FAILED"
                audit(db, user, "document.queue_failed", claim.id, doc.id)
            db.commit()
    return row(claim, CLAIM)
