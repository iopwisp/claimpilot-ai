"""Run against isolated SQLite storage. The configured provider controls inference."""

import json
import os
import tempfile
from collections import Counter
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from app.ai.provider import VERSION, provider
from app.db import Base, Claim, Document, Field, User
from app.documents import path_for, process, rank_policy, validate
from app.schemas import ClaimInput
from app.workflow import analyze
from .fixtures import CASES, ROOT, pdf_bytes


def run():
    ai = provider()
    totals = Counter()
    confusion = Counter()
    results = []
    with tempfile.TemporaryDirectory() as tmp, patch("app.documents.STATE", Path(tmp)):
        engine = create_engine("sqlite://")
        Base.metadata.create_all(engine)
        with Session(engine) as db:
            user = User(email="synthetic@example.invalid", password_hash="unused")
            db.add(user)
            db.flush()
            for line in CASES.read_text().splitlines():
                case = json.loads(line)
                claim = Claim(
                    **ClaimInput.model_validate(case["claim"]).model_dump(), created_by=user.id
                )
                db.add(claim)
                db.flush()
                truth = case["ground_truth"]
                for filename, source in case["documents"].items():
                    data = pdf_bytes(source["pages"])
                    doc = Document(
                        claim_id=claim.id,
                        filename=filename,
                        mime="application/pdf",
                        digest=validate(data, filename, "application/pdf"),
                    )
                    db.add(doc)
                    db.flush()
                    path_for(doc).write_bytes(data)
                    totals["pages"] += len(source["pages"])
                    try:
                        process(db, doc, ai)
                        totals["valid_pages"] += len(doc.pages)
                    except (ValueError, RuntimeError):
                        doc.status = "FAILED"
                    db.flush()
                    confusion[source["kind"], doc.kind] += 1
                    facts = list(db.scalars(select(Field).where(Field.document_id == doc.id)))
                    expected = source["facts"]
                    totals["fields"] += len(expected)
                    for key, value in expected.items():
                        totals["correct_fields"] += int(
                            {f.value for f in facts if f.name == key} == {value}
                        )
                    for f in facts:
                        totals["citations"] += 1
                        totals["correct_citations"] += int(
                            1 <= f.page <= len(source["pages"])
                            and f.quote in source["pages"][f.page - 1]
                            and expected.get(f.name) == f.value
                            and f.value in f.quote
                        )
                report = analyze(db, claim, ai)
                hits = rank_policy(db, claim.id, claim.incident_description, ai)
                expected_page = truth["policy_page"]
                if expected_page:
                    totals["queries"] += 1
                    totals["retrieved"] += int(any(h["page"] == expected_page for h in hits))
                else:
                    totals["insufficient"] += 1
                    totals["abstained"] += int(not report["policy"]["evidence"])
                issues = sorted({item["type"] for item in report["inconsistencies"]})
                missing = sorted(
                    item["name"] for item in report["required_items"] if item["status"] == "MISSING"
                )
                results.append(
                    {
                        "case": case["id"],
                        "issues_match": issues == truth["issues"],
                        "missing_match": missing == truth["missing"],
                        "policy_citation_match": any(
                            h["page"] == expected_page and truth["policy_quote"] in h["quote"]
                            for h in report["policy"]["evidence"]
                        )
                        if expected_page
                        else not report["policy"]["evidence"],
                    }
                )
    labels = {k for pair in confusion for k in pair}
    f1 = sum(
        2 * confusion[k, k] / sum(n * ((a == k) + (b == k)) for (a, b), n in confusion.items())
        for k in labels
    ) / len(labels)
    metrics = {
        "structured_extraction_exact_match": totals["correct_fields"] / max(totals["fields"], 1),
        "document_classification_macro_f1": f1,
        "retrieval_recall_at_5": totals["retrieved"] / totals["queries"],
        "structured_output_validity": totals["valid_pages"] / totals["pages"],
        "source_citation_correctness": totals["correct_citations"] / max(totals["citations"], 1),
        "insufficient_evidence_accuracy": totals["abstained"] / totals["insufficient"],
    }
    out = Path(os.getenv("EVAL_OUTPUT_DIR", ROOT / "evaluation"))
    out.mkdir(parents=True, exist_ok=True)
    payload = {
        "model": ai.model,
        "prompt": VERSION,
        "temperature": 0 if ai.model != "local-rules-v1" else None,
        "metrics": metrics,
        "counts": totals,
        "cases": results,
    }
    (out / "results.json").write_text(json.dumps(payload, indent=2))
    summary = [
        "# Evaluation report",
        "",
        f"Provider: {ai.model}. Prompt: {VERSION}. Cases: {len(results)}.",
        "",
        "| Metric | Observed |",
        "|---|---:|",
        *(f"| {k} | {v:.2%} |" for k, v in metrics.items()),
        "",
        *(
            f"{k}: {sum(r[k] for r in results)}/{len(results)} cases.  "
            for k in ["issues_match", "missing_match", "policy_citation_match"]
        ),
        "",
        "Synthetic English vehicle cases use labelled PDF fields and five document classes. These measurements describe this fixture distribution only. OCR, photographs, free-form prose and production traffic require separate evaluation.",
    ]
    (out / "REPORT.md").write_text("\n".join(summary) + "\n")
    print("\n".join(summary))


if __name__ == "__main__":
    run()
