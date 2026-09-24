from typing import Literal

from pydantic import BaseModel, Field


class EvidenceValue(BaseModel):
    value: str | None = None
    citations: list[str] = Field(default_factory=list)
    confidence: Literal["high", "medium", "low"] = "medium"


class EntityReference(BaseModel):
    entity_type: Literal["sales-orders", "clients", "items"]
    name: str
    identifier: str | None = None
    citations: list[str] = Field(default_factory=list)


class CandidateIdentifiers(BaseModel):
    order_number: str | None = None
    customer_identifier: str | None = None
    registration_number: str | None = None
    customer_id: str | None = None
    internal_sku: str | None = None
    customer_item_code: str | None = None
    client_identifier: str | None = None


class CandidateMention(BaseModel):
    entity_type: Literal["sales-orders", "clients", "items"]
    name: str
    identifiers: CandidateIdentifiers = Field(default_factory=CandidateIdentifiers)
    citations: list[str] = Field(default_factory=list)


class DiscoveryOutput(BaseModel):
    candidates: list[CandidateMention] = Field(default_factory=list)
