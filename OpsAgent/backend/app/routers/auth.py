"""Signing in.

The role on the token is the role the permission layer uses. It comes
from the database at sign-in and is never taken from anything a request
body says about itself.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_session
from ..models import User
from ..security import create_access_token, get_current_user, verify_password
from ..serializers import reach_detail, user_detail
from ..services.permissions import reach_of

router = APIRouter(prefix="/api/auth", tags=["auth"])


class SignIn(BaseModel):
    email: str
    password: str


def _issue(session: Session, email: str, password: str) -> dict:
    user = session.scalar(select(User).where(User.email == email.strip().lower()))
    if user is None or not verify_password(password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="That email address and password do not match.",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account is no longer active.",
        )
    body = user_detail(user)
    body["reach"] = reach_detail(reach_of(session, user))
    return {
        "access_token": create_access_token(user.email, role=user.role),
        "token_type": "bearer",
        "user": body,
    }


@router.post("/sign-in")
def sign_in(body: SignIn, session: Session = Depends(get_session)) -> dict:
    return _issue(session, body.email, body.password)


@router.post("/token")
def token(
    form: OAuth2PasswordRequestForm = Depends(),
    session: Session = Depends(get_session),
) -> dict:
    """The form-encoded shape, so the generated API page can sign in too."""
    return _issue(session, form.username, form.password)


@router.get("/me")
def me(
    user: User = Depends(get_current_user), session: Session = Depends(get_session)
) -> dict:
    body = user_detail(user)
    body["reach"] = reach_detail(reach_of(session, user))
    return body
