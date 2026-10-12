"""Signing in."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_session
from ..models import User
from ..security import ROLE_LABELS, create_access_token, get_current_user, verify_password
from ..seed.generator import DEMO_PASSWORD, DEMO_USERS
from ..serializers import user_out

router = APIRouter(prefix="/api/auth", tags=["Signing in"])


class SignInRequest(BaseModel):
    email: str
    password: str


class SignInResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


@router.post("/sign-in", response_model=SignInResponse)
def sign_in(payload: SignInRequest, session: Session = Depends(get_session)) -> SignInResponse:
    user = session.scalar(select(User).where(User.email == str(payload.email).lower()))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="That email address and password do not match an account.",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="This account is switched off."
        )
    token = create_access_token(user.email, role=user.role, extra={"name": user.full_name})
    return SignInResponse(access_token=token, user=user_out(user))


@router.get("/me")
def me(user: User = Depends(get_current_user)) -> dict:
    return user_out(user)


@router.get("/demo-accounts")
def demo_accounts(session: Session = Depends(get_session)) -> dict:
    """Shown on the sign-in screen so a reviewer can get straight in."""
    loaded = {u.email for u in session.scalars(select(User))}
    return {
        "password": DEMO_PASSWORD,
        "note": (
            "These accounts exist only in the demonstration data. Each one shows a "
            "different set of permissions."
        ),
        "accounts": [
            {
                "email": person["email"],
                "full_name": person["full_name"],
                "role": person["role"],
                "role_label": ROLE_LABELS.get(person["role"], person["role"]),
                "what_they_can_do": {
                    "sales_engineer": "Run a request through the agent and prepare a quote.",
                    "sales_manager": "Everything a sales engineer can do, and approve prices below the margin floor.",
                    "director": "Everything a sales manager can do, and approve quotes above the value threshold.",
                    "pricing_owner": "Own the duty tables and the exchange rates.",
                    "administrator": "Everything, including loading the demonstration data.",
                }.get(person["role"], ""),
                "available": person["email"] in loaded,
            }
            for person in DEMO_USERS
        ],
    }
