import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class SendMessageRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=4096)
    client_message_id: str = Field(..., min_length=1, max_length=255)


class MessageResponse(BaseModel):
    id: uuid.UUID
    dialog_id: uuid.UUID
    sender_login: str
    text: str
    client_message_id: str
    created_at: datetime


class MessagesListResponse(BaseModel):
    messages: list[MessageResponse]
