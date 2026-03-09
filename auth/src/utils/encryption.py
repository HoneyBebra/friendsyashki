import base64
import hashlib
import hmac

from cryptography.fernet import Fernet
from passlib.context import CryptContext

from src.core.config import settings

pwd_context = CryptContext(schemes=["pbkdf2_sha256"])


def _build_fernet(secret: str) -> Fernet:
    """
    Accept either a valid Fernet key or any passphrase-like secret.
    """
    try:
        return Fernet(secret.encode())
    except ValueError:
        derived_key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest())
        return Fernet(derived_key)


fernet = _build_fernet(settings.encryption_user_data_secret_key)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def hash_user_data(data: str) -> str:
    return hmac.new(
        settings.encryption_user_data_secret_key.encode(),
        data.encode(),
        hashlib.sha256,
    ).hexdigest()


def verify_user_data(data: str, hashed_data: str) -> bool:
    return hmac.compare_digest(hash_user_data(data), hashed_data)


def encrypt_data(data: str) -> str:
    return fernet.encrypt(data.encode()).decode()


def decrypt_data(data: str) -> str:
    return fernet.decrypt(data.encode()).decode()
