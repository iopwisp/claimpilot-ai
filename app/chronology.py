"""Build a chronology from explicit dates, retaining the original cited lines."""

import re
from datetime import date, datetime


LABELS = {
    "incident": ("incident date", "date of loss", "дата происшествия"),
    "notice": ("notice date", "date of notification", "date reported", "дата уведомления"),
    "inspection": ("inspection date", "date of inspection", "дата осмотра"),
    "invoice": ("invoice date", "date of invoice", "дата счета", "дата счёта"),
    "treatment": ("treatment date", "date of treatment", "дата лечения"),
    "policy_start": ("policy start date", "policy effective date", "дата начала полиса"),
    "policy_end": ("policy end date", "policy expiry date", "дата окончания полиса"),
}
KINDS = {label: kind for kind, labels in LABELS.items() for label in labels}
SEPARATOR = re.compile(r"\s*[:：]\s*|\s+[—–-]\s+")
MAX_CITATIONS = 300


def source_date(value):
    value = value.strip()
    try:
        return date.fromisoformat(value)
    except ValueError:
        for pattern in ("%d %B %Y", "%d %b %Y", "%B %d, %Y", "%d.%m.%Y"):
            try:
                return datetime.strptime(value, pattern).date()
            except ValueError:
                continue
    return None


def chronology(facts, documents=None):
    groups = {}
    seen = set()

    def add(kind, value, doc, page, quote):
        reference = (kind, value, doc, page, quote)
        if reference in seen:
            return True
        if len(seen) >= MAX_CITATIONS:
            return False
        seen.add(reference)
        parsed = source_date(value)
        day = parsed.isoformat() if parsed else None
        key = (kind, day, "" if day else value)
        event = groups.setdefault(
            key,
            {
                "kind": kind,
                "date": day,
                "value": day or value,
                "sources": [],
            },
        )
        event["sources"].append({"document_id": doc, "page": page, "quote": quote})
        return True

    def mentions():
        for f in facts:
            if f["name"] == "incident_date" and f["value"].strip() and f["value"] in f["quote"]:
                yield "incident", f["value"], f["document_id"], f["page"], f["quote"]
        for doc in documents or ():
            for page, text in enumerate(doc.pages or [], 1):
                for line in text.splitlines():
                    parts = SEPARATOR.split(line.strip(), maxsplit=1)
                    if len(parts) == 2 and parts[1] and (kind := KINDS.get(parts[0].casefold())):
                        yield kind, parts[1], doc.id, page, line.strip()

    truncated = any(not add(*mention) for mention in mentions())
    return {
        "events": sorted(groups.values(), key=lambda e: (e["date"] or "9999-99", e["kind"], e["value"])),
        "scope": "extracted_incidents" if documents is None else "labeled_dates",
        "truncated": truncated,
    }


def with_chronology(report):
    if "chronology" in report:
        return report
    return {**report, "chronology": chronology(report.get("extracted_fields", []))}
