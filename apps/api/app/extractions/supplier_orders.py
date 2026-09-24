from pydantic import BaseModel, Field

from .common import EntityReference, EvidenceValue


class SupplierOrderLine(BaseModel):
    item_code: EvidenceValue = Field(default_factory=EvidenceValue)
    description: EvidenceValue = Field(default_factory=EvidenceValue)
    quantity: EvidenceValue
    unit: EvidenceValue = Field(default_factory=EvidenceValue)
    unit_price: EvidenceValue = Field(default_factory=EvidenceValue)


class SupplierOrderExtraction(BaseModel):
    report: list[EvidenceValue]
    order_number: EvidenceValue
    supplier_name: EvidenceValue
    supplier_identifier: EvidenceValue = Field(default_factory=EvidenceValue)
    order_date: EvidenceValue = Field(default_factory=EvidenceValue)
    expected_delivery_date: EvidenceValue = Field(default_factory=EvidenceValue)
    status: EvidenceValue = Field(default_factory=EvidenceValue)
    currency: EvidenceValue = Field(default_factory=EvidenceValue)
    payment_terms: EvidenceValue = Field(default_factory=EvidenceValue)
    delivery_location: EvidenceValue = Field(default_factory=EvidenceValue)
    line_items: list[SupplierOrderLine] = Field(default_factory=list)
    changes: list[EvidenceValue] = Field(default_factory=list)
    approvals: list[EvidenceValue] = Field(default_factory=list)
    references: list[EntityReference] = Field(default_factory=list)
