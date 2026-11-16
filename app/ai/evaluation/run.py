"""Run against isolated SQLite storage. The configured provider controls inference."""

import json
import argparse
import os
import tempfile
from collections import Counter
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from app.ai.provider import VERSION, LocalProvider, provider
from app.db import Base, Claim, Document, Field, User
from app.documents import path_for, process, rank_policy, validate
from app.schemas import ClaimInput, Extraction
from app.workflow import analyze
from .fixtures import CASES, ROOT, pdf_bytes


def run():
    ai = provider()
    totals = Counter()
    extract = ai.extract

    def measured_extract(text):
        totals["pages"] += 1
        try:
            parsed = Extraction.model_validate(extract(text))
        except ValueError:
            # A refused or malformed extraction counts as a miss for this page.
            return Extraction(kind="OTHER", facts=[])
        totals["valid_pages"] += 1
        return parsed

    ai.extract = measured_extract
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
                policy_ids = set()
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
                    if source["kind"] == "INSURANCE_POLICY":
                        policy_ids.add(doc.id)
                    process(db, doc, ai)
                    db.flush()
                    confusion[source["kind"], doc.kind] += 1
                    facts = list(db.scalars(select(Field).where(Field.document_id == doc.id)))
                    expected = source["facts"]
                    totals["fields"] += len(set(expected) | {f.name for f in facts})
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
                    totals["retrieved"] += int(
                        any(
                            h["document_id"] in policy_ids
                            and h["page"] == expected_page
                            and truth["policy_quote"] in h["text"]
                            for h in hits
                        )
                    )
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
                            h["document_id"] in policy_ids
                            and h["page"] == expected_page
                            and truth["policy_quote"] in h["quote"]
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
        "temperature": None if isinstance(ai, LocalProvider) else 0,
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
    return payload


def check(result):
    targets = {
        "structured_extraction_exact_match": 0.90,
        "document_classification_macro_f1": 0.85,
        "retrieval_recall_at_5": 0.85,
        "structured_output_validity": 0.99,
        "source_citation_correctness": 0.95,
        "insufficient_evidence_accuracy": 1.0,
    }
    failed = [key for key, target in targets.items() if result["metrics"][key] < target]
    for key in ("issues_match", "missing_match", "policy_citation_match"):
        if not all(case[key] for case in result["cases"]):
            failed.append(key)
    if failed:
        raise SystemExit("Quality targets missed: " + ", ".join(failed))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check", action="store_true", help="Fail if the fixture regression targets are missed"
    )
    args = parser.parse_args()
    result = run()
    if args.check:
        check(result)
