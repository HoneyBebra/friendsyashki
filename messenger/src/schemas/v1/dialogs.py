import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class CreateDirectDialogRequest(BaseModel):
    target_login: str = Field(..., min_length=1, max_length=255)


class ParticipantResponse(BaseModel):
    user_id: uuid.UUID
    joined_at: datetime


class DialogResponse(BaseModel):
    id: uuid.UUID
    type: str
    title: str | None
    participants: list[ParticipantResponse]
    created_at: datetime


class DialogsListResponse(BaseModel):
    dialogs: list[DialogResponse]
