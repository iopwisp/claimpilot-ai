from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, or_, select

from app.db import Claim, Document, User, session
from app.documents import path_for
from app.schemas import ClaimInput
from app.security import identity
from app.workflow import facts_for, row


from .access import CLAIM, scope, audit, claim_access, editable, reset

api = APIRouter(tags=["claims"])


@api.get("/claims")
def claims(
    q: str = "",
    status: str = "",
    sort: Literal["newest", "oldest", "amount"] = "newest",
    auth=Depends(identity),
    db=Depends(session),
):
    query = select(Claim).where(scope(auth[0]))
    if q:
        query = query.where(
            or_(
                Claim.id == q,
                Claim.claim_number.icontains(q, autoescape=True),
                Claim.policy_number.icontains(q, autoescape=True),
                Claim.claimant_name.icontains(q, autoescape=True),
            )
        )
    if status:
        query = query.where(Claim.status == status)
    query = query.order_by(
        {
            "newest": Claim.created_at.desc(),
            "oldest": Claim.created_at,
            "amount": Claim.claim_amount.desc(),
        }[sort]
    )
    return [row(c, CLAIM) for c in db.scalars(query)]


@api.get("/dashboard")
def dashboard(auth=Depends(identity), db=Depends(session)):
    query = (
        select(func.count(Document.id)).join(Claim).where(scope(auth[0]), Document.status == "QUEUED")
    )
    return {"documents_processing": db.scalar(query)}


@api.post("/claims", status_code=201)
def create(body: ClaimInput, auth=Depends(identity), db=Depends(session)):
    if auth[0].role == "reviewer":
        raise HTTPException(403)
    claim = Claim(**body.model_dump(), created_by=auth[0].id)
    db.add(claim)
    db.flush()
    audit(db, auth[0], "claim.create", claim.id)
    db.commit()
    return row(claim, CLAIM)


@api.get("/claims/{cid}")
def details(cid: str, auth=Depends(identity), db=Depends(session)):
    claim = claim_access(db, auth[0], cid)
    return {**row(claim, CLAIM), "fields": facts_for(db, cid)}


@api.patch("/claims/{cid}")
def update(cid: str, body: dict, auth=Depends(identity), db=Depends(session)):
    claim = claim_access(db, auth[0], cid, True)
    editable(claim, auth[0])
    existing = body.copy()
    if "reviewer_email" in existing:
        email = str(existing.pop("reviewer_email")).lower()
        reviewer = db.scalar(select(User).where(User.email == email, User.role == "reviewer"))
        if not reviewer:
            raise HTTPException(422, "Reviewer not found")
        claim.reviewer_id = reviewer.id
    if existing:
        try:
            changes = ClaimInput.model_validate(
                {**{k: getattr(claim, k) for k in ClaimInput.model_fields}, **existing}
            )
        except ValueError:
            raise HTTPException(422, "Invalid claim fields")
        for k, v in changes.model_dump().items():
            setattr(claim, k, v)
        reset(claim)
    audit(db, auth[0], "claim.update", cid)
    db.commit()
    return row(claim, CLAIM)


@api.delete("/claims/{cid}")
def delete(cid: str, auth=Depends(identity), db=Depends(session)):
    claim = claim_access(db, auth[0], cid, True)
    editable(claim, auth[0])
    if claim.status != "DRAFT":
        raise HTTPException(409, "Only drafts can be deleted")
    docs = db.scalars(select(Document).where(Document.claim_id == cid)).all()
    if any(d.status == "QUEUED" for d in docs):
        raise HTTPException(409, "Document processing in progress")
    paths = [path_for(d) for d in docs]
    db.delete(claim)
    audit(db, auth[0], "claim.delete", cid)
    db.commit()
    for path in paths:
        path.unlink(missing_ok=True)
    return {"ok": True}
