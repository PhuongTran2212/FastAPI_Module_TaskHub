# app/core/security.py
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
    issued_at: datetime


def hash_password(password: str) -> str:
    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
    return hashed.decode("utf-8")


def verify_password(password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(
            password.encode("utf-8"),
            hashed_password.encode("utf-8"),
        )
    except ValueError:
        # Hash không hợp lệ (vd user seed Day 2) hoặc mật khẩu > 72 byte
        return False


# Dùng khi email không tồn tại để thời gian phản hồi giống như sai mật khẩu
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

    payload = {
        "sub": str(user_id),  # PyJWT >= 2.10 bắt buộc sub là string
        "type": token_type.value,
        "jti": jti,
        "iat": now,
        "exp": expires_at,
    }
    token = jwt.encode(
        payload,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    return token, jti, expires_at


def create_access_token(user_id: int) -> str:
    minutes = get_settings().access_token_expire_minutes
    token, _, _ = _create_token(user_id, TokenType.ACCESS, timedelta(minutes=minutes))
    return token


def create_refresh_token(user_id: int) -> tuple[str, str, datetime]:
    days = get_settings().refresh_token_expire_days
    return _create_token(user_id, TokenType.REFRESH, timedelta(days=days))


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

    jti = payload["jti"]
    if not isinstance(jti, str) or not jti:
        raise TokenError(messages.INVALID_TOKEN_ID)

    return TokenPayload(
        user_id=user_id,
        jti=jti,
        # PyJWT đã kiểm tra iat là số; JWT lưu iat theo giây
        issued_at=datetime.fromtimestamp(payload["iat"], UTC),
    )
