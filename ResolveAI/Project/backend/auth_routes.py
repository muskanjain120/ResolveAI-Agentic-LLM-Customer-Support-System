"""Authentication API routes."""

from __future__ import annotations

import os
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from backend.auth import (
    create_access_token,
    get_current_user,
    hash_password,
    verify_google_id_token,
    verify_password,
)
from backend.database import get_db
from backend.models import Agent, User
from backend.schemas import (
    AgentLoginRequest,
    CustomerLoginRequest,
    CustomerRegisterRequest,
    AuthTokenResponse,
    GoogleTokenRequest,
    UserRead,
)

router = APIRouter(prefix="/auth", tags=["auth"])

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "").strip()
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "").strip()
GOOGLE_REDIRECT_URI = os.getenv(
    "GOOGLE_REDIRECT_URI",
    "http://localhost:8000/auth/google/callback",
)
STREAMLIT_URL = os.getenv("STREAMLIT_URL", "http://localhost:8501").rstrip("/")


def _token_response(user: User | Agent, role: str) -> AuthTokenResponse:
    if role == "customer":
        assert isinstance(user, User)
        token = create_access_token(
            subject=f"customer:{user.id}",
            role="customer",
            user_id=user.id,
            email=user.email,
            name=user.name,
        )
        return AuthTokenResponse(
            access_token=token,
            role="customer",
            user=UserRead.model_validate(user),
        )
    assert isinstance(user, Agent)
    token = create_access_token(
        subject=f"agent:{user.id}",
        role="agent",
        user_id=user.id,
        email=user.email,
        name=user.name,
    )
    return AuthTokenResponse(
        access_token=token,
        role="agent",
        agent_id=user.id,
        email=user.email,
        name=user.name,
    )


@router.get("/google/start")
def google_oauth_start():
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(503, "Google OAuth not configured")
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "online",
        "prompt": "select_account",
    }
    url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params)
    return {"auth_url": url}


@router.get("/google/callback")
def google_oauth_callback(code: str | None = None, error: str | None = None, db: Session = Depends(get_db)):
    if error or not code:
        return RedirectResponse(f"{STREAMLIT_URL}/?auth_error=google_denied")
    if not GOOGLE_CLIENT_SECRET:
        return RedirectResponse(f"{STREAMLIT_URL}/?auth_error=google_not_configured")

    token_url = "https://oauth2.googleapis.com/token"
    data = {
        "code": code,
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "grant_type": "authorization_code",
    }
    try:
        r = httpx.post(token_url, data=data, timeout=15)
        r.raise_for_status()
        tokens = r.json()
        id_token = tokens.get("id_token")
        if not id_token:
            raise ValueError("No id_token in response")
        info = verify_google_id_token(id_token)
    except Exception as e:
        reason = str(e)
        # trim to keep URL short
        if len(reason) > 120:
            reason = reason[:117] + "..."
        return RedirectResponse(f"{STREAMLIT_URL}/?auth_error=google_exchange_failed&reason={httpx.QueryParams({'msg': reason})['msg']}")

    google_sub = info.get("sub")
    email = info.get("email")
    name = info.get("name") or (email.split("@")[0] if email else "Customer")
    picture = info.get("picture")

    if not google_sub or not email:
        return RedirectResponse(f"{STREAMLIT_URL}/?auth_error=google_profile_incomplete")

    user = db.query(User).filter(User.google_sub == google_sub).first()
    if not user:
        user = db.query(User).filter(User.email == email).first()
        if user:
            user.google_sub = google_sub
        else:
            user = User(
                name=name,
                email=email,
                google_sub=google_sub,
                picture=picture,
                plan="free",
            )
            db.add(user)
    else:
        user.name = name or user.name
        user.picture = picture or user.picture
    db.commit()
    db.refresh(user)

    access = create_access_token(
        subject=f"customer:{user.id}",
        role="customer",
        user_id=user.id,
        email=user.email,
        name=user.name,
    )
    return RedirectResponse(f"{STREAMLIT_URL}/?access_token={access}")


@router.post("/google", response_model=AuthTokenResponse)
def google_token_login(payload: GoogleTokenRequest, db: Session = Depends(get_db)):
    """Sign in with Google ID token (One Tap / GIS button)."""
    info = verify_google_id_token(payload.credential)
    google_sub = info.get("sub")
    email = info.get("email")
    name = info.get("name") or (email.split("@")[0] if email else "Customer")
    picture = info.get("picture")
    if not google_sub or not email:
        raise HTTPException(400, "Incomplete Google profile")

    user = db.query(User).filter(User.google_sub == google_sub).first()
    if not user:
        user = db.query(User).filter(User.email == email).first()
        if user:
            user.google_sub = google_sub
        else:
            user = User(name=name, email=email, google_sub=google_sub, picture=picture, plan="free")
            db.add(user)
    else:
        user.name = name or user.name
        user.picture = picture or user.picture
    db.commit()
    db.refresh(user)
    return _token_response(user, "customer")


# ── Customer email/password (manual login/register) ────────────────


@router.post("/customer/register", response_model=AuthTokenResponse)
def customer_register(payload: CustomerRegisterRequest, db: Session = Depends(get_db)):
    email = payload.email.lower().strip()
    existing = db.query(User).filter(User.email == email).first()
    if existing:
        raise HTTPException(409, "Email already registered")

    user = User(
        name=payload.name.strip(),
        email=email,
        password_hash=hash_password(payload.password),
        plan="free",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return _token_response(user, "customer")


@router.post("/customer/login", response_model=AuthTokenResponse)
def customer_login(payload: CustomerLoginRequest, db: Session = Depends(get_db)):
    email = payload.email.lower().strip()
    user = db.query(User).filter(User.email == email).first()
    if not user or not user.password_hash or not verify_password(payload.password, user.password_hash):
        raise HTTPException(401, "Invalid email or password")
    return _token_response(user, "customer")


@router.post("/agent/login", response_model=AuthTokenResponse)
def agent_login(payload: AgentLoginRequest, db: Session = Depends(get_db)):
    agent = db.query(Agent).filter(Agent.email == payload.email.lower().strip()).first()
    if not agent or not agent.is_active or not verify_password(payload.password, agent.password_hash):
        raise HTTPException(401, "Invalid email or password")
    return _token_response(agent, "agent")


@router.get("/me")
def auth_me(user=Depends(get_current_user)):
    return {
        "role": user.role,
        "user_id": user.user_id,
        "email": user.email,
        "name": user.name,
    }
