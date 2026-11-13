import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

from app.core import messages
from app.core.config import get_settings
from app.core.enums import TokenType
from app.core.exceptions import TokenError


@dataclass(frozen=True)
class TokenPayload:
    user_id: int
    jti: str


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed_password.encode("utf-8"))
    except ValueError:
        return False


DUMMY_PASSWORD_HASH = hash_password("taskhub-dummy-password")


def _create_token(
    user_id: int,
    token_type: TokenType,
    expires_delta: timedelta,
) -> tuple[str, str, datetime]:
    settings = get_settings()
    now = datetime.now(UTC)
    expires_at = now + expires_delta
    jti = uuid.uuid4().hex
    token = jwt.encode(
        {
            "sub": str(user_id),
            "type": token_type.value,
            "jti": jti,
            "iat": now,
            "exp": expires_at,
        },
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    return token, jti, expires_at


def create_access_token(user_id: int) -> str:
    return _create_token(
        user_id,
        TokenType.ACCESS,
        timedelta(minutes=get_settings().access_token_expire_minutes),
    )[0]


def create_refresh_token(user_id: int) -> tuple[str, str, datetime]:
    return _create_token(
        user_id,
        TokenType.REFRESH,
        timedelta(days=get_settings().refresh_token_expire_days),
    )


def decode_token(token: str, expected_type: TokenType) -> TokenPayload:
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["sub", "jti", "exp", "iat"]},
        )
    except jwt.InvalidTokenError as exc:
        raise TokenError(messages.INVALID_TOKEN) from exc
    if payload.get("type") != expected_type.value:
        raise TokenError(messages.INVALID_TOKEN_TYPE)
    try:
        user_id = int(payload["sub"])
    except (TypeError, ValueError) as exc:
        raise TokenError(messages.INVALID_TOKEN_SUBJECT) from exc
    if user_id <= 0:
        raise TokenError(messages.INVALID_TOKEN_SUBJECT)
    if not isinstance(payload["jti"], str) or not payload["jti"]:
        raise TokenError(messages.INVALID_TOKEN_ID)
    return TokenPayload(user_id=user_id, jti=payload["jti"])
