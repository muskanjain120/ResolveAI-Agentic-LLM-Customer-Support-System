import os
import sys
from datetime import timedelta

import requests
import streamlit as st

_FRONTEND = os.path.dirname(os.path.abspath(__file__))
if _FRONTEND not in sys.path:
    sys.path.insert(0, _FRONTEND)

from utils.auth import consume_token_from_query, is_authenticated, logout, set_auth  # noqa: E402
from utils.ui import (  # noqa: E402
    API,
    PROJECT_NAME,
    api_health,
    empty_state,
    esc,
    feature_card,
    fetch_customer_tickets_live,
    fetch_tickets,
    init_page,
    kpi_row,
    open_ticket,
    page_header,
    section_title,
    status_badge,
)

consume_token_from_query()
init_page(
    f"{PROJECT_NAME} — Command Center",
    "⚡",
    nav="home",
    show_sidebar=is_authenticated(),
)

if not is_authenticated():
    st.markdown(
        """
        <div class="hero">
            <div class="hero-badge">● Secure access enabled</div>
            <h1>Welcome to ResolveAI</h1>
            <p>Customer login uses Google OAuth. Agent login is restricted to authorized staff credentials.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if "google_auth_url" not in st.session_state:
        st.session_state["google_auth_url"] = ""
    if "login_mode" not in st.session_state:
        st.session_state["login_mode"] = "customer"

    c1, c2 = st.columns(2)
    with c1:
        active = "is-active" if st.session_state.get("login_mode") == "customer" else ""
        st.markdown(
            f"""
            <div class="login-flip-card login-card-customer {active}">
                <div class="login-flip-face front">
                    <div class="login-card-header">
                        <div class="login-icon">👤</div>
                        <div>
                            <h3>Customer</h3>
                            <p>Submit support tickets and track agent-reviewed responses.</p>
                        </div>
                    </div>
                    <div class="login-tags">
                        <span>Google OAuth</span><span>Email Login</span><span>Live Updates</span>
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button("Use Customer Login", key="pick_customer", use_container_width=True):
            st.session_state["login_mode"] = "customer"
            st.rerun()
    with c2:
        active = "is-active" if st.session_state.get("login_mode") == "agent" else ""
        st.markdown(
            f"""
            <div class="login-flip-card login-card-agent {active}">
                <div class="login-flip-face front">
                    <div class="login-card-header">
                        <div class="login-icon">🛡️</div>
                        <div>
                            <h3>Agent</h3>
                            <p>Restricted staff access for dashboard, review, KB, and logs.</p>
                        </div>
                    </div>
                    <div class="login-tags">
                        <span>Role Guarded</span><span>Ops Metrics</span><span>Approvals</span>
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button("Use Agent Login", key="pick_agent", use_container_width=True):
            st.session_state["login_mode"] = "agent"
            st.rerun()

    st.markdown("<div class='login-form-panel'>", unsafe_allow_html=True)
    if st.session_state.get("login_mode") == "customer":
        st.markdown("### Customer Sign In")
        customer_tabs = st.tabs(["Google", "Email Login", "Register"])

        with customer_tabs[0]:
            if st.button(
                "Continue with Google",
                key="google_login",
                type="primary",
                use_container_width=True,
            ):
                r = requests.get(f"{API}/auth/google/start", timeout=10)
                if r.ok:
                    st.session_state["google_auth_url"] = r.json()["auth_url"]
                else:
                    st.error(r.text[:200])
            if st.session_state.get("google_auth_url"):
                st.link_button(
                    "Open Google Sign-In",
                    st.session_state["google_auth_url"],
                    use_container_width=True,
                )

        with customer_tabs[1]:
            with st.form("customer_email_login"):
                email = st.text_input("Email")
                password = st.text_input("Password", type="password")
                submitted = st.form_submit_button(
                    "Sign in",
                    type="primary",
                    use_container_width=True,
                )
            if submitted:
                if not email.strip() or not password:
                    st.error("Email and password are required.")
                else:
                    r = requests.post(
                        f"{API}/auth/customer/login",
                        json={"email": email.strip(), "password": password},
                        timeout=10,
                    )
                    if r.ok:
                        data = r.json()
                        user = data.get("user") or {}
                        set_auth(
                            data["access_token"],
                            "customer",
                            user.get("name") or "Customer",
                            user.get("email") or email.strip(),
                            user.get("id"),
                        )
                        st.rerun()
                    else:
                        st.error(r.text[:200])

        with customer_tabs[2]:
            with st.form("customer_email_register"):
                name = st.text_input("Full name")
                email = st.text_input("Email")
                password = st.text_input("Password", type="password")
                submitted = st.form_submit_button(
                    "Create account",
                    type="primary",
                    use_container_width=True,
                )
            if submitted:
                if not name.strip() or not email.strip() or not password:
                    st.error("Name, email, and password are required.")
                else:
                    r = requests.post(
                        f"{API}/auth/customer/register",
                        json={"name": name.strip(), "email": email.strip(), "password": password},
                        timeout=10,
                    )
                    if r.ok:
                        data = r.json()
                        user = data.get("user") or {}
                        set_auth(
                            data["access_token"],
                            "customer",
                            user.get("name") or name.strip(),
                            user.get("email") or email.strip(),
                            user.get("id"),
                        )
                        st.rerun()
                    else:
                        st.error(r.text[:200])
    else:
        st.markdown("### Agent Sign In")
        with st.form("agent_login"):
            email = st.text_input("Agent email")
            password = st.text_input("Password", type="password")
            submit = st.form_submit_button("Sign in as Agent", type="primary", use_container_width=True)
        if submit:
            r = requests.post(
                f"{API}/auth/agent/login",
                json={"email": email, "password": password},
                timeout=10,
            )
            if r.ok:
                data = r.json()
                set_auth(data["access_token"], "agent", data.get("name") or "Agent", data.get("email") or "", data.get("agent_id"))
                st.rerun()
            else:
                st.error("Invalid agent credentials.")
    st.markdown("</div>", unsafe_allow_html=True)
    st.stop()

online, _, gemini_ok = api_health()

if st.session_state.get("role") == "customer":
    name = st.session_state.get("user_name") or "there"

    page_header(
        f"Welcome back, {name}",
        "Your support hub — live ticket updates without refreshing",
        badge="LIVE",
    )

    section_title("Quick actions", "What would you like to do?", icon="🚀")
    c1, c2 = st.columns(2)
    with c1:
        feature_card(
            "✉️",
            "Customer Portal",
            "Create a new ticket and view full history with agent responses.",
            ["Submit", "Track", "Review"],
            "cyan",
        )
        if st.button("Open Customer Portal →", type="primary", use_container_width=True):
            st.switch_page("pages/5_New_Ticket.py")
    with c2:
        feature_card(
            "📋",
            "Live updates",
            "Ticket status and agent replies refresh automatically every few seconds.",
            ["Auto-sync", "No refresh", "Real-time"],
            "purple",
        )

    @st.fragment(run_every=timedelta(seconds=4))
    def customer_home_live() -> None:
        tickets = fetch_customer_tickets_live({"limit": 100}) if online else []
        total = len(tickets)
        pending = sum(
            1
            for t in tickets
            if t.get("status") in ("open", "classifying", "drafting", "pending_review")
        )
        resolved = sum(1 for t in tickets if t.get("status") in ("resolved", "approved", "closed"))
        with_review = sum(1 for t in tickets if t.get("approved_response"))

        kpi_row([
            ("My tickets", total, "All submissions", "accent-purple", "🎫"),
            ("In progress", pending, "AI or agent working", "accent-amber", "⚙️"),
            ("With response", with_review, "Agent reply available", "accent-cyan", "💬"),
            ("Resolved", resolved, "Closed tickets", "accent-green", "✅"),
        ])

        st.markdown("---")
        section_title("Recent tickets", "Updates when agents approve or status changes", icon="📡")

        if not online:
            st.error("Backend offline — run: `.\\run.ps1` or restart the API server.")
        elif not tickets:
            empty_state(
                "📭",
                "No tickets yet",
                "Open Customer Portal to submit your first support request.",
                cta="Use the button above →",
            )
        else:
            st.markdown(
                f'<p class="live-pill">{len(tickets)} ticket(s) · syncing live</p>',
                unsafe_allow_html=True,
            )
            for t in tickets[:5]:
                status = t.get("status", "open")
                st.markdown(
                    f"""
                    <div class="ticket-card" style="margin-bottom:8px">
                        <span class="ticket-id">#{esc(t['id'])}</span>
                        <span class="ticket-subject">{esc((t.get('subject') or '')[:55])}</span>
                        {status_badge(status)}
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                if t.get("approved_response"):
                    st.caption(f"Agent: {t['approved_response'][:120]}…")
            if st.button("View all in Customer Portal", use_container_width=True, key="home_to_portal"):
                st.switch_page("pages/5_New_Ticket.py")

    customer_home_live()
    st.stop()

tickets = fetch_tickets({"limit": 100}) if online else []

total = len(tickets)
pending = sum(1 for t in tickets if t.get("status") == "pending_review")
resolved = sum(1 for t in tickets if t.get("status") == "resolved")
processing = sum(1 for t in tickets if t.get("status") in ("classifying", "drafting"))

st.markdown(
    """
    <div class="hero">
        <div class="hero-badge">● Neural pipeline active</div>
        <h1>AI Support Command Center</h1>
        <p>
            Autonomous classification, RAG-powered resolution drafting, and human-in-the-loop
            approval — orchestrated in real time by Gemini agents.
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)

kpi_row([
    ("Total tickets", total, "All-time queue volume", "accent-purple", "📊"),
    ("AI processing", processing, "Classifying & drafting", "accent-amber", "⚙️"),
    ("Needs review", pending, "Human approval queue", "accent-cyan", "👁️"),
    ("Resolved", resolved, "Successfully closed", "accent-green", "✅"),
])

section_title("Mission control", "Jump into any module — optimized for speed", icon="🚀")

c1, c2, c3 = st.columns(3)
with c1:
    feature_card(
        "📋",
        "Live Dashboard",
        "Filter, search, and triage tickets with live sync and analytics.",
        ["Real-time", "Filters", "Charts"],
        "purple",
    )
    if st.button("Launch Dashboard →", key="nav_dash", use_container_width=True, type="primary"):
        st.switch_page("pages/1_Dashboard.py")
with c2:
    feature_card(
        "✉️",
        "New Ticket",
        "Submit customer requests and watch the full agent pipeline execute.",
        ["Gemini", "RAG", "Async"],
        "cyan",
    )
    if st.button("Create Ticket →", key="nav_new", use_container_width=True, type="primary"):
        st.switch_page("pages/5_New_Ticket.py")
with c3:
    feature_card(
        "🧠",
        "Agent Logs",
        "Deep trace of classification, retrieval, and drafting decisions.",
        ["Tracing", "Debug", "Live"],
        "amber",
    )
    if st.button("Open Agent Logs →", key="nav_logs", use_container_width=True, type="primary"):
        st.switch_page("pages/4_Agent_Logs.py")

st.markdown("---")
section_title("Activity feed", "Latest pipeline events", icon="📡")

if not online:
    st.error("Backend offline — run: `.\\run.ps1` or `uvicorn backend.server:app --reload`")
elif not gemini_ok:
    st.warning("Gemini API key missing — add GEMINI_API_KEY to `.env` and restart the API.")
elif pending > 0:
    st.markdown(
        f'<p class="live-pill">⚡ {pending} ticket(s) need your review now</p>',
        unsafe_allow_html=True,
    )
    if st.button(f"⚡ Review next ({pending} pending)", type="primary", use_container_width=True):
        for t in tickets:
            if t.get("status") == "pending_review":
                open_ticket(t["id"])
                break
elif not tickets:
    empty_state(
        "📭",
        "Queue is empty",
        "Submit your first ticket to activate the AI pipeline.",
        cta="Go to New Ticket in the sidebar →",
    )
else:
    for t in tickets[:6]:
        status = t.get("status", "open").replace("_", " ")
        pri = t.get("priority") or "—"
        st.markdown(
            f"""
            <div class="ticket-card" style="margin-bottom:8px">
                <span class="ticket-id">#{t['id']}</span>
                <span class="ticket-subject">{esc(t['subject'][:55])}</span>
                <span class="badge badge-medium">{pri}</span>
                <span class="muted">{status}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
