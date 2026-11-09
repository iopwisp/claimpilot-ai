import json
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from sqlalchemy import select
from .db import Document, Field, WorkflowSettings
from .documents import search_policy
from .ai.contracts import OUTPUT

RULES = json.loads(Path(__file__).with_name("rules.json").read_text())


def row(entity, names):
    return {name: getattr(entity, name) for name in names.split()}


def facts_for(db, claim_id):
    pairs = db.execute(
        select(Field, Document)
        .join(Document)
        .where(Document.claim_id == claim_id)
        .order_by(Document.uploaded_at, Field.page)
    )
    return [
        dict(
            **row(field, "id name value corrected page quote review document_id"), filename=doc.filename
        )
        for field, doc in pairs
    ]


def normalized(field, value):
    text = str(value).strip().casefold()
    if field == "claim_amount":
        try:
            return Decimal(text.replace(",", ""))
        except InvalidOperation:
            return text
    if field == "incident_date":
        try:
            return date.fromisoformat(text).isoformat()
        except ValueError:
            for pattern in ("%d %B %Y", "%d %b %Y", "%B %d, %Y", "%d.%m.%Y"):
                try:
                    return datetime.strptime(text, pattern).date().isoformat()
                except ValueError:
                    continue
            return text
    return " ".join(text.split())


def compare(claim, docs, facts, ai):
    issues = []

    def issue(kind, field, values, description):
        issues.append(
            dict(
                type=kind,
                severity="MEDIUM",
                field=field,
                values=values,
                description=description,
                requires_review=True,
            )
        )

    grouped = defaultdict(list)
    for fact in facts:
        grouped[fact["name"]].append(fact)
    for field, kind in {
        "incident_date": "DATE_MISMATCH",
        "claim_amount": "AMOUNT_MISMATCH",
        "policy_number": "INVALID_POLICY_NUMBER",
        "claimant_name": "INCONSISTENT_CLAIM_DETAILS",
        "currency": "INCONSISTENT_CLAIM_DETAILS",
    }.items():
        sources = grouped[field]
        if not sources:
            issue(
                "MISSING_INFORMATION",
                field,
                [],
                f"Verify {field.replace('_', ' ')} against a source document.",
            )
            continue
        baseline = str(getattr(claim, field))
        observed = {normalized(field, item["corrected"] or item["value"]) for item in sources}
        if observed - {normalized(field, baseline)}:
            issue(
                kind,
                field,
                [{"source": "Claim record", "value": baseline}, *sources],
                f"Submitted values differ for {field.replace('_', ' ')}.",
            )
    seen = {}
    for doc in docs:
        if doc.digest in seen:
            issue(
                "DUPLICATE_DOCUMENT",
                "file",
                [seen[doc.digest], row(doc, "id filename")],
                "Two uploaded files have identical contents.",
            )
        seen[doc.digest] = row(doc, "id filename")
    descriptions = grouped["incident_description"]
    if len(descriptions) > 1:
        for pair in ai.conflicts(descriptions):
            if 0 <= pair.first < len(descriptions) and 0 <= pair.second < len(descriptions):
                a, b = descriptions[pair.first], descriptions[pair.second]
                if a["document_id"] != b["document_id"]:
                    issue(
                        "INCONSISTENT_CLAIM_DETAILS",
                        "incident_description",
                        [a, b],
                        "Incident descriptions need reconciliation.",
                    )
    return issues


def checklist(docs, claim, police_report="conditional"):
    kinds = {d.kind for d in docs if d.status == "READY"}
    items = []
    for name, options in RULES.items():
        if name == "Police report" and police_report == "optional":
            continue
        status = (
            "PRESENT"
            if kinds.intersection(options)
            else (
                "REQUIRES_CONFIRMATION"
                if name == "Police report" and police_report == "conditional"
                else "MISSING"
            )
        )
        items.append(dict(name=name, status=status))
    items.append(
        dict(
            name="Incident description",
            status="PRESENT" if claim.incident_description.strip() else "MISSING",
        )
    )
    return items


def analyze(db, claim, ai):
    docs = list(db.scalars(select(Document).where(Document.claim_id == claim.id)))
    facts = facts_for(db, claim.id)
    report = {}
    settings = db.get(WorkflowSettings, 1)

    def report_summary():
        recommendations = [
            f"Request {item['name'].lower()}."
            for item in report["required_items"]
            if item["status"] == "MISSING"
        ]
        recommendations += [item["description"] for item in report["inconsistencies"]]
        if not report["policy"]["evidence"]:
            recommendations.append("Verify the applicable policy provision.")
        return [{"id": f"rec-{i + 1}", "text": v} for i, v in enumerate(recommendations)]

    steps = [
        (
            "get_claim_details",
            "overview",
            lambda: {
                k: str(v)
                for k, v in row(
                    claim,
                    "claim_number claimant_name policy_number incident_date claim_amount currency incident_description",
                ).items()
            },
        ),
        ("list_claim_documents", "documents", lambda: [row(d, "id filename kind status") for d in docs]),
        ("compare_claim_fields", "inconsistencies", lambda: compare(claim, docs, facts, ai)),
        (
            "get_missing_documents",
            "required_items",
            lambda: checklist(docs, claim, settings.police_report if settings else "conditional"),
        ),
        ("search_policy", "policy", lambda: search_policy(db, claim.id, claim.incident_description, ai)),
        ("generate_review_report", "recommendations", report_summary),
    ]
    for name, key, operation in steps:
        if ai.call(name) != name:
            raise ValueError("Unexpected tool")
        schema = OUTPUT[name]
        report[key] = schema.dump_python(schema.validate_python(operation()), mode="json")
    report.update(
        extracted_fields=facts,
        sources=[row for row in facts if row["quote"]],
        requires_human_review=True,
        tools=[s[0] for s in steps],
    )
    return report
