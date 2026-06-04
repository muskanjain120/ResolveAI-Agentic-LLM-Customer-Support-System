import os
import sys
from datetime import timedelta

import requests
import streamlit as st

_FRONTEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _FRONTEND not in sys.path:
    sys.path.insert(0, _FRONTEND)

from utils.auth import auth_headers, ensure_role  # noqa: E402
from utils.ui import (  # noqa: E402
    API,
    esc,
    fetch_customer_tickets_live,
    glass_close,
    glass_open,
    init_page,
    invalidate_cache,
    page_header,
    section_title,
    status_badge,
)

init_page("Customer Portal — ResolveAI", "✉️", nav="new")
ensure_role("customer")

page_header(
    "Customer Portal",
    "Submit tickets and track agent-reviewed responses · updates every few seconds",
    badge="LIVE",
)


def _render_ticket_list(tickets: list[dict]) -> None:
    if not tickets:
        st.info("No tickets yet. Submit one using the form above.")
        return
    st.markdown(
        f'<p class="live-pill">{len(tickets)} ticket(s) · auto-refreshing</p>',
        unsafe_allow_html=True,
    )
    for t in tickets:
        status = t.get("status", "open")
        st.markdown(
            f"""
            <div class="ticket-card" style="margin-bottom:8px">
                <span class="ticket-id">#{esc(t['id'])}</span>
                <span class="ticket-subject">{esc((t.get('subject') or '')[:60])}</span>
                {status_badge(status)}
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown(t.get("body") or "")
        if t.get("approved_response"):
            st.success(f"**Agent review**\n\n{t['approved_response']}")
        elif status in ("classifying", "drafting", "pending_review"):
            st.caption("Your ticket is being processed by AI and support agents.")
        else:
            st.caption("Agent response will appear here after review.")
        st.markdown("---")


@st.fragment(run_every=timedelta(seconds=4))
def live_my_tickets() -> None:
    tickets = fetch_customer_tickets_live({"limit": 100})
    _render_ticket_list(tickets)


glass_open()
st.markdown("#### New ticket")
with st.form("new_ticket", clear_on_submit=True):
    subject = st.text_input("Subject *", placeholder="Brief summary of the issue")
    body = st.text_area(
        "Message *",
        height=180,
        placeholder="Describe your issue in detail.",
    )
    submitted = st.form_submit_button("Submit ticket", type="primary", use_container_width=True)
    if submitted:
        if subject.strip() and body.strip():
            res = requests.post(
                f"{API}/customer/tickets",
                json={"subject": subject.strip(), "body": body.strip()},
                headers=auth_headers(),
                timeout=15,
            )
            if res.status_code == 201:
                ticket = res.json()
                st.session_state["last_created_ticket"] = ticket["id"]
                invalidate_cache()
                st.success(f"Ticket **#{ticket['id']}** submitted — it appears below instantly.")
                st.rerun()
            else:
                st.error(res.text[:300])
        else:
            st.error("Subject and message are required.")
glass_close()

st.markdown("---")
section_title("My tickets", "Status and agent replies update automatically", icon="📋")
live_my_tickets()

if st.button("← Back to Home"):
    st.switch_page("app.py")
