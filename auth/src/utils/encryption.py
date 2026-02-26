import hashlib

from cryptography.fernet import Fernet
from passlib.context import CryptContext

from src.core.config import settings

pwd_context = CryptContext(schemes=["pbkdf2_sha256"])

fernet = Fernet(settings.encryption_user_data_secret_key)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def hash_user_data(data: str) -> str:
    return hashlib.sha256(
        f"{data}{settings.encryption_user_data_secret_key}".encode(),
    ).hexdigest()


def verify_user_data(data: str, hashed_data: str) -> bool:
    return hash_user_data(data) == hashed_data


def encrypt_data(data: str) -> str:
    return fernet.encrypt(data.encode()).decode()


def decrypt_data(data: str) -> str:
    return fernet.decrypt(data.encode()).decode()
