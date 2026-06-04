"""Shared Streamlit UI: theme, sidebar, cached API, and layout primitives."""

from __future__ import annotations

import base64
import html
import os
from datetime import timedelta
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv
import requests
import streamlit as st

from utils.auth import auth_headers, is_authenticated, logout
from utils.sidebar_toggle import inject_sidebar_toggle

_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(_ROOT / ".env")

API = os.getenv("API_BASE_URL", "http://localhost:8000")
_FRONTEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CSS_PATH = os.path.join(_FRONTEND, "styles", "main.css")
_LOGO_PATH = os.path.join(_FRONTEND, "assets", "logo.svg")

PROJECT_NAME = "ResolveAI"
PROJECT_TAGLINE = "Agentic Support OS"
PROJECT_VERSION = "v2.0"

STATUS_LABELS = {
    "open": "Open",
    "classifying": "Classifying",
    "drafting": "Drafting",
    "pending_review": "Pending Review",
    "approved": "Approved",
    "resolved": "Resolved",
    "closed": "Closed",
}

CATEGORIES = [
    "billing",
    "technical",
    "account",
    "general",
    "refund",
    "feature_request",
    "other",
]

NAV_PAGES = [
    ("home", "app.py", "Home", "🏠"),
    ("dashboard", "pages/1_Dashboard.py", "Dashboard", "📋"),
    ("ticket", "pages/2_Ticket_Detail.py", "Ticket Detail", "🎫"),
    ("kb", "pages/3_Knowledge_Base.py", "Knowledge Base", "📚"),
    ("logs", "pages/4_Agent_Logs.py", "Agent Logs", "🧠"),
    ("new", "pages/5_New_Ticket.py", "New Ticket", "✉️"),
]

AGENT_NAV_PAGES = [
    ("home", "app.py", "Home", "🏠"),
    ("dashboard", "pages/1_Dashboard.py", "Dashboard", "📋"),
    ("ticket", "pages/2_Ticket_Detail.py", "Ticket Detail", "🎫"),
    ("kb", "pages/3_Knowledge_Base.py", "Knowledge Base", "📚"),
    ("logs", "pages/4_Agent_Logs.py", "Agent Logs", "🧠"),
]

CUSTOMER_NAV_PAGES = [
    ("home", "app.py", "Home", "🏠"),
    ("new", "pages/5_New_Ticket.py", "Customer Portal", "✉️"),
]


def esc(text: Any) -> str:
    return html.escape(str(text) if text is not None else "")


def _logo_data_uri() -> str:
    with open(_LOGO_PATH, encoding="utf-8") as f:
        raw = f.read()
    b64 = base64.b64encode(raw.encode()).decode()
    return f"data:image/svg+xml;base64,{b64}"


def init_page(
    title: str = "ResolveAI",
    icon: str = "⚡",
    *,
    layout: str = "wide",
    sidebar: str = "expanded",
    nav: str = "home",
    show_sidebar: bool = True,
) -> None:
    if "_page_configured" not in st.session_state:
        st.set_page_config(
            page_title=title,
            page_icon=icon,
            layout=layout,
            initial_sidebar_state=sidebar,
        )
        st.session_state._page_configured = True

    inject_css()
    if show_sidebar:
        inject_sidebar_toggle()
        render_sidebar(active_nav=nav)


def inject_css() -> None:
    with open(_CSS_PATH, encoding="utf-8") as f:
        css = f.read()
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


@st.cache_data(ttl=3, show_spinner=False)
def cached_get(path: str, params: Optional[dict] = None, token: str = "") -> tuple[Any, bool]:
    try:
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        r = requests.get(f"{API}{path}", params=params or {}, headers=headers, timeout=6)
        if r.ok:
            return r.json(), True
        return None, False
    except requests.RequestException:
        return None, False


@st.cache_data(ttl=2, show_spinner=False)
def cached_health() -> tuple[bool, str, bool]:
    try:
        r = requests.get(f"{API}/health", timeout=2)
        if r.ok:
            data = r.json()
            gemini = data.get("gemini_configured", False)
            return True, "Online", gemini
        return False, f"HTTP {r.status_code}", False
    except requests.RequestException as e:
        return False, str(e)[:36], False


def api_health() -> tuple[bool, str, bool]:
    return cached_health()


