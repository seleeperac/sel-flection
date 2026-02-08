import datetime as dt

from cryptography.fernet import Fernet
from jose import JWTError, jwt

from app.config import settings


ALGORITHM = "HS256"


def create_access_token(subject: str) -> str:
    expire = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=settings.app_access_token_expire_minutes)
    payload = {"sub": subject, "exp": expire}
    return jwt.encode(payload, settings.app_secret_key, algorithm=ALGORITHM)


def decode_access_token(token: str) -> str:
    try:
        payload = jwt.decode(token, settings.app_secret_key, algorithms=[ALGORITHM])
        sub = payload.get("sub")
        if not sub:
            raise JWTError("missing subject")
        return sub
    except JWTError as exc:
        raise ValueError("invalid token") from exc


def _cipher() -> Fernet:
    if not settings.token_encryption_key:
        raise RuntimeError("TOKEN_ENCRYPTION_KEY is required")
    return Fernet(settings.token_encryption_key.encode())


def encrypt_text(value: str) -> str:
    return _cipher().encrypt(value.encode()).decode()


def decrypt_text(value: str) -> str:
    return _cipher().decrypt(value.encode()).decode()

