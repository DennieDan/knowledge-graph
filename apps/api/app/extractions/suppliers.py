from pydantic import BaseModel, Field

from .common import EntityReference, EvidenceValue


class SupplierExtraction(BaseModel):
    report: list[EvidenceValue]
    name: EvidenceValue
    registration_number: EvidenceValue = Field(default_factory=EvidenceValue)
    supplier_id: EvidenceValue = Field(default_factory=EvidenceValue)
    contacts: list[EvidenceValue] = Field(default_factory=list)
    addresses: list[EvidenceValue] = Field(default_factory=list)
    supplied_items: list[EvidenceValue] = Field(default_factory=list)
    prices: list[EvidenceValue] = Field(default_factory=list)
    lead_times: list[EvidenceValue] = Field(default_factory=list)
    payment_terms: EvidenceValue = Field(default_factory=EvidenceValue)
    delivery_terms: EvidenceValue = Field(default_factory=EvidenceValue)
    performance_notes: list[EvidenceValue] = Field(default_factory=list)
    references: list[EntityReference] = Field(default_factory=list)
