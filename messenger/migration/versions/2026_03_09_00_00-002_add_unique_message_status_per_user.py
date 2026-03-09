"""add unique constraint on message_statuses (message_id, user_id)

Revision ID: 002
Revises: 001
Create Date: 2026-03-09 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

revision: str = "002"
down_revision: Union[str, Sequence[str], None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_message_status_message_user",
        "message_statuses",
        ["message_id", "user_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_message_status_message_user",
        "message_statuses",
        type_="unique",
    )
