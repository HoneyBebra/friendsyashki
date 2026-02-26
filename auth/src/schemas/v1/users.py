from typing import Annotated
from uuid import UUID

from pydantic import AfterValidator, BaseModel, EmailStr, Field, model_validator

from src.schemas.v1.base import validate_password


class UserDataBase(BaseModel):
    email: EmailStr | None = Field(default=None)
    phone_number: str | None = Field(pattern=r"^\+?1?\d{9,15}$", default=None)


class UserEntersDataBaseSchema(UserDataBase):
    password: Annotated[str, AfterValidator(validate_password)]

    @model_validator(mode="before")
    def check_email_or_phone_number_exists(self) -> "UserEntersDataBaseSchema":
        if not self.get("email") and not self.get("phone_number"):
            raise ValueError("email or phone number is required")
        return self


class UserRegisterSchema(UserEntersDataBaseSchema):
    login: str = Field(min_length=3, max_length=50)
    confirm_password: Annotated[str, AfterValidator(validate_password)]

    @model_validator(mode="before")
    def check_passwords_match(self) -> "UserRegisterSchema":
        if self.get("password") != self.get("confirm_password"):
            raise ValueError("passwords do not match")
        return self


class UserLoginSchema(UserEntersDataBaseSchema):
    pass


class ResponseUserData(BaseModel):
    id: UUID
