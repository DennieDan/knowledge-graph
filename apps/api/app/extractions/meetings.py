from pydantic import BaseModel, Field

from .common import EntityReference, EvidenceValue


class MeetingActionItem(BaseModel):
    task: EvidenceValue
    owner: EvidenceValue = Field(default_factory=EvidenceValue)
    due_date: EvidenceValue = Field(default_factory=EvidenceValue)


class MeetingExtraction(BaseModel):
    report: list[EvidenceValue]
    title: EvidenceValue
    meeting_date: EvidenceValue = Field(default_factory=EvidenceValue)
    attendees: list[EvidenceValue] = Field(default_factory=list)
    decisions: list[EvidenceValue] = Field(default_factory=list)
    action_items: list[MeetingActionItem] = Field(default_factory=list)
    follow_ups: list[EvidenceValue] = Field(default_factory=list)
    references: list[EntityReference] = Field(default_factory=list)
