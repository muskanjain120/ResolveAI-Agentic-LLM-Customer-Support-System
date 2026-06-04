"""JWT auth, Google OAuth verification, and FastAPI dependencies."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Annotated, Literal, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import Agent, User

JWT_SECRET = os.getenv("JWT_SECRET", "change-me-in-production-use-long-random-string")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = int(os.getenv("JWT_EXPIRE_HOURS", "72"))

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "").strip()

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
security = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(
    *,
    subject: str,
    role: Literal["customer", "agent"],
    user_id: int,
    email: str,
    name: str,
) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRE_HOURS)
    payload = {
        "sub": subject,
        "role": role,
        "uid": user_id,
        "email": email,
        "name": name,
        "exp": expire,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session",
        ) from e


def verify_google_id_token(id_token: str) -> dict:
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(
            status_code=503,
            detail="Google sign-in is not configured (GOOGLE_CLIENT_ID missing)",
        )
    try:
        from google.oauth2 import id_token as google_id_token
        from google.auth.transport import requests as google_requests

        return google_id_token.verify_oauth2_token(
            id_token,
            google_requests.Request(),
            GOOGLE_CLIENT_ID,
            # Tolerate small clock drift between Google-issued tokens and your local time.
            clock_skew_in_seconds=300,
        )
    except Exception as e:
        raise HTTPException(
            status_code=401,
            detail=f"Google sign-in failed: {e}",
        ) from e


class AuthUser:
    def __init__(self, role: str, user_id: int, email: str, name: str):
        self.role = role
        self.user_id = user_id
        self.email = email
        self.name = name


def _user_from_payload(payload: dict, db: Session) -> AuthUser:
    role = payload.get("role")
    uid = payload.get("uid")
    if role not in ("customer", "agent") or uid is None:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    if role == "customer":
        user = db.query(User).get(int(uid))
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        return AuthUser("customer", user.id, user.email, user.name)

    agent = db.query(Agent).get(int(uid))
    if not agent or not agent.is_active:
        raise HTTPException(status_code=401, detail="Agent not found or inactive")
    return AuthUser("agent", agent.id, agent.email, agent.name)


def get_optional_user(
    creds: Annotated[Optional[HTTPAuthorizationCredentials], Depends(security)],
    db: Session = Depends(get_db),
) -> Optional[AuthUser]:
    if not creds or not creds.credentials:
        return None
    payload = decode_token(creds.credentials)
    return _user_from_payload(payload, db)


def get_current_user(
    creds: Annotated[Optional[HTTPAuthorizationCredentials], Depends(security)],
    db: Session = Depends(get_db),
) -> AuthUser:
    if not creds or not creds.credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")
    payload = decode_token(creds.credentials)
    return _user_from_payload(payload, db)


def require_customer(user: Annotated[AuthUser, Depends(get_current_user)]) -> AuthUser:
    if user.role != "customer":
        raise HTTPException(status_code=403, detail="Customer access only")
    return user


def require_agent(user: Annotated[AuthUser, Depends(get_current_user)]) -> AuthUser:
    if user.role != "agent":
        raise HTTPException(status_code=403, detail="Agent access only")
    return user
