"""Schemas for the six scoped workflow tool results."""

from typing import Literal
from pydantic import BaseModel, ConfigDict, TypeAdapter
from app.schemas import Kind


class ToolResult(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Overview(ToolResult):
    claim_number: str
    claimant_name: str
    policy_number: str
    incident_date: str
    claim_amount: str
    currency: str
    incident_description: str


class Attachment(ToolResult):
    id: str
    filename: str
    kind: Kind
    status: Literal["READY"]


class Reference(ToolResult):
    document_id: str
    page: int
    quote: str


class PolicyResult(ToolResult):
    answer: str
    evidence: list[Reference]
    requires_human_review: Literal[True]


class RequiredItem(ToolResult):
    name: str
    status: Literal["PRESENT", "MISSING", "REQUIRES_CONFIRMATION"]


class Discrepancy(ToolResult):
    type: Literal[
        "DATE_MISMATCH",
        "AMOUNT_MISMATCH",
        "INVALID_POLICY_NUMBER",
        "DUPLICATE_DOCUMENT",
        "INCONSISTENT_CLAIM_DETAILS",
        "MISSING_INFORMATION",
    ]
    severity: Literal["LOW", "MEDIUM", "HIGH"]
    field: str
    description: str
    values: list[dict[str, str | int | None]]
    requires_review: Literal[True]


class Recommendation(ToolResult):
    id: str
    text: str


OUTPUT = {
    "get_claim_details": TypeAdapter(Overview),
    "list_claim_documents": TypeAdapter(list[Attachment]),
    "search_policy": TypeAdapter(PolicyResult),
    "compare_claim_fields": TypeAdapter(list[Discrepancy]),
    "get_missing_documents": TypeAdapter(list[RequiredItem]),
    "generate_review_report": TypeAdapter(list[Recommendation]),
}
