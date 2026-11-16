from uuid import uuid4

import pytest

from app.ai.provider import LocalProvider
from app.workflow import normalized
from test_claims import account


def test_sample_to_reviewed_report(client):
    owner, _ = account(client)
    reviewer, email = account(client, "reviewer")
    stranger, _ = account(client)
    body = {"scenario": "02-date-mismatch", "request_id": str(uuid4())}
    samples = "/api/v1/samples"
    assert client.post(samples, headers=reviewer, json=body).status_code == 403
    first = client.post(samples, headers=owner, json=body)
    assert first.status_code == 201, first.text
    claim = first.json()
    route = "/api/v1/claims/" + claim["id"]
    assert client.post(samples, headers=owner, json=body).json()["id"] == claim["id"]
    assert client.post(samples, headers=stranger, json=body).status_code == 409
    assert (
        client.post(samples, headers=owner, json={**body, "scenario": "01-complete"}).status_code == 409
    )
    assert len(client.get(route + "/documents", headers=owner).json()) == 4
    client.patch(route, headers=owner, json={"reviewer_email": email}).raise_for_status()
    client.post(route + "/analyze", headers=owner).raise_for_status()
    initial = client.get(route + "/report", headers=reviewer).json()
    assert [x["type"] for x in initial["review"]["current_issues"]] == ["DATE_MISMATCH"]
    original = next(
        f
        for f in initial["review"]["fields"]
        if f["filename"] == "police.pdf" and f["name"] == "incident_date"
    )
    change = {
        "action": "correct_field",
        "target": original["id"],
        "value": claim["incident_date"],
        "analysis_id": initial["job_id"],
    }
    assert (
        client.post(route + "/review", headers=reviewer, json={**change, "value": "unknown"}).status_code
        == 422
    )
    assert (
        client.post(
            route + "/review", headers=reviewer, json={**change, "analysis_id": "stale"}
        ).status_code
        == 409
    )
    client.post(route + "/review", headers=reviewer, json=change).raise_for_status()
    client.post(route + "/review", headers=reviewer, json={"action": "complete"}).raise_for_status()
    final = client.get(route + "/report", headers=owner).json()
    assert final["report"] == initial["report"]
    assert final["review"]["reviewed_fields"] == 1 and not final["review"]["current_issues"]
    assert final["review"]["resolved_issues"] == initial["review"]["current_issues"]
    fact = next(f for f in final["review"]["fields"] if f["id"] == original["id"])
    assert fact["corrected"] == claim["incident_date"] and fact["value"] in fact["quote"]
    assert final["review"]["actions"][-1]["action"] == "review.complete"


@pytest.mark.parametrize("amount", ["1,250.50", "1 250,50", "1.250,50", "1250,50", "1250.50"])
def test_amount_formats(amount):
    assert normalized("claim_amount", amount) == normalized("claim_amount", "1250.50")
    assert normalized("claim_amount", "1,50") != normalized("claim_amount", "150")


def test_variations_and_unsupported_questions():
    ai = LocalProvider()
    page = "Страховое заявление\nЗаявитель — Алина Соколова\nСумма заявления: 1 250,50\nВалюта: RUB"
    extracted = ai.extract(page)
    assert extracted.kind == "CLAIM_FORM"
    assert {f.name: f.value for f in extracted.facts} == {
        "claimant_name": "Алина Соколова",
        "claim_amount": "1 250,50",
        "currency": "RUB",
    }
    assert all(f.value in f.quote and f.quote in page for f in extracted.facts)
    hits = [
        {
            "text": "Insurance Policy\nVehicle collision damage is covered. A deductible applies.",
            "score": 0.9,
        }
    ]
    for question in (
        "Does the policy cover earthquake damage?",
        "Which insurance policy?",
        "Is vehicle flood damage covered?",
    ):
        assert ai.passage(question, hits).index == -1
    assert "deductible" in ai.passage("vehicle collision", hits).quote
