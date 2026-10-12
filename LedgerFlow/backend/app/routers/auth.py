"""Signing in."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_session
from ..models import User
from ..security import ROLE_LABELS, create_access_token, get_current_user, verify_password
from ..serializers import user_detail

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
            status_code=status.HTTP_403_FORBIDDEN, detail="This account is no longer active."
        )
    return {
        "access_token": create_access_token(user.email, role=user.role),
        "token_type": "bearer",
        "user": user_detail(user),
    }


@router.post("/sign-in")
def sign_in(body: SignIn, session: Session = Depends(get_session)) -> dict:
    return _issue(session, body.email, body.password)


@router.post("/token")
def token(
    form: OAuth2PasswordRequestForm = Depends(), session: Session = Depends(get_session)
) -> dict:
    """The form-encoded shape, so the generated API page can sign in too."""
    return _issue(session, form.username, form.password)


@router.get("/me")
def me(user: User = Depends(get_current_user)) -> dict:
    return user_detail(user)


@router.get("/people")
def people(session: Session = Depends(get_session)) -> list[dict]:
    """Who can sign in, for the demonstration's sign-in picker.

    Open on purpose, and only while this is a demonstration: an unauthenticated
    list of everybody's name, address and role is a gift to anybody phishing
    the finance team. Set ENVIRONMENT to anything else and it closes.
    """
    if settings.environment != "demo":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Not available."
        )
    rows = session.scalars(select(User).where(User.is_active.is_(True)).order_by(User.id))
    return [
        {
            "email": u.email,
            "name": u.full_name,
            "role": u.role,
            "role_label": ROLE_LABELS.get(u.role, u.role),
        }
        for u in rows
    ]
