from pydantic import BaseModel


class UserJwtSchema(BaseModel):
    sub: str
    iat: float
    exp: float
    type: str
