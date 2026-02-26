from fastapi import APIRouter, Depends, HTTPException, Response, status

from src.core.config import settings
from src.dependencies.jwt import get_access_token_data, get_refresh_token_data
from src.exceptions.users import InvalidCredentials, UserAlreadyExists
from src.schemas.v1.jwt import UserJwtSchema
from src.schemas.v1.users import ResponseUserData, UserLoginSchema, UserRegisterSchema
from src.services.users import UsersService

router = APIRouter(prefix="/users")


@router.post(
    "/signup",
    description="Creating user",
    summary="Validating fields -> "
            "Checking if user already created -> "
            "Creating user -> "
            "logging in user",
    responses={
        status.HTTP_204_NO_CONTENT: {
            "model": None,
            "description": "User created and logged in"
        },
        status.HTTP_409_CONFLICT: {
            "model": None,
            "description": "User already created",
        },
        status.HTTP_422_UNPROCESSABLE_ENTITY: {
            "description": "Wrong data was passed",
        }
    },
)
async def signup_user(
        user_data: UserRegisterSchema,
        user_service: UsersService = Depends(),
) -> Response:
    try:
        response = Response()

        user = await user_service.create(user_data)
        response = await user_service.add_tokens_to_response(
            user_id=user.id,
            response=response,
        )
        return response
    except UserAlreadyExists as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=e.message,
        ) from e


@router.post(
    "/login",
    description="Logging in user",
    summary="Validating fields -> Checking password -> Logging in user",
    responses={
        status.HTTP_204_NO_CONTENT: {
            "model": None,
            "description": "User logged in"
        },
        status.HTTP_401_UNAUTHORIZED: {
            "model": None,
            "description": "User didn't login"
        },
        status.HTTP_422_UNPROCESSABLE_ENTITY: {
            "description": "Wrong data was passed",
        }
    },
)
async def login_user(
    login_data: UserLoginSchema,
    user_service: UsersService = Depends()
) -> Response:
    try:
        response = Response()
        user = await user_service.authenticate(login_data)
        return await user_service.add_tokens_to_response(
            user_id=user.id,
            response=response,
        )
    except InvalidCredentials as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=e.message,
        ) from e


@router.get(
    "/me",
    description="Get user data",
    summary="Read user data from DB",
    responses={
        status.HTTP_200_OK: {
            "model": ResponseUserData,
            "description": "User data received"
        },
        status.HTTP_403_FORBIDDEN: {
            "model": None,
            "description": "No rights",
        }
    },
)
async def get_user(
    access_token_data: tuple[UserJwtSchema, str] = Depends(get_access_token_data),
) -> ResponseUserData:
    jwt_data, _ = access_token_data

    return {"id": jwt_data.sub}  # type: ignore[return-value]


@router.post(
    "/refresh",
    description="Refresh access token",
    summary="Get new access token and replace refresh one",
    responses={
        status.HTTP_200_OK: {
            "model": None,
            "description": "User data received"
        },
        status.HTTP_403_FORBIDDEN: {
            "model": None,
            "description": "No rights",
        }
    },
)
async def refresh_tokens(
    user_service: UsersService = Depends(),
    refresh_token_data: tuple[UserJwtSchema, str] = Depends(get_refresh_token_data),
) -> Response:
    response = Response()

    jwt_data, raw_token = refresh_token_data

    await user_service.add_token_to_blacklist(raw_token, settings.refresh_token_expire)
    return await user_service.add_tokens_to_response(
        user_id=jwt_data.sub,
        response=response,
    )


@router.post(
    "/logout",
    description="Logout user",
    summary="Logout user -> Add tokens to blacklist",
    responses={
        status.HTTP_200_OK: {
            "model": None,
            "description": "User invalidated"
        },
        status.HTTP_403_FORBIDDEN: {
            "model": None,
            "description": "No rights",
        }
    },
)
async def logout_user(
    user_service: UsersService = Depends(),
    refresh_token_data: tuple[UserJwtSchema, str] = Depends(get_refresh_token_data),
    access_token_data: tuple[UserJwtSchema, str] = Depends(get_access_token_data),
) -> None:

    _, access_raw_token = access_token_data
    _, refresh_raw_token = refresh_token_data
    await user_service.add_token_to_blacklist(access_raw_token, settings.access_token_expire)
    await user_service.add_token_to_blacklist(refresh_raw_token, settings.refresh_token_expire)
