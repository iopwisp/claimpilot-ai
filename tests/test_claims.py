import uuid
import pytest
from PIL import Image
from io import BytesIO
from sqlalchemy import select
from app.ai.evaluation.fixtures import case, pdf_bytes
from app.ai.provider import LocalProvider
from app.db import Session, User
from app.documents import validate
from fastapi import HTTPException
from app.schemas import Extraction
from pydantic import ValidationError


def account(client, role="handler"):
    body = {"email": uuid.uuid4().hex + "@example.invalid", "password": "synthetic-password"}
    assert client.post("/api/v1/auth/register", json=body).status_code == 201
    if role != "handler":
        with Session.begin() as db:
            db.scalar(select(User).where(User.email == body["email"])).role = role
    token = client.post("/api/v1/auth/login", json=body).json()["access_token"]
    return {"Authorization": "Bearer " + token}, body["email"]


@pytest.mark.parametrize("index", [0, 1, 2, 3, 4])
def test_claim_lifecycle(client, index):
    fx = case(index)
    handler, _ = account(client)
    reviewer, email = account(client, "reviewer")
    foreign, _ = account(client)
    root = "/api/v1/claims"
    claim = client.post(root, json=fx["claim"], headers=handler).json()
    route = root + "/" + claim["id"]
    assert client.get(route, headers=foreign).status_code == 404
    assert client.patch(route, headers=handler, json={"reviewer_email": email}).status_code == 200
    for name, doc in fx["documents"].items():
        r = client.post(
            route + "/documents",
            headers=handler,
            files={"file": (name, pdf_bytes(doc["pages"]), "application/pdf")},
        )
        assert r.status_code == 202, r.text
        assert client.get(route + "/documents/" + r.json()["id"], headers=foreign).status_code == 404
    assert client.post(route + "/analyze", headers=handler).status_code == 202
    result = client.get(route + "/report", headers=reviewer).json()["report"]
    assert result["requires_human_review"]
    truth = fx["ground_truth"]
    assert sorted(x["type"] for x in result["inconsistencies"]) == truth["issues"]
    assert [x["name"] for x in result["required_items"] if x["status"] == "MISSING"] == truth["missing"]
    assert [x["page"] for x in result["policy"]["evidence"]] == (
        [truth["policy_page"]] if truth["policy_page"] else []
    )
    assert (
        client.post(route + "/review", headers=handler, json={"action": "complete"}).status_code == 403
    )
    target = result["extracted_fields"][0]["id"]
    for body in [
        {"action": "correct_field", "target": target, "value": "Verified correction"},
        {"action": "comment", "value": "Compared source."},
        {"action": "complete"},
    ]:
        assert client.post(route + "/review", headers=reviewer, json=body).status_code == 200
    assert client.get(route, headers=handler).json()["status"] == "COMPLETED"
    assert client.delete(route, headers=handler).status_code == 409
    assert client.get(route + "/audit", headers=reviewer).json()[0]["action"] == "review.complete"
    assert client.post("/api/v1/auth/logout", headers=handler).status_code == 200
    assert client.get(route, headers=handler).status_code == 401


def test_files_and_schema():
    for data, name, mime in [
        (b"bad", "a.pdf", "application/pdf"),
        (b"bad", "a.exe", "application/pdf"),
        (pdf_bytes(["page"] * 51), "a.pdf", "application/pdf"),
        (b"x" * (20 * 1024 * 1024 + 1), "a.png", "image/png"),
    ]:
        with pytest.raises(HTTPException):
            validate(data, name, mime)
    buf = BytesIO()
    Image.new("RGB", (30, 30)).save(buf, "PNG")
    assert validate(buf.getvalue(), "ok.png", "image/png")
    with pytest.raises(ValidationError):
        Extraction(kind="UNKNOWN", facts=[])
    assert LocalProvider().extract("Unknown file").facts == []
