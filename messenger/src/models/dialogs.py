from __future__ import annotations

import enum
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Enum, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import BaseModel

if TYPE_CHECKING:
    from src.models.dialog_participants import DialogParticipant
    from src.models.messages import Message


class DialogType(str, enum.Enum):
    DIRECT = "direct"
    GROUP = "group"


class Dialog(BaseModel):
    __tablename__ = "dialogs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    type: Mapped[DialogType] = mapped_column(
        Enum(DialogType, name="dialog_type", native_enum=False),
        nullable=False,
    )
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)

    participants: Mapped[list[DialogParticipant]] = relationship(
        back_populates="dialog", lazy="selectin"
    )
    messages: Mapped[list[Message]] = relationship(back_populates="dialog", lazy="noload")
