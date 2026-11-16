from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from sqlalchemy import func, select

from app.ai.provider import provider
from app.db import Document, session, uid
from app.documents import LIMIT, index_policy, path_for, preview, validate
from app.schemas import Kind
from app.security import identity
from app.workflow import row


from .access import DOC, audit, claim_access, editable, reset, dispatch

api = APIRouter(tags=["documents"])


@api.post("/claims/{cid}/documents", status_code=202)
def upload(cid: str, file: UploadFile = File(...), auth=Depends(identity), db=Depends(session)):
    claim = claim_access(db, auth[0], cid, True)
    editable(claim, auth[0])
    count = db.scalar(select(func.count(Document.id)).where(Document.claim_id == cid))
    if count >= 100:
        raise HTTPException(409, "A claim can contain up to 100 documents")
    doc = stage_document(db, claim, auth[0], file.filename, file.content_type, file.file.read(LIMIT + 1))
    reset(claim)
    try:
        dispatch(db, "document", doc, uid())
    except HTTPException:
        raise
    except Exception:
        path_for(doc).unlink(missing_ok=True)
        raise
    return row(doc, DOC)


def stage_document(db, claim, user, filename, mime, data):
    name = Path((filename or "").replace("\\", "/")).name[:250]
    doc = Document(
        id=uid(), claim_id=claim.id, filename=name, mime=mime, digest=validate(data, name, mime)
    )
    path = path_for(doc)
    try:
        path.write_bytes(data)
        db.add(doc)
        audit(db, user, "document.upload", claim.id, doc.id)
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return doc


@api.get("/claims/{cid}/documents")
def documents(cid: str, auth=Depends(identity), db=Depends(session)):
    claim_access(db, auth[0], cid)
    return [
        row(d, DOC)
        for d in db.scalars(
            select(Document).where(Document.claim_id == cid).order_by(Document.uploaded_at)
        )
    ]


def get_doc(db, cid, did):
    doc = db.get(Document, did)
    if not doc or doc.claim_id != cid:
        raise HTTPException(404)
    return doc


@api.get("/claims/{cid}/documents/{did}")
def source(cid: str, did: str, auth=Depends(identity), db=Depends(session)):
    claim_access(db, auth[0], cid)
    doc = get_doc(db, cid, did)
    return FileResponse(
        path_for(doc),
        media_type=doc.mime,
        filename=doc.filename,
        content_disposition_type="attachment",
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )


class Classification(BaseModel):
    kind: Kind


@api.get("/claims/{cid}/documents/{did}/pages/{number}")
def preview_page(cid: str, did: str, number: int, auth=Depends(identity), db=Depends(session)):
    claim_access(db, auth[0], cid)
    return Response(
        preview(get_doc(db, cid, did), number),
        media_type="image/png",
        headers={"Cache-Control": "no-store"},
    )


@api.patch("/claims/{cid}/documents/{did}")
def classify(cid: str, did: str, body: Classification, auth=Depends(identity), db=Depends(session)):
    claim = claim_access(db, auth[0], cid, True)
    editable(claim, auth[0])
    doc = get_doc(db, cid, did)
    if doc.status != "READY":
        raise HTTPException(409)
    doc.kind = body.kind
    doc.metadata_json = {
        **doc.metadata_json,
        "classification_requires_review": False,
        "classified_by": "human",
    }
    index_policy(db, doc, provider())
    reset(claim)
    audit(db, auth[0], "document.classify", cid, did, body.model_dump())
    db.commit()
    return row(doc, DOC)


@api.post("/claims/{cid}/documents/{did}/retry", status_code=202)
def retry(cid: str, did: str, auth=Depends(identity), db=Depends(session)):
    claim = claim_access(db, auth[0], cid, True)
    editable(claim, auth[0])
    doc = get_doc(db, cid, did)
    if doc.status != "FAILED":
        raise HTTPException(409)
    doc.status = "QUEUED"
    reset(claim)
    audit(db, auth[0], "document.retry", cid, did)
    dispatch(db, "document", doc, uid())
    return row(doc, DOC)
