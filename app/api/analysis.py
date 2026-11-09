from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field as Input
from sqlalchemy import select

from app.ai.provider import provider
from app.db import Analysis, Audit, Document, Field, Inconsistency, session, uid
from app.documents import search_policy
from app.schemas import Review
from app.security import identity
from app.workflow import row


from .access import CLAIM, audit, claim_access, editable, dispatch

api = APIRouter(tags=["analysis"])


@api.post("/claims/{cid}/analyze", status_code=202)
def analyze_claim(cid: str, auth=Depends(identity), db=Depends(session)):
    claim = claim_access(db, auth[0], cid, True)
    editable(claim, auth[0])
    docs = db.scalars(select(Document).where(Document.claim_id == cid)).all()
    if not docs or any(d.status != "READY" for d in docs):
        raise HTTPException(409, "Upload documents and finish processing first")
    claim.job_id = uid()
    claim.status = "PROCESSING"
    audit(db, auth[0], "analysis.start", cid, claim.job_id)
    dispatch(db, "analysis", claim, claim.job_id)
    return row(claim, "job_id status")


@api.get("/claims/{cid}/analysis")
@api.get("/claims/{cid}/report")
def report(cid: str, auth=Depends(identity), db=Depends(session)):
    claim = claim_access(db, auth[0], cid)
    a = db.get(Analysis, claim.job_id) if claim.job_id else None
    return {
        "job_id": claim.job_id,
        "status": claim.status,
        "report": a.result if a else None,
        "model": a.model if a else None,
    }


class Question(BaseModel):
    question: str = Input(min_length=3, max_length=1000)


@api.post("/claims/{cid}/policy-search")
def search(cid: str, body: Question, auth=Depends(identity), db=Depends(session)):
    claim_access(db, auth[0], cid)
    result = search_policy(db, cid, body.question, provider())
    audit(db, auth[0], "policy.search", cid)
    db.commit()
    return result


@api.post("/claims/{cid}/review")
def review(cid: str, body: Review, auth=Depends(identity), db=Depends(session)):
    claim = claim_access(db, auth[0], cid, True)
    if auth[0].role not in ("reviewer", "admin"):
        raise HTTPException(403)
    if claim.status not in ("NEEDS_REVIEW", "READY_FOR_REVIEW"):
        raise HTTPException(409, "Analysis required before review")
    if body.action in ("correct_field", "accept_field"):
        field = db.scalar(
            select(Field).join(Document).where(Field.id == body.target, Document.claim_id == cid)
        )
        if not field or (body.action == "correct_field" and not body.value.strip()):
            raise HTTPException(422, "Field and correction required")
        if body.action == "correct_field":
            field.corrected = body.value.strip()
        field.review = "CORRECTED" if field.corrected else "ACCEPTED"
    elif body.action == "reject_recommendation":
        previous = db.get(Analysis, claim.job_id)
        if body.target not in {r["id"] for r in previous.result["recommendations"]}:
            raise HTTPException(422, "Unknown recommendation")
    elif body.action == "comment" and not body.value.strip():
        raise HTTPException(422, "Enter a comment")
    elif body.action == "complete":
        claim.status = "COMPLETED"
        db.query(Inconsistency).filter_by(analysis_id=claim.job_id).update({"review_status": "REVIEWED"})
    audit(
        db,
        auth[0],
        "review." + body.action,
        cid,
        body.target,
        {"value": body.value, "job_id": claim.job_id},
    )
    db.commit()
    return row(claim, CLAIM)


@api.get("/claims/{cid}/audit")
def history(cid: str, auth=Depends(identity), db=Depends(session)):
    claim_access(db, auth[0], cid)
    return [
        row(a, "action entity_id user_id details created_at")
        for a in db.scalars(select(Audit).where(Audit.claim_id == cid).order_by(Audit.created_at.desc()))
    ]
