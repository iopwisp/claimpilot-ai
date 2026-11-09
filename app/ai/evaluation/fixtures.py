"""Deterministic fictional case materials, with annotations independent of extraction."""

import json
from datetime import date, timedelta
from pathlib import Path
import pymupdf

ROOT = Path(__file__).resolve().parents[3]
CASES = ROOT / "evaluation" / "cases.jsonl"
NAMES = [
    "Aster Vale",
    "Rowan Lake",
    "Mira Flint",
    "Jules Fern",
    "Ellis Reed",
    "Sage Pine",
    "Arden Moss",
    "Lane Birch",
    "Iris Ash",
    "Quinn Elm",
]
EVENTS = [
    "Vehicle collision damage",
    "Road accident repairs",
    "Collision damage to bumper",
    "Vehicle accident damage",
    "Road collision damage",
]
DECOYS = [
    "Dental care requires a separate endorsement.",
    "Baggage delay benefits apply after twelve hours.",
    "Storm repairs require a property inspection.",
    "Marine cargo exclusions are listed in Schedule C.",
    "Emergency lodging is subject to a nightly limit.",
    "Rental equipment must be returned within ten days.",
]


def case(i):
    scenario = i % 5
    incident = date(2026, 1, 1) + timedelta(days=i * 2)
    person = NAMES[i % 10] + " " + chr(65 + i // 10)
    details = {
        "claimant_name": person,
        "incident_date": incident.isoformat(),
        "claim_amount": str(1200 + i * 37),
        "currency": "USD",
        "policy_number": f"SYN-{9000 + i}",
        "incident_description": EVENTS[i % len(EVENTS)],
    }

    def record(kind, title, fields):
        lines = [title, "", *(k.replace("_", " ").title() + ": " + v for k, v in fields.items())]
        return {"kind": kind, "pages": ["\n".join(lines)], "facts": fields}

    docs = {"form.pdf": record("CLAIM_FORM", "Claim Form", details)}
    pages = ["Insurance Policy\n" + p for p in DECOYS]
    page = (i * 3) % 7
    provision = "Vehicle collision damage and road accident repairs are covered subject to inspection."
    if scenario != 3:
        pages.insert(page, "Insurance Policy\n" + provision)
    docs["policy.pdf"] = {"kind": "INSURANCE_POLICY", "pages": pages, "facts": {}}
    police_date = (
        (incident + timedelta(days=1)).isoformat() if scenario == 1 else details["incident_date"]
    )
    docs["police.pdf"] = record(
        "POLICE_REPORT", "Police Report", {"incident_date": police_date, "claimant_name": person}
    )
    if scenario != 2:
        amount = str(int(details["claim_amount"]) + 75) if scenario == 4 else details["claim_amount"]
        docs["invoice.pdf"] = record("INVOICE", "Invoice", {"claim_amount": amount, "currency": "USD"})
    if i % 4 == 0:
        docs["medical.pdf"] = record("MEDICAL_REPORT", "Medical Report", {"claimant_name": person})
    return {
        "id": f"synthetic-{i + 1:03}",
        "claim": details,
        "documents": docs,
        "ground_truth": {
            "policy_page": None if scenario == 3 else page + 1,
            "policy_quote": None if scenario == 3 else provision,
            "issues": ["DATE_MISMATCH"]
            if scenario == 1
            else ["AMOUNT_MISMATCH"]
            if scenario == 4
            else [],
            "missing": ["Damage evidence"] if scenario == 2 else [],
        },
    }


def pdf_bytes(pages):
    with pymupdf.open() as pdf:
        for content in pages:
            page = pdf.new_page()
            page.insert_textbox(pymupdf.Rect(48, 48, 548, 790), content, fontsize=12, fontname="helv")
        return pdf.tobytes()


def generate():
    CASES.parent.mkdir(exist_ok=True)
    with CASES.open("w", encoding="utf8") as out:
        for i in range(50):
            item = case(i)
            out.write(json.dumps(item) + "\n")
            if i < 3:
                path = ROOT / "demo" / ["01-complete", "02-date-mismatch", "03-missing-evidence"][i]
                path.mkdir(parents=True, exist_ok=True)
                (path / "claim.json").write_text(json.dumps(item["claim"], indent=2))
                for name, doc in item["documents"].items():
                    (path / name).write_bytes(pdf_bytes(doc["pages"]))


if __name__ == "__main__":
    generate()