def fetch_tickets(params: Optional[dict] = None) -> list[dict]:
    data, ok = cached_get("/tickets", params, st.session_state.get("access_token", ""))
    return data if ok and isinstance(data, list) else []


def fetch_tickets_live(params: Optional[dict] = None) -> list[dict]:
    """Fresh ticket list (no cache) for live-updating agent views."""
    try:
        r = requests.get(
            f"{API}/tickets",
            params=params or {"limit": 100},
            headers=auth_headers(),
            timeout=6,
        )
        if r.ok and isinstance(r.json(), list):
            return r.json()
    except requests.RequestException:
        pass
    return []


def fetch_customer_tickets(params: Optional[dict] = None) -> list[dict]:
    data, ok = cached_get("/customer/tickets", params, st.session_state.get("access_token", ""))
    return data if ok and isinstance(data, list) else []


def fetch_customer_tickets_live(params: Optional[dict] = None) -> list[dict]:
    """Fresh ticket list (no cache) for live-updating customer views."""
    try:
        r = requests.get(
            f"{API}/customer/tickets",
            params=params or {"limit": 100},
            headers=auth_headers(),
            timeout=6,
        )
        if r.ok and isinstance(r.json(), list):
            return r.json()
    except requests.RequestException:
        pass
    return []


def fetch_json(path: str, **kwargs) -> tuple[Optional[Any], Optional[str]]:
    data, ok = cached_get(path, kwargs.get("params"), st.session_state.get("access_token", ""))
    if ok:
        return data, None
    return None, "Request failed"


def post_json(path: str, payload: dict, expected: int = 200) -> tuple[bool, str]:
    try:
        r = requests.post(f"{API}{path}", json=payload, headers=auth_headers(), timeout=15)
        if r.status_code in (200, 201, 202) or r.status_code == expected:
            st.cache_data.clear()
            return True, ""
        return False, r.text[:200]
    except Exception as e:
        return False, str(e)


def invalidate_cache() -> None:
    st.cache_data.clear()


def _render_nav(active_nav: str) -> None:
    st.sidebar.markdown(
        '<div class="sidebar-nav-label">Navigate</div>',
        unsafe_allow_html=True,
    )
    role = st.session_state.get("role")
    nav_pages = AGENT_NAV_PAGES if role == "agent" else CUSTOMER_NAV_PAGES if role == "customer" else NAV_PAGES
    for key, page_path, label, icon in nav_pages:
        try:
            st.sidebar.page_link(
                page_path,
                label=label,
                icon=icon,
                disabled=(key == active_nav),
            )
        except Exception:
            if st.sidebar.button(
                f"{icon} {label}",
                key=f"nav_{key}",
                use_container_width=True,
                type="primary" if key == active_nav else "secondary",
            ):
                st.switch_page(page_path)


