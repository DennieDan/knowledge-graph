from typing import Literal

from pydantic import BaseModel, Field

from .common import EvidenceValue


class ConversationTopic(BaseModel):
    title: str
    kind: Literal["topic", "decision", "key_point"] = "topic"
    summary: EvidenceValue
    date: str | None = None


class ConversationExtraction(BaseModel):
    topics: list[ConversationTopic] = Field(default_factory=list)
