from fastapi import HTTPException
from sqlalchemy import or_, select

from app.db import Audit, Claim
from app.jobs import enqueue


CLAIM = "id claim_number claimant_name policy_number incident_date incident_description claim_amount currency status created_at updated_at reviewer_id job_id"
DOC = "id filename kind status metadata_json uploaded_at"


def audit(db, user, action, claim=None, entity=None, details=None):
    db.add(
        Audit(user_id=user.id, action=action, claim_id=claim, entity_id=entity, details=details or {})
    )


def scope(user):
    if user.role == "admin":
        return True
    return (
        or_(Claim.created_by == user.id, Claim.reviewer_id == user.id)
        if user.role == "reviewer"
        else Claim.created_by == user.id
    )


def claim_access(db, user, cid, write=False):
    q = select(Claim).where(Claim.id == cid, scope(user))
    claim = db.scalar(q.with_for_update() if write else q)
    if not claim:
        raise HTTPException(404, "Claim not found")
    return claim


def editable(claim, user):
    if user.role not in ("handler", "admin") or claim.status in ("COMPLETED", "PROCESSING"):
        raise HTTPException(409, "Claim cannot be edited in this state")


def reset(claim):
    claim.status = "DRAFT"
    claim.job_id = None


def dispatch(db, kind, obj, job):
    db.commit()
    try:
        enqueue(kind, obj.id, job)
    except Exception:
        obj.status = "FAILED"
        db.commit()
        raise HTTPException(503, "Queue unavailable. Retry when the worker is available.")
