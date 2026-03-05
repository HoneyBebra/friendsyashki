from uuid import UUID

from fastapi import Depends
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.postgres import get_session
from src.models.message_statuses import MessageStatus, MessageStatusEnum
from src.models.messages import Message
from src.repositories.base.messages import BaseMessagesRepository

_STATUS_ORDER = {
    MessageStatusEnum.SENT: 1,
    MessageStatusEnum.DELIVERED: 2,
    MessageStatusEnum.READ: 3,
}


class MessagesRepository(BaseMessagesRepository):
    def __init__(self, session: AsyncSession = Depends(get_session)) -> None:
        self.session = session

    async def create(
        self,
        dialog_id: UUID,
        sender_id: UUID,
        text: str,
        client_message_id: str,
    ) -> Message:
        message = Message(
            dialog_id=dialog_id,
            sender_id=sender_id,
            text=text,
            client_message_id=client_message_id,
        )
        self.session.add(message)
        await self.session.commit()
        await self.session.refresh(message)
        return message

    async def get_by_client_message_id(
        self, client_message_id: str
    ) -> Message | None:
        result = await self.session.execute(
            select(Message).where(
                Message.client_message_id == client_message_id
            )
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, message_id: UUID) -> Message | None:
        result = await self.session.execute(
            select(Message).where(Message.id == message_id)
        )
        return result.scalar_one_or_none()

    async def get_by_dialog(
        self,
        dialog_id: UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Message]:
        result = await self.session.execute(
            select(Message)
            .where(Message.dialog_id == dialog_id)
            .order_by(Message.created_at.asc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def get_status(
        self,
        message_id: UUID,
        user_id: UUID,
    ) -> MessageStatus | None:
        result = await self.session.execute(
            select(MessageStatus).where(
                MessageStatus.message_id == message_id,
                MessageStatus.user_id == user_id,
            )
        )
        rows = list(result.scalars().all())
        if not rows:
            return None
        return max(rows, key=lambda r: _STATUS_ORDER.get(r.status, 0))

    async def set_status(
        self,
        message_id: UUID,
        user_id: UUID,
        status: str,
    ) -> MessageStatus:
        msg_status = MessageStatus(
            message_id=message_id,
            user_id=user_id,
            status=MessageStatusEnum(status),
        )
        self.session.add(msg_status)
        await self.session.commit()
        await self.session.refresh(msg_status)
        return msg_status

    async def set_delivered_if_sent(
        self,
        message_id: UUID,
        user_id: UUID,
    ) -> MessageStatus | None:
        existing = await self.get_status(message_id, user_id)
        if existing is None:
            msg_status = MessageStatus(
                message_id=message_id,
                user_id=user_id,
                status=MessageStatusEnum.DELIVERED,
            )
            self.session.add(msg_status)
            await self.session.commit()
            await self.session.refresh(msg_status)
            return msg_status
        if existing.status != MessageStatusEnum.SENT:
            return None
        await self.session.execute(
            update(MessageStatus)
            .where(MessageStatus.id == existing.id)
            .values(status=MessageStatusEnum.DELIVERED)
        )
        await self.session.commit()
        await self.session.refresh(existing)
        return existing
