from __future__ import annotations

import os
from urllib.parse import urlparse, parse_qs

import requests
import streamlit as st

API = os.getenv("API_BASE_URL", "http://localhost:8000")


def auth_headers() -> dict:
    token = st.session_state.get("access_token")
    if not token:
        return {}
    return {"Authorization": f"Bearer {token}"}


def is_authenticated() -> bool:
    return bool(st.session_state.get("access_token") and st.session_state.get("role"))


def logout() -> None:
    for key in ("access_token", "role", "user_name", "user_email", "user_id"):
        st.session_state.pop(key, None)
    # Remove persisted token from URL (so refresh stays logged out)
    try:
        st.query_params.clear()
    except Exception:
        pass


def set_auth(access_token: str, role: str, name: str, email: str, user_id: int | None = None) -> None:
    st.session_state["access_token"] = access_token
    st.session_state["role"] = role
    st.session_state["user_name"] = name
    st.session_state["user_email"] = email
    if user_id is not None:
        st.session_state["user_id"] = user_id
    # Persist across refreshes by keeping token in URL query params.
    # NOTE: this is acceptable for local dev; for production use cookies instead.
    try:
        st.query_params["access_token"] = access_token
    except Exception:
        pass


def consume_token_from_query() -> bool:
    query = st.query_params
    token = query.get("access_token")
    if not token:
        return False
    st.session_state["access_token"] = token
    r = requests.get(f"{API}/auth/me", headers=auth_headers(), timeout=10)
    if not r.ok:
        logout()
        return False
    me = r.json()
    set_auth(
        token,
        me["role"],
        me.get("name") or "User",
        me.get("email") or "",
        me.get("user_id"),
    )
    return True


def ensure_role(required_role: str, redirect_to: str = "app.py") -> None:
    if st.session_state.get("role") != required_role:
        st.warning("Please sign in with the correct account.")
        st.switch_page(redirect_to)

