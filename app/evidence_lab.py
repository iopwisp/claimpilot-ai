"""Trace the statements in one saved analysis back to their cited pages."""

from collections import defaultdict
from itertools import combinations

from app.workflow import normalized


def compact_packet(providers, document_ids, budget=4096):
    """Find a minimum file cover when provable, otherwise return an irreducible cover."""
    forced = {next(iter(group)) for group in providers if len(group) == 1}
    remaining = [group for group in providers if not forced.intersection(group)]
    masks = dict.fromkeys(document_ids, 0)
    for index, group in enumerate(remaining):
        for doc in group:
            masks[doc] |= 1 << index
    target = (1 << len(remaining)) - 1
    candidates = {}
    for doc, mask in masks.items():
        if mask:
            candidates.setdefault(mask, doc)
    options = list(candidates)
    selected = []
    missing = target
    while missing:
        mask = max(options, key=lambda m: (m & missing).bit_count())
        selected.append(mask)
        missing &= ~mask

    # Greedy can select an early file later made redundant by two others.
    suffix = [0]
    for mask in reversed(selected):
        suffix.append(suffix[-1] | mask)
    kept, covered = [], 0
    for index, mask in enumerate(selected):
        if covered | suffix[len(selected) - index - 1] != target:
            kept.append(mask)
            covered |= mask
    selected = kept

    def packet(masks, exact):
        chosen = forced.union(candidates[m] for m in masks)
        return {"document_ids": [doc for doc in document_ids if doc in chosen], "minimum": exact}

    if selected:
        capacity = max(m.bit_count() for m in options)
        lower = (len(remaining) + capacity - 1) // capacity
        for size in range(lower, len(selected)):
            for trial in combinations(options, size):
                if budget <= 0:
                    return packet(selected, False)
                budget -= 1
                covered = 0
                for mask in trial:
                    covered |= mask
                if covered == target:
                    return packet(trial, True)
    return packet(selected, True)


def evidence_index(report):
    documents = sorted(report["documents"], key=lambda d: (d["filename"].casefold(), d["id"]))
    doc_ids = [doc["id"] for doc in documents]
    known = set(doc_ids)
    groups = {}
    citations = defaultdict(set)

    def add(key, field, value, source):
        doc, page, quote = source["document_id"], source["page"], source["quote"]
        if doc not in known or page < 1 or not quote.strip():
            return
        groups.setdefault(key, (field, value))
        citations[key].add((doc, page, quote))

    fields = report.get("extracted_fields", [])
    currencies = defaultdict(set)
    for f in fields:
        if f["name"] == "currency" and f["value"].strip() and f["value"] in f["quote"]:
            currencies[f["document_id"], f["page"]].add(f["value"].strip().upper())
    for f in fields:
        field, value = f["name"], f["value"]
        if not value.strip() or value not in f["quote"]:
            continue
        # Only associate an amount with an unambiguous currency on the same page.
        codes = currencies[f["document_id"], f["page"]] if field == "claim_amount" else set()
        unit = next(iter(codes)) if len(codes) == 1 else ""
        key = (field, normalized(field, value), unit)
        display = value
        if field == "claim_amount":
            display = f"{value} {unit}" if unit else f"{value} (currency unspecified)"
        add(key, field, display, f)
    for source in report["policy"]["evidence"]:
        quote = source["quote"]
        add(("policy_passage", quote), "policy_passage", quote, source)

    items = []
    for key, (field, value) in sorted(groups.items(), key=lambda g: g[1]):
        refs = sorted(citations[key])
        items.append(
            {
                "field": field,
                "value": value,
                "sources": [
                    {"document_id": doc, "page": page, "quote": quote} for doc, page, quote in refs
                ],
            }
        )
    return documents, items


def source_sets(items):
    return [{s["document_id"] for s in item["sources"]} for item in items]


def evidence_lab(report):
    documents, items = evidence_index(report)
    ids = [d["id"] for d in documents]
    return {"documents": documents, "items": items, "packet": compact_packet(source_sets(items), ids)}


def recovery_packet(report, excluded):
    documents, items = evidence_index(report)
    ids = [d["id"] for d in documents if d["id"] in excluded]
    if len(ids) != len(excluded):
        raise ValueError("Choose files from this analysis")
    lost = [group for group in source_sets(items) if group.issubset(excluded)]
    return compact_packet(lost, ids)
