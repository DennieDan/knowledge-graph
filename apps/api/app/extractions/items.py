from pydantic import BaseModel, Field

from .common import EntityReference, EvidenceValue


class ItemExtraction(BaseModel):
    report: list[EvidenceValue]
    name: EvidenceValue
    internal_sku: EvidenceValue = Field(default_factory=EvidenceValue)
    customer_item_code: EvidenceValue = Field(default_factory=EvidenceValue)
    client_identifier: EvidenceValue = Field(default_factory=EvidenceValue)
    description: EvidenceValue = Field(default_factory=EvidenceValue)
    unit: EvidenceValue = Field(default_factory=EvidenceValue)
    material: EvidenceValue = Field(default_factory=EvidenceValue)
    dimensions: EvidenceValue = Field(default_factory=EvidenceValue)
    tolerances: EvidenceValue = Field(default_factory=EvidenceValue)
    revision: EvidenceValue = Field(default_factory=EvidenceValue)
    packaging: EvidenceValue = Field(default_factory=EvidenceValue)
    lead_time: EvidenceValue = Field(default_factory=EvidenceValue)
    references: list[EntityReference] = Field(default_factory=list)
