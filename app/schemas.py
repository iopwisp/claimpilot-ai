from datetime import date
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

Kind = Literal[
    "CLAIM_FORM", "INSURANCE_POLICY", "MEDICAL_REPORT", "POLICE_REPORT", "INVOICE", "PHOTOGRAPH", "OTHER"
]
Name = Literal[
    "claimant_name", "incident_date", "policy_number", "claim_amount", "currency", "incident_description"
]


class Credentials(BaseModel):
    email: str = Field(pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$", max_length=254)
    password: str = Field(min_length=10, max_length=128)


class ClaimInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    claimant_name: str = Field(min_length=1, max_length=160)
    policy_number: str = Field(min_length=1, max_length=80)
    incident_date: date
    incident_description: str = Field(min_length=1, max_length=5000)
    claim_amount: Decimal = Field(ge=0, max_digits=16, decimal_places=2)
    currency: str = Field(pattern="^[A-Z]{3}$")


class Fact(BaseModel):
    name: Name
    value: str
    quote: str


class Extraction(BaseModel):
    kind: Kind
    facts: list[Fact]


class Review(BaseModel):
    action: Literal["accept_field", "correct_field", "reject_recommendation", "comment", "complete"]
    target: str = Field(default="", max_length=100)
    value: str = Field(default="", max_length=3000)
