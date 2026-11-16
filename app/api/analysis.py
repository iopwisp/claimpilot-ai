from collections import Counter
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field as Input
from sqlalchemy import select

from app.ai.provider import provider
from app.db import Analysis, Audit, Document, EvidenceRequest, Field, Inconsistency, session, uid
from app.documents import search_policy
from app.evidence_lab import evidence_lab, recovery_packet
from app.schemas import ClaimInput, Review
from app.security import identity
from app.workflow import COMPARED_FIELDS, facts_for, field_issues, normalized, row


from .access import CLAIM, audit, claim_access, editable, dispatch
from .evidence import ACTIVE

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
    result = {
        "job_id": claim.job_id,
        "status": claim.status,
        "report": a.result if a else None,
        "model": a.model if a else None,
    }
    if a:
        facts = facts_for(db, cid)
        initial = a.result["inconsistencies"]
        current = field_issues(claim, facts)
        active_keys = {(item["field"], item["type"]) for item in current}
        resolved = [
            item
            for item in initial
            if item["field"] in COMPARED_FIELDS and (item["field"], item["type"]) not in active_keys
        ]
        current.extend(item for item in initial if item["field"] not in COMPARED_FIELDS)
        result.update(
            prompt_version=a.prompt_version,
            analyzed_at=a.created_at,
            review={
                "fields": facts,
                "current_issues": current,
                "resolved_issues": resolved,
                "reviewed_fields": sum(f["review"] != "UNREVIEWED" for f in facts),
                "actions": [
                    row(event, "action entity_id user_id details created_at")
                    for event in db.scalars(
                        select(Audit)
                        .where(Audit.claim_id == cid, Audit.action.startswith("review."))
                        .order_by(Audit.created_at)
                    )
                    if event.details.get("job_id") == a.id
                ],
            },
        )
    return result


class Question(BaseModel):
    question: str = Input(min_length=3, max_length=1000)


@api.get("/claims/{cid}/analyses")
def versions(cid: str, auth=Depends(identity), db=Depends(session)):
    claim = claim_access(db, auth[0], cid)
    query = (
        select(Analysis.id, Analysis.model, Analysis.prompt_version, Analysis.created_at)
        .where(Analysis.claim_id == cid)
        .order_by(Analysis.created_at.desc(), Analysis.id.desc())
    )
    return [
        {**dict(version), "current": version.id == claim.job_id}
        for version in db.execute(query).mappings()
    ]


def changes(before, after):
    def by_item(result):
        return {item["name"]: item["status"] for item in result["required_items"]}

    old, new = by_item(before), by_item(after)
    # Findings can repeat for one field, e.g. several duplicate documents.

    def counts(result):
        return Counter((item["type"], item["field"]) for item in result["inconsistencies"])

    previous, current = counts(before), counts(after)
    old_docs = {d["id"]: d for d in before["documents"]}
    new_docs = {d["id"]: d for d in after["documents"]}
    return {
        "added_documents": [d for k, d in new_docs.items() if k not in old_docs],
        "removed_documents": [d for k, d in old_docs.items() if k not in new_docs],
        "materials": [
            {"name": name, "before": old.get(name), "after": new.get(name)}
            for name in sorted(old.keys() | new.keys())
            if old.get(name) != new.get(name)
        ],
        "findings": [
            {
                "type": kind,
                "field": field,
                "before": previous[kind, field],
                "after": current[kind, field],
            }
            for kind, field in sorted(previous.keys() | current.keys())
            if previous[kind, field] != current[kind, field]
        ],
        "policy_changed": before["policy"] != after["policy"],
    }


def saved_analysis(db, user, cid, aid):
    claim_access(db, user, cid)
    record = db.scalar(select(Analysis).where(Analysis.id == aid, Analysis.claim_id == cid))
    if not record:
        raise HTTPException(404, "Analysis not found")
    return record


@api.get("/claims/{cid}/analyses/{aid}/evidence-lab")
def lab(cid: str, aid: str, auth=Depends(identity), db=Depends(session)):
    record = saved_analysis(db, auth[0], cid, aid)
    return {"analysis_id": record.id, "analyzed_at": record.created_at, **evidence_lab(record.result)}


class Scenario(BaseModel):
    excluded: set[str]


@api.post("/claims/{cid}/analyses/{aid}/evidence-lab/recovery")
def recover_sources(cid: str, aid: str, body: Scenario, auth=Depends(identity), db=Depends(session)):
    record = saved_analysis(db, auth[0], cid, aid)
    try:
        return recovery_packet(record.result, body.excluded)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@api.get("/claims/{cid}/analyses/{aid}")
def snapshot(cid: str, aid: str, auth=Depends(identity), db=Depends(session)):
    record = saved_analysis(db, auth[0], cid, aid)
    earlier = (
        select(Analysis)
        .where(
            Analysis.claim_id == cid,
            (Analysis.created_at < record.created_at)
            | ((Analysis.created_at == record.created_at) & (Analysis.id < record.id)),
        )
        .order_by(Analysis.created_at.desc(), Analysis.id.desc())
        .limit(1)
    )
    previous = db.scalar(earlier)
    return {
        "report": record.result,
        "previous_id": previous.id if previous else None,
        "changes": changes(previous.result, record.result) if previous else None,
    }


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
    if body.analysis_id is not None and body.analysis_id != claim.job_id:
        raise HTTPException(409, "This report was replaced. Refresh the case before reviewing it.")
    if body.action in ("correct_field", "accept_field"):
        field = db.scalar(
            select(Field).join(Document).where(Field.id == body.target, Document.claim_id == cid)
        )
        if not field or (body.action == "correct_field" and not body.value.strip()):
            raise HTTPException(422, "Field and correction required")
        if body.action == "correct_field":
            value = body.value.strip()
            if field.name in ("incident_date", "claim_amount"):
                value = normalized(field.name, value)
            try:
                ClaimInput.model_validate(
                    {**{k: getattr(claim, k) for k in ClaimInput.model_fields}, field.name: value}
                )
            except ValueError:
                raise HTTPException(422, "Invalid correction for " + field.name.replace("_", " "))
            field.corrected = body.value.strip()
        field.review = "CORRECTED" if field.corrected else "ACCEPTED"
    elif body.action == "reject_recommendation":
        previous = db.get(Analysis, claim.job_id)
        if body.target not in {r["id"] for r in previous.result["recommendations"]}:
            raise HTTPException(422, "Unknown recommendation")
    elif body.action == "comment" and not body.value.strip():
        raise HTTPException(422, "Enter a comment")
    elif body.action == "complete":
        if db.scalar(
            select(EvidenceRequest.id)
            .where(EvidenceRequest.claim_id == cid, EvidenceRequest.status.in_(ACTIVE))
            .limit(1)
        ):
            raise HTTPException(409, "Resolve outstanding evidence requests before completing review")
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
