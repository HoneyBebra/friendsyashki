import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.dialogs import DialogType
from src.models.message_statuses import MessageStatusEnum
from src.repositories.dialogs import DialogsRepository
from src.repositories.messages import MessagesRepository


@pytest.mark.asyncio
class TestDialogsRepository:
    async def test_create_dialog(self, db_session: AsyncSession) -> None:
        repo = DialogsRepository(session=db_session)
        dialog = await repo.create(dialog_type="direct")
        assert dialog.id is not None
        assert dialog.type == DialogType.DIRECT
        assert dialog.created_at is not None

    async def test_create_group_dialog(self, db_session: AsyncSession) -> None:
        repo = DialogsRepository(session=db_session)
        dialog = await repo.create(dialog_type="group", title="Test Group")
        assert dialog.type == DialogType.GROUP
        assert dialog.title == "Test Group"

    async def test_get_by_id(self, db_session: AsyncSession) -> None:
        repo = DialogsRepository(session=db_session)
        dialog = await repo.create(dialog_type="direct")
        found = await repo.get_by_id(dialog.id)
        assert found is not None
        assert found.id == dialog.id

    async def test_get_by_id_not_found(self, db_session: AsyncSession) -> None:
        repo = DialogsRepository(session=db_session)
        found = await repo.get_by_id(uuid.uuid4())
        assert found is None

    async def test_add_participant_and_get_user_dialogs(self, db_session: AsyncSession) -> None:
        repo = DialogsRepository(session=db_session)
        dialog = await repo.create(dialog_type="direct")
        user_id = uuid.uuid4()
        await repo.add_participant(dialog.id, user_id)
        dialogs = await repo.get_user_dialogs(user_id)
        assert len(dialogs) >= 1
        assert any(d.id == dialog.id for d in dialogs)


@pytest.mark.asyncio
class TestMessagesRepository:
    async def test_create_message(self, db_session: AsyncSession) -> None:
        dialog_repo = DialogsRepository(session=db_session)
        dialog = await dialog_repo.create(dialog_type="direct")
        repo = MessagesRepository(session=db_session)
        msg = await repo.create(
            dialog_id=dialog.id,
            sender_id=uuid.uuid4(),
            text="Hello, world!",
            client_message_id=str(uuid.uuid4()),
        )
        assert msg.id is not None
        assert msg.text == "Hello, world!"
        assert msg.created_at is not None

    async def test_get_by_id(self, db_session: AsyncSession) -> None:
        dialog_repo = DialogsRepository(session=db_session)
        dialog = await dialog_repo.create(dialog_type="direct")
        repo = MessagesRepository(session=db_session)
        msg = await repo.create(
            dialog_id=dialog.id,
            sender_id=uuid.uuid4(),
            text="Test message",
            client_message_id=str(uuid.uuid4()),
        )
        found = await repo.get_by_id(msg.id)
        assert found is not None
        assert found.id == msg.id
        assert found.text == "Test message"

    async def test_get_by_dialog(self, db_session: AsyncSession) -> None:
        dialog_repo = DialogsRepository(session=db_session)
        dialog = await dialog_repo.create(dialog_type="direct")
        sender = uuid.uuid4()
        repo = MessagesRepository(session=db_session)
        await repo.create(
            dialog_id=dialog.id,
            sender_id=sender,
            text="first",
            client_message_id=str(uuid.uuid4()),
        )
        await repo.create(
            dialog_id=dialog.id,
            sender_id=sender,
            text="second",
            client_message_id=str(uuid.uuid4()),
        )
        messages = await repo.get_by_dialog(dialog.id)
        assert len(messages) == 2
        assert messages[0].text == "first"
        assert messages[1].text == "second"

    async def test_get_by_dialog_with_pagination(self, db_session: AsyncSession) -> None:
        dialog_repo = DialogsRepository(session=db_session)
        dialog = await dialog_repo.create(dialog_type="direct")
        sender = uuid.uuid4()
        repo = MessagesRepository(session=db_session)
        for i in range(5):
            await repo.create(
                dialog_id=dialog.id,
                sender_id=sender,
                text=f"msg-{i}",
                client_message_id=str(uuid.uuid4()),
            )
        page = await repo.get_by_dialog(dialog.id, limit=2, offset=1)
        assert len(page) == 2
        assert page[0].text == "msg-1"
        assert page[1].text == "msg-2"

    async def test_set_status(self, db_session: AsyncSession) -> None:
        dialog_repo = DialogsRepository(session=db_session)
        dialog = await dialog_repo.create(dialog_type="direct")
        repo = MessagesRepository(session=db_session)
        msg = await repo.create(
            dialog_id=dialog.id,
            sender_id=uuid.uuid4(),
            text="Status test",
            client_message_id=str(uuid.uuid4()),
        )
        status = await repo.set_status(
            message_id=msg.id,
            user_id=uuid.uuid4(),
            status="delivered",
        )
        assert status.id is not None
        assert status.status == MessageStatusEnum.DELIVERED
