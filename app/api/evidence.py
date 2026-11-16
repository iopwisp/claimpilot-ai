from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import StaleDataError

from app.db import Analysis, Document, EvidenceRequest, session
from app.security import identity
from app.workflow import row
from .access import audit, claim_access

api = APIRouter(tags=["evidence"])
ACTIVE = ("OPEN", "SUBMITTED")
FIELDS = "id item status document_id note version updated_at analysis_id"


def requests_for(db, cid):
    return [
        row(item, FIELDS)
        for item in db.scalars(
            select(EvidenceRequest)
            .where(EvidenceRequest.claim_id == cid)
            .order_by(EvidenceRequest.updated_at.desc(), EvidenceRequest.id)
        )
    ]


class NewRequest(BaseModel):
    analysis_id: str
    item: str = Field(min_length=1, max_length=160)


@api.post("/claims/{cid}/evidence", status_code=201)
def create_request(cid: str, body: NewRequest, auth=Depends(identity), db=Depends(session)):
    user = auth[0]
    claim = claim_access(db, user, cid, True)
    if user.role not in ("admin", "reviewer"):
        raise HTTPException(403)
    if claim.job_id != body.analysis_id or claim.status not in ("NEEDS_REVIEW", "READY_FOR_REVIEW"):
        raise HTTPException(409, "Open the current review report")
    report = db.get(Analysis, claim.job_id).result
    if not any(i["name"] == body.item and i["status"] != "PRESENT" for i in report["required_items"]):
        raise HTTPException(422, "Choose a missing or unconfirmed item")
    active = db.scalar(
        select(EvidenceRequest).where(
            EvidenceRequest.claim_id == cid,
            EvidenceRequest.item == body.item,
            EvidenceRequest.status.in_(ACTIVE),
        )
    )
    if active:
        raise HTTPException(409, "This item already has an active request")
    item = EvidenceRequest(claim_id=cid, analysis_id=claim.job_id, item=body.item)
    db.add(item)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Request changed; refresh the case")
    audit(db, user, "evidence.requested", cid, item.id, {"item": item.item, "job_id": claim.job_id})
    db.commit()
    return row(item, FIELDS)


class Decision(BaseModel):
    action: Literal["submit", "accept", "return", "withdraw"]
    version: int = Field(ge=1)
    document_id: str | None = None
    note: str = Field(default="", max_length=2000)


@api.post("/claims/{cid}/evidence/{rid}")
def change_request(cid: str, rid: str, body: Decision, auth=Depends(identity), db=Depends(session)):
    user = auth[0]
    claim = claim_access(db, user, cid, True)
    item = db.get(EvidenceRequest, rid)
    if not item or item.claim_id != cid:
        raise HTTPException(404)
    roles = ("admin", "handler") if body.action == "submit" else ("admin", "reviewer")
    if user.role not in roles:
        raise HTTPException(403)
    if claim.status in ("PROCESSING", "COMPLETED") or item.version != body.version:
        raise HTTPException(409, "Case or request changed. Refresh before continuing.")
    allowed = {
        "submit": ("OPEN",),
        "accept": ("SUBMITTED",),
        "return": ("SUBMITTED",),
        "withdraw": ACTIVE,
    }
    if item.status not in allowed[body.action]:
        raise HTTPException(409, "Request is no longer awaiting this action")
    note = body.note.strip()
    if body.action in ("return", "withdraw") and not note:
        raise HTTPException(422, "Enter a reason")
    if body.action == "submit":
        doc = db.get(Document, body.document_id) if body.document_id else None
        if not doc or doc.claim_id != cid or doc.status != "READY":
            raise HTTPException(422, "Choose a processed document from this case")
        item.document_id = doc.id
    item.status = {
        "submit": "SUBMITTED",
        "return": "OPEN",
        "accept": "ACCEPTED",
        "withdraw": "WITHDRAWN",
    }[body.action]
    item.note = note
    item.version += 1
    audit(
        db,
        user,
        "evidence." + body.action,
        cid,
        rid,
        {"item": item.item, "document_id": item.document_id, "value": note, "version": item.version},
    )
    try:
        db.commit()
    except StaleDataError:
        db.rollback()
        raise HTTPException(409, "Request changed; refresh the case")
    return row(item, FIELDS)
