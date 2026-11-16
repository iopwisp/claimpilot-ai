from uuid import uuid4

from app.ai.evaluation.fixtures import pdf_bytes
from test_claims import account


def test_missing_evidence_handoff(client):
    handler, _ = account(client)
    reviewer, email = account(client, "reviewer")
    other, _ = account(client)

    def sample(auth):
        result = client.post(
            "/api/v1/samples",
            json={"scenario": "03-missing-evidence", "request_id": str(uuid4())},
            headers=auth,
        )
        result.raise_for_status()
        return "/api/v1/claims/" + result.json()["id"]

    route = sample(handler)
    foreign = sample(other)
    client.patch(route, headers=handler, json={"reviewer_email": email}).raise_for_status()
    job = client.post(route + "/analyze", headers=handler).json()["job_id"]
    path = route + "/evidence"
    body = {"analysis_id": job, "item": "Damage evidence"}
    assert client.post(path, headers=handler, json=body).status_code == 403
    assert client.post(path, headers=other, json=body).status_code == 404
    assert client.post(path, headers=reviewer, json={**body, "analysis_id": "old"}).status_code == 409
    assert client.post(path, headers=reviewer, json={**body, "item": "Claim form"}).status_code == 422
    task = client.post(path, headers=reviewer, json=body).json()
    assert (
        client.get("/api/v1/dashboard", headers=handler).json()["evidence_queue"][0]["id"] == task["id"]
    )
    assert not client.get("/api/v1/dashboard", headers=other).json()["evidence_queue"]
    assert client.post(path, headers=reviewer, json=body).status_code == 409

    def decide(auth, action, version, **kwargs):
        return client.post(
            path + "/" + task["id"], headers=auth, json={"action": action, "version": version, **kwargs}
        )

    def complete():
        return client.post(route + "/review", headers=reviewer, json={"action": "complete"})

    assert complete().status_code == 409
    assert decide(reviewer, "withdraw", 1).status_code == 422
    assert decide(reviewer, "withdraw", 1, note="Superseded request").json()["status"] == "WITHDRAWN"
    assert decide(handler, "submit", 2).status_code == 409
    task = client.post(path, headers=reviewer, json=body).json()
    foreign_doc = client.get(foreign + "/documents", headers=other).json()[0]["id"]
    assert decide(handler, "submit", 1, document_id=foreign_doc).status_code == 422
    doc = client.post(
        route + "/documents",
        headers=handler,
        files={"file": ("repair.pdf", pdf_bytes(["Invoice\nClaim amount: 1274"]), "application/pdf")},
    ).json()["id"]
    assert decide(reviewer, "submit", 1, document_id=doc).status_code == 403
    assert decide(handler, "submit", 1, document_id=doc).json()["status"] == "SUBMITTED"
    assert (
        client.get("/api/v1/dashboard", headers=reviewer).json()["evidence_queue"][0]["id"] == task["id"]
    )
    assert decide(reviewer, "return", 2).status_code == 422
    assert decide(reviewer, "return", 2, note="Please verify the invoice.").json()["status"] == "OPEN"
    assert decide(handler, "submit", 1, document_id=doc).status_code == 409
    assert decide(handler, "submit", 3, document_id=doc).json()["version"] == 4
    client.post(route + "/analyze", headers=handler).raise_for_status()
    history = client.get(route + "/analyses", headers=reviewer).json()
    assert len(history) == 2 and history[0]["current"] and history[1]["id"] == job
    latest = client.get(route + "/analyses/" + history[0]["id"], headers=handler).json()
    assert latest["previous_id"] == job
    assert [d["filename"] for d in latest["changes"]["added_documents"]] == ["repair.pdf"]
    assert latest["changes"]["materials"] == [
        {"name": "Damage evidence", "before": "MISSING", "after": "PRESENT"}
    ]
    original = client.get(route + "/analyses/" + job, headers=reviewer).json()
    assert original["changes"] is None and "repair.pdf" not in [
        d["filename"] for d in original["report"]["documents"]
    ]
    assert client.get(foreign + "/analyses/" + job, headers=other).status_code == 404
    assert complete().status_code == 409
    assert decide(reviewer, "accept", 4).json()["status"] == "ACCEPTED"
    complete().raise_for_status()
    assert client.get(route, headers=handler).json()["evidence_requests"][0]["document_id"] == doc
    actions = [e["action"] for e in client.get(route + "/audit", headers=reviewer).json()]
    assert actions.count("evidence.submit") == 2 and "evidence.return" in actions
