import hashlib
import io
import re
from collections import Counter
from pathlib import Path

import pymupdf
import pytesseract
from PIL import Image, ImageOps
from fastapi import HTTPException
from sqlalchemy import select

from .ai.provider import provider
from .db import Chunk, Document, Field, STATE

LIMIT = 20 * 1024 * 1024
PIXELS = 25_000_000


def path_for(doc):
    return STATE / (doc.id + ".upload")


def preview(doc, number):
    if doc.mime != "application/pdf":
        if number != 1:
            raise HTTPException(404, "Page not found")
        with Image.open(path_for(doc)) as image:
            image = ImageOps.exif_transpose(image)
            image.thumbnail((1500, 1800))
            buffer = io.BytesIO()
            image.convert("RGB").save(buffer, "PNG")
            return buffer.getvalue()
    with pymupdf.open(path_for(doc)) as pdf:
        if not 1 <= number <= len(pdf):
            raise HTTPException(404, "Page not found")
        page = pdf[number - 1]
        scale = min(2, 1800 / max(page.rect.width, page.rect.height, 1))
        return page.get_pixmap(matrix=pymupdf.Matrix(scale, scale)).tobytes("png")


def validate(data, filename, mime):
    if len(data) > LIMIT:
        raise HTTPException(413, "File exceeds 20 MB")
    ext = Path(filename).suffix.lower()
    types = {".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}
    if ext not in types or mime != types[ext]:
        raise HTTPException(415, "Expected PDF, PNG or JPEG")
    try:
        if ext == ".pdf":
            with pymupdf.open(stream=data, filetype="pdf") as pdf:
                if not data.startswith(b"%PDF-") or not 1 <= len(pdf) <= 50 or pdf.needs_pass:
                    raise ValueError()
        else:
            with Image.open(io.BytesIO(data)) as img:
                if img.format != ("PNG" if ext == ".png" else "JPEG") or img.width * img.height > PIXELS:
                    raise ValueError()
                img.verify()
    except Exception:
        raise HTTPException(422, "Unreadable, oversized or encrypted document")
    return hashlib.sha256(data).hexdigest()


def pages(doc):
    path = path_for(doc)
    if doc.mime != "application/pdf":
        with Image.open(path) as image:
            return [pytesseract.image_to_string(ImageOps.exif_transpose(image))], [1]
    result, scanned = [], []
    with pymupdf.open(path) as pdf:
        for index, page in enumerate(pdf):
            text = page.get_text(sort=True)
            if not text.strip():
                if page.rect.get_area() * 4 > PIXELS:
                    raise ValueError("Page too large")
                pix = page.get_pixmap(matrix=pymupdf.Matrix(2, 2), colorspace=pymupdf.csRGB, alpha=False)
                text = pytesseract.image_to_string(
                    Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                )
                scanned.append(index + 1)
            result.append(text)
    return result, scanned


def index_policy(db, doc, ai):
    db.query(Chunk).filter_by(document_id=doc.id).delete()
    if doc.kind != "INSURANCE_POLICY":
        return
    for number, page in enumerate(doc.pages, 1):
        parts = [
            page[start : start + 1000]
            for start in range(0, len(page), 850)
            if page[start : start + 1000].strip()
        ]
        if parts:
            for text, vector in zip(parts, ai.embed(parts), strict=True):
                db.add(Chunk(document_id=doc.id, page=number, text=text, embedding=vector))


def process(db, doc, ai=None):
    ai = ai or provider()
    texts, ocr = pages(doc)
    doc.pages = [
        "\n".join(re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()).strip()
        for text in texts
    ]
    kinds = []
    for number, text in enumerate(doc.pages, 1):
        if len(text) > 80000:
            raise ValueError("Page text limit exceeded")
        if text:
            result = ai.extract(text)
            kinds.append(result.kind)
            for fact in result.facts:
                if fact.value.strip() and fact.quote in text and fact.value in fact.quote:
                    db.add(
                        Field(
                            document_id=doc.id,
                            name=fact.name,
                            value=fact.value,
                            page=number,
                            quote=fact.quote,
                        )
                    )
    votes = Counter(kind for kind in kinds if kind != "OTHER")
    doc.kind = (
        votes.most_common(1)[0][0]
        if votes
        else ("PHOTOGRAPH" if doc.mime.startswith("image/") and not any(doc.pages) else "OTHER")
    )
    doc.metadata_json = {"page_count": len(texts), "ocr_pages": ocr, "model": ai.model}
    index_policy(db, doc, ai)
    doc.status = "READY"


def rank_policy(db, claim_id, question, ai):
    query = (
        select(Chunk)
        .join(Document)
        .where(Document.claim_id == claim_id, Document.kind == "INSURANCE_POLICY")
    )
    vector = ai.embed([question])[0]
    if db.bind.dialect.name == "postgresql":
        distance = Chunk.embedding.cosine_distance(vector)
        ranked = [
            (chunk, 1 - float(dist))
            for chunk, dist in db.execute(query.add_columns(distance).order_by(distance).limit(5))
            if dist is not None
        ]
    else:
        ranked = sorted(
            (
                (chunk, sum(a * b for a, b in zip(vector, chunk.embedding)))
                for chunk in db.scalars(query)
            ),
            key=lambda pair: -pair[1],
        )[:5]
    return [
        dict(document_id=c.document_id, page=c.page, text=c.text, score=score) for c, score in ranked
    ]


def search_policy(db, claim_id, question, ai):
    hits = rank_policy(db, claim_id, question, ai)
    choice = ai.passage(question, hits) if hits else None
    if (
        choice
        and 0 <= choice.index < len(hits)
        and choice.quote.strip()
        and choice.quote in hits[choice.index]["text"]
    ):
        hit = hits[choice.index]
        return {
            "answer": choice.quote,
            "evidence": [
                {"document_id": hit["document_id"], "page": hit["page"], "quote": choice.quote}
            ],
            "requires_human_review": True,
        }
    return {"answer": "Insufficient policy evidence.", "evidence": [], "requires_human_review": True}
