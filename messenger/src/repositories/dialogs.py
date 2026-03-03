from uuid import UUID

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.postgres import get_session
from src.models.dialog_participants import DialogParticipant
from src.models.dialogs import Dialog, DialogType
from src.repositories.base.dialogs import BaseDialogsRepository


class DialogsRepository(BaseDialogsRepository):
    def __init__(self, session: AsyncSession = Depends(get_session)) -> None:
        self.session = session

    async def create(self, dialog_type: str, title: str | None = None) -> Dialog:
        dialog = Dialog(type=DialogType(dialog_type), title=title)
        self.session.add(dialog)
        await self.session.commit()
        await self.session.refresh(dialog)
        return dialog

    async def get_by_id(self, dialog_id: UUID) -> Dialog | None:
        result = await self.session.execute(
            select(Dialog).where(Dialog.id == dialog_id)
        )
        return result.scalar_one_or_none()

    async def get_user_dialogs(self, user_id: UUID) -> list[Dialog]:
        result = await self.session.execute(
            select(Dialog)
            .join(DialogParticipant)
            .where(DialogParticipant.user_id == user_id)
        )
        return list(result.scalars().all())

    async def add_participant(self, dialog_id: UUID, user_id: UUID) -> None:
        participant = DialogParticipant(dialog_id=dialog_id, user_id=user_id)
        self.session.add(participant)
        await self.session.commit()