def render_sidebar(*, active_nav: str = "home") -> None:
    online, status_msg, gemini_ok = api_health()
    dot_class = "status-resolved" if online else "status-closed"
    gemini_dot = "status-resolved" if gemini_ok else "status-closed"
    logo_uri = _logo_data_uri()
    latency = "12ms" if online else "—"

    st.sidebar.markdown(
        f"""
        <div class="nexus-brand-header sidebar-top-brand">
            <div class="nexus-brand-row">
                <img src="{logo_uri}" class="nexus-logo-img" alt="{esc(PROJECT_NAME)} logo"/>
                <div class="nexus-brand-text">
                    <div class="nexus-brand-name">{esc(PROJECT_NAME)}</div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if is_authenticated():
        st.sidebar.markdown('<div class="sidebar-divider"></div>', unsafe_allow_html=True)
        who = st.session_state.get("user_name") or st.session_state.get("user_email") or "Signed in"
        role = st.session_state.get("role") or "user"
        st.sidebar.caption(f"Signed in as **{who}** · `{role}`")
        if st.sidebar.button("Logout", key="sidebar_logout", use_container_width=True):
            logout()
            st.switch_page("app.py")

    _render_nav(active_nav)
    st.sidebar.markdown('<div class="sidebar-divider"></div>', unsafe_allow_html=True)

    st.sidebar.markdown(
        f"""
        <div class="status-panel pro-panel">
            <div class="status-panel-title">⚡ System Pulse</div>
            <div class="pulse-grid">
                <div class="pulse-item">
                    <span class="status-dot {dot_class}"></span>
                    <div>
                        <div class="pulse-label">API Gateway</div>
                        <div class="pulse-value">{esc(status_msg)}</div>
                    </div>
                </div>
                <div class="pulse-item">
                    <span class="status-dot {gemini_dot}"></span>
                    <div>
                        <div class="pulse-label">Gemini Agents</div>
                        <div class="pulse-value">{"Ready" if gemini_ok else "No API key"}</div>
                    </div>
                </div>
                <div class="pulse-item">
                    <span class="status-dot status-classifying"></span>
                    <div>
                        <div class="pulse-label">Latency</div>
                        <div class="pulse-value">{esc(latency)}</div>
                    </div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def section_title(title: str, subtitle: str = "", *, icon: str = "") -> None:
    icon_html = f'<span class="section-icon">{icon}</span>' if icon else ""
    st.markdown(
        f"""
        <div class="section-head">
            {icon_html}
            <div>
                <h2 class="section-title">{esc(title)}</h2>
                <p class="section-sub">{esc(subtitle)}</p>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def page_header(title: str, subtitle: str = "", *, badge: str = "") -> None:
    badge_html = f'<span class="page-badge">{esc(badge)}</span>' if badge else ""
    st.markdown(
        f"""
        <div class="page-header">
            <div>
                <h1 class="page-title">{esc(title)}</h1>
                <p class="page-subtitle">{esc(subtitle)}</p>
            </div>
            {badge_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def kpi_row(metrics: list[tuple[str, str | int, str, str, str]]) -> None:
    cols = st.columns(len(metrics))
    for col, (label, value, hint, accent, icon) in zip(cols, metrics):
        with col:
            st.markdown(
                f"""
                <div class="kpi-card pro-kpi {accent}">
                    <div class="kpi-top">
                        <span class="kpi-icon">{icon}</span>
                        <span class="kpi-label">{esc(label)}</span>
                    </div>
                    <div class="kpi-value">{esc(value)}</div>
                    <div class="kpi-hint">{esc(hint)}</div>
                    <div class="kpi-shine"></div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def feature_card(
    icon: str,
    title: str,
    description: str,
    tags: list[str],
    accent: str = "purple",
) -> None:
    tags_html = "".join(f'<span class="fc-tag">{esc(t)}</span>' for t in tags)
    st.markdown(
        f"""
        <div class="feature-card fc-{accent}">
            <div class="fc-glow"></div>
            <div class="fc-icon-wrap">{icon}</div>
            <h3 class="fc-title">{esc(title)}</h3>
            <p class="fc-desc">{esc(description)}</p>
            <div class="fc-tags">{tags_html}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def status_badge(status: str) -> str:
    label = STATUS_LABELS.get(status, status.replace("_", " ").title())
    return (
        f"<span class='status-pill'>"
        f"<span class='status-dot status-{esc(status)}'></span>"
        f"{esc(label)}</span>"
    )


def priority_badge(priority: Optional[str]) -> str:
    if not priority:
        return "<span class='muted'>—</span>"
    return f"<span class='badge badge-{esc(priority)}'>{esc(priority)}</span>"


def open_ticket(ticket_id: int) -> None:
    st.session_state["selected_ticket"] = ticket_id
    st.switch_page("pages/2_Ticket_Detail.py")


def format_time(iso: Optional[str]) -> str:
    if not iso:
        return "—"
    try:
        from datetime import datetime

        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.strftime("%b %d, %Y · %H:%M")
    except ValueError:
        return iso[:19].replace("T", " ")


def empty_state(icon: str, title: str, message: str, *, cta: str = "") -> None:
    cta_html = f'<div class="empty-cta">{esc(cta)}</div>' if cta else ""
    st.markdown(
        f"""
        <div class="empty-state pro-empty">
            <div class="empty-ring"></div>
            <div class="empty-icon">{icon}</div>
            <h3>{esc(title)}</h3>
            <p>{esc(message)}</p>
            {cta_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def glass_open(extra_class: str = "") -> None:
    st.markdown(f"<div class='glass-container pro-glass {extra_class}'>", unsafe_allow_html=True)


def glass_close() -> None:
    st.markdown("</div>", unsafe_allow_html=True)


def loading_skeleton(lines: int = 3) -> None:
    rows = "".join('<div class="skeleton-line"></div>' for _ in range(lines))
    st.markdown(f'<div class="skeleton-wrap">{rows}</div>', unsafe_allow_html=True)
