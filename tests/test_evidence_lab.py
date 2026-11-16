from uuid import uuid4

from app.evidence_lab import compact_packet, evidence_lab
from test_claims import account


def test_exact_search_can_improve_greedy_and_flags_its_budget():
    files = {"a": {1, 2, 3, 4}, "d": {5}, "e": {6}, "b": {1, 2, 5}, "c": {3, 4, 6}}
    groups = [{d for d in files if i in files[d]} for i in range(1, 7)]
    assert compact_packet(groups, list(files)) == {"minimum": True, "document_ids": ["b", "c"]}
    fallback = compact_packet(groups, list(files), budget=0)
    assert not fallback["minimum"]
    chosen = set(fallback["document_ids"])
    assert all(chosen & group for group in groups)
    assert all(any(group & chosen == {d} for group in groups) for d in chosen)
    assert compact_packet([], list(files)) == {"minimum": True, "document_ids": []}


def test_keeps_corrections_conflicts_and_currency_units_separate():
    def fact(doc, page, name, value, **kw):
        return dict(document_id=doc, page=page, name=name, value=value, quote="Value: " + value, **kw)

    result = evidence_lab(
        {
            "documents": [{"id": d, "filename": d} for d in "abc"],
            "extracted_fields": [
                fact("a", 1, "incident_date", "10.01.2026"),
                fact("a", 2, "incident_date", "2026-01-10"),
                fact("b", 1, "incident_date", "2026-01-11", corrected="2026-01-10"),
                fact("a", 1, "claim_amount", "1,200"),
                fact("a", 1, "currency", "USD"),
                fact("b", 1, "claim_amount", "1200"),
                fact("b", 1, "currency", "EUR"),
                fact("c", 1, "claim_amount", "1200.00"),
                fact("c", 1, "currency", "USD"),
            ],
            "policy": {"evidence": []},
        }
    )
    dates = [i for i in result["items"] if i["field"] == "incident_date"]
    assert [len(i["sources"]) for i in dates] == [2, 1]
    amounts = [i for i in result["items"] if i["field"] == "claim_amount"]
    assert {i["value"]: len(i["sources"]) for i in amounts} == {"1,200 USD": 2, "1200 EUR": 1}
    assert result["packet"] == {"minimum": True, "document_ids": ["a", "b"]}


def test_lab_access_and_historical_recovery(client):
    owner, _ = account(client)
    other, _ = account(client)

    def sample(user):
        return client.post(
            "/api/v1/samples", headers=user, json={"scenario": "01-complete", "request_id": str(uuid4())}
        ).json()["id"]

    cid, other_id = sample(owner), sample(other)
    route = "/api/v1/claims/" + cid
    client.post(route + "/analyze", headers=owner).raise_for_status()
    report = client.get(route + "/report", headers=owner).json()
    path = route + "/analyses/" + report["job_id"] + "/evidence-lab"
    lab = client.get(path, headers=owner).json()
    ids = {d["filename"]: d["id"] for d in lab["documents"]}
    assert len(lab["items"]) == 7
    assert set(lab["packet"]["document_ids"]) == {ids["form.pdf"], ids["policy.pdf"]}
    assert client.get(path, headers=other).status_code == 404
    assert client.get(path.replace(cid, other_id), headers=other).status_code == 404
    restore = path + "/recovery"
    assert client.post(restore, headers=other, json={"excluded": []}).status_code == 404
    assert client.post(restore, headers=owner, json={"excluded": ["unknown"]}).status_code == 422
    excluded = [ids[name] for name in ["policy.pdf", "invoice.pdf", "form.pdf"]]
    recovery = client.post(restore, headers=owner, json={"excluded": excluded}).json()
    assert recovery == {"document_ids": lab["packet"]["document_ids"], "minimum": True}
    assert client.get(route + "/report", headers=owner).json() == report
    client.post(route + "/analyze", headers=owner).raise_for_status()
    assert client.get(path, headers=owner).json() == lab
