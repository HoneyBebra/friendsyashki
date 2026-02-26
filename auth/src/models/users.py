from uuid import UUID, uuid4

from sqlalchemy import Index
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import BaseModel


class Users(BaseModel):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
        unique=True,
        nullable=False,
    )
    login: Mapped[str] = mapped_column()
    password: Mapped[str] = mapped_column()
    encrypted_phone_number: Mapped[str] = mapped_column(nullable=True, unique=True)
    phone_number_hash: Mapped[str] = mapped_column(nullable=True, unique=True)
    encrypted_email: Mapped[str] = mapped_column(nullable=True, unique=True)
    email_hash: Mapped[str] = mapped_column(nullable=True, unique=True)

    __table_args__ = (
        Index("ix_users_login", "login"),
    )
