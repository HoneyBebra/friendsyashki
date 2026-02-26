from typing import Any

from fastapi import Depends, Response

from src.core.config import settings
from src.exceptions.users import InvalidCredentials, UserAlreadyExists
from src.models.users import Users
from src.repositories.jwt_token import JwtTokenRepository
from src.repositories.users import UsersRepository
from src.schemas.v1.users import UserLoginSchema, UserRegisterSchema
from src.utils.encryption import encrypt_data, hash_password, hash_user_data, verify_password
from src.utils.jwt import create_token


class UsersService:
    def __init__(
            self,
            users_repository: UsersRepository = Depends(),
            jwt_token_repository: JwtTokenRepository = Depends(),
    ) -> None:
        self.users_repository = users_repository
        self.jwt_token_repository = jwt_token_repository

    async def create(self, user_data: UserRegisterSchema) -> Users:
        email_hash, encrypted_email = await self.__get_personal_or_raise_if_exists(
            raw_data=user_data.email,
            field_name_for_check_existing_in_db="email_hash",
        )
        phone_number_hash, encrypted_phone_number = await self.__get_personal_or_raise_if_exists(
            raw_data=user_data.phone_number,
            field_name_for_check_existing_in_db="phone_number_hash",
        )

        password_hash = hash_password(password=user_data.password)

        user = await self.users_repository.create(
            login=user_data.login,
            password_hash=password_hash,
            encrypted_email=encrypted_email,
            encrypted_phone_number=encrypted_phone_number,
            email_hash=email_hash,
            phone_number_hash=phone_number_hash,
        )
        return user

    async def authenticate(self, user_data: UserLoginSchema) -> Users:
        if user_data.email is None and user_data.phone_number is None:
            raise InvalidCredentials("email or phone number is required")

        fields_for_db_query: dict[str, str | None] = {}
        if user_data.email is not None:
            fields_for_db_query["email_hash"] = hash_user_data(user_data.email)
        if user_data.phone_number is not None:
            fields_for_db_query["phone_number_hash"] = hash_user_data(user_data.phone_number)

        users = await self.users_repository.read(**fields_for_db_query)

        if not users or not verify_password(user_data.password, users[0].password):
            raise InvalidCredentials

        return users[0]

    async def __get_already_used_field(self, **params_to_search: Any) -> Any:
        for field, value in params_to_search.items():
            if await self.users_repository.read(**{field: value}):
                return field
        return None

    async def add_token_to_blacklist(
            self,
            token: str,
            expires_in: int,
    ) -> None:
        await self.jwt_token_repository.set_token_to_blacklist(
            token=token,
            expires_in=expires_in,
        )

    async def __get_personal_or_raise_if_exists(
            self,
            raw_data: str | None,
            field_name_for_check_existing_in_db: str,
    ) -> tuple[str | None, str | None]:
        if raw_data is not None:
            data_hash = hash_user_data(raw_data)
            encrypted_data = encrypt_data(raw_data)
            already_used_field = await self.__get_already_used_field(
                **{field_name_for_check_existing_in_db: data_hash},
            )
            if already_used_field is not None:
                raise UserAlreadyExists(already_used_field.replace("_hash", ""))

            return data_hash, encrypted_data

        return None, None

    @staticmethod
    async def add_tokens_to_response(
            user_id: str,
            response: Response,
    ) -> Response:
        access_token = await create_token(
            sub=user_id,
            token_type="access",
        )
        refresh_token = await create_token(
            sub=user_id,
            token_type="refresh",
        )

        response.set_cookie(
            key=settings.access_token_key_in_cookie,
            value=access_token,
            httponly=True,
            secure=True,
        )
        response.set_cookie(
            key=settings.refresh_token_key_in_cookie,
            value=refresh_token,
            httponly=True,
            secure=True,
        )

        return response
