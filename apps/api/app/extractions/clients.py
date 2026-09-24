from pydantic import BaseModel, Field

from .common import EntityReference, EvidenceValue


class ClientExtraction(BaseModel):
    report: list[EvidenceValue]
    name: EvidenceValue
    registration_number: EvidenceValue = Field(default_factory=EvidenceValue)
    customer_id: EvidenceValue = Field(default_factory=EvidenceValue)
    contacts: list[EvidenceValue] = Field(default_factory=list)
    billing_addresses: list[EvidenceValue] = Field(default_factory=list)
    delivery_addresses: list[EvidenceValue] = Field(default_factory=list)
    payment_terms: EvidenceValue = Field(default_factory=EvidenceValue)
    delivery_terms: EvidenceValue = Field(default_factory=EvidenceValue)
    references: list[EntityReference] = Field(default_factory=list)
