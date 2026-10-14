"""Sign-in, password hashing and role checks.

Deliberately built on the standard library only. A demo that cannot be started
because a password library failed to compile is a demo that does not get shown.
"""

from __future__ import annotations

import base64
import datetime as dt
import hashlib
import hmac
import json
import secrets
from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .db import get_session
from .models import User

# ---------------------------------------------------------------------------
# Passwords
# ---------------------------------------------------------------------------
_HASH_NAME = "sha256"
_ITERATIONS = 240_000


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    derived = hashlib.pbkdf2_hmac(_HASH_NAME, password.encode(), salt, _ITERATIONS)
    return f"pbkdf2_{_HASH_NAME}${_ITERATIONS}${salt.hex()}${derived.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, iterations, salt_hex, expected_hex = stored.split("$")
        if not algorithm.startswith("pbkdf2_"):
            return False
        derived = hashlib.pbkdf2_hmac(
            algorithm.removeprefix("pbkdf2_"),
            password.encode(),
            bytes.fromhex(salt_hex),
            int(iterations),
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(derived.hex(), expected_hex)


# ---------------------------------------------------------------------------
# Tokens (a small, standards-shaped JSON web token)
# ---------------------------------------------------------------------------
def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _b64url_decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def create_access_token(subject: str, *, role: str, extra: dict[str, Any] | None = None) -> str:
    now = dt.datetime.now(dt.timezone.utc)
    payload: dict[str, Any] = {
        "sub": subject,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int((now + dt.timedelta(minutes=settings.access_token_minutes)).timestamp()),
    }
    payload.update(extra or {})
    header = _b64url_encode(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    body = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode())
    signing_input = f"{header}.{body}".encode()
    signature = hmac.new(settings.jwt_secret.encode(), signing_input, hashlib.sha256).digest()
    return f"{header}.{body}.{_b64url_encode(signature)}"


class TokenError(Exception):
    pass


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        header_b64, body_b64, signature_b64 = token.split(".")
    except ValueError as exc:
        raise TokenError("The sign-in token is not in the expected form.") from exc

    expected = hmac.new(
        settings.jwt_secret.encode(), f"{header_b64}.{body_b64}".encode(), hashlib.sha256
    ).digest()
    if not hmac.compare_digest(_b64url_decode(signature_b64), expected):
        raise TokenError("The sign-in token has been altered.")

    payload = json.loads(_b64url_decode(body_b64))
    if int(payload.get("exp", 0)) < int(dt.datetime.now(dt.timezone.utc).timestamp()):
        raise TokenError("The sign-in token has expired. Please sign in again.")
    return payload


# ---------------------------------------------------------------------------
# Roles
# ---------------------------------------------------------------------------
#: Higher number means more authority. A role satisfies any requirement at or
#: below its own level, so a director can approve what a manager can approve.
ROLE_RANK: dict[str, int] = {
    "viewer": 0,
    "clerk": 10,
    "operations_lead": 20,
    "developer": 30,
    "administrator": 50,
}

ROLE_LABELS: dict[str, str] = {
    "viewer": "Viewer",
    "clerk": "Shipping clerk",
    "operations_lead": "Operations lead",
    "developer": "Developer",
    "administrator": "Administrator",
}


def role_rank(role: str) -> int:
    """-1 for a role nobody has defined, which satisfies nothing."""
    return ROLE_RANK.get(role, -1)


def role_satisfies(role: str, required: str) -> bool:
    """Does this role meet the requirement?

    Fails closed. A role that is not in the table satisfies nothing, and a
    requirement that is not in the table is met by nobody but the
    administrator.

    The reason is a hole this used to have: both sides fell back to -1, so
    an unrecognised role compared against an unrecognised requirement came
    out as -1 >= -1, which is True. Rename a role in the database without
    renaming it here, or mistype one in a decorator, and the check silently
    passed for everybody.
    """
    if role == "administrator":
        return True

    mine = role_rank(role)
    needed = role_rank(required)
    if mine < 0 or needed < 0:
        return False
    return mine >= needed


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/sign-in", auto_error=False)


def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    session: Session = Depends(get_session),
) -> User:
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Please sign in.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = decode_access_token(token)
    except TokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    user = session.scalar(select(User).where(User.email == payload.get("sub")))
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="This account is no longer active."
        )
    return user


def require_role(required: str):
    """Dependency factory: `Depends(require_role("sales_manager"))`."""

    def dependency(user: User = Depends(get_current_user)) -> User:
        if not role_satisfies(user.role, required):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"This action needs the {ROLE_LABELS.get(required, required)} role. "
                    f"You are signed in as {ROLE_LABELS.get(user.role, user.role)}."
                ),
            )
        return user

    return dependency
