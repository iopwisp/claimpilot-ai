from types import SimpleNamespace
from uuid import uuid4

from app.chronology import MAX_CITATIONS, chronology, with_chronology
from test_claims import account


def test_chronology_preserves_conflicts_pages_and_ambiguous_dates():
    f = {
        "name": "incident_date",
        "value": "2026-05-03",
        "corrected": "2026-05-04",
        "document_id": "a",
        "page": 1,
        "quote": "Incident Date: 2026-05-03",
    }
    docs = [
        SimpleNamespace(id="a", pages=[f["quote"], "Дата уведомления — 11.05.2026"]),
        SimpleNamespace(
            id="b",
            pages=[
                "Date of loss: May 4, 2026\nInvoice date: 05/06/2026\nReference: 2026-05-11\nNotice date: 2026-05-11"
            ],
        ),
    ]
    result = chronology([f], docs)
    events = result["events"]
    assert [(e["kind"], e["date"]) for e in events] == [
        ("incident", "2026-05-03"),
        ("incident", "2026-05-04"),
        ("notice", "2026-05-11"),
        ("invoice", None),
    ]
    assert len(events[0]["sources"]) == 1
    assert [(s["document_id"], s["page"]) for s in events[2]["sources"]] == [("a", 2), ("b", 1)]
    assert events[-1]["value"] == "05/06/2026"
    old = {"extracted_fields": [f]}
    legacy = with_chronology(old)["chronology"]
    assert legacy["events"] == events[:1] and legacy["scope"] == "extracted_incidents"
    assert "chronology" not in old


def test_chronology_discloses_truncation():
    doc = SimpleNamespace(id="doc", pages=["Inspection date: 2026-01-01"] * MAX_CITATIONS)
    assert not chronology([], [doc])["truncated"]
    doc.pages.append("Invoice date: 2026-02-01")
    assert chronology([], [doc])["truncated"]


def test_notice_window_sample_and_saved_snapshot(client):
    owner, _ = account(client)
    other, _ = account(client)
    sample = client.post(
        "/api/v1/samples",
        headers=owner,
        json={"scenario": "04-notice-window", "request_id": str(uuid4())},
    )
    sample.raise_for_status()
    path = "/api/v1/claims/" + sample.json()["id"]
    client.post(path + "/analyze", headers=owner).raise_for_status()
    current = client.get(path + "/report", headers=owner).json()
    timeline = current["report"]["chronology"]
    assert timeline["scope"] == "labeled_dates" and not timeline["truncated"]
    assert [e["kind"] for e in timeline["events"]] == [
        "policy_start",
        "incident",
        "incident",
        "inspection",
        "invoice",
        "notice",
        "policy_end",
    ]
    snap = path + "/analyses/" + current["job_id"]
    assert client.get(snap, headers=other).status_code == 404
    assert client.get(snap, headers=owner).json()["report"]["chronology"] == timeline
