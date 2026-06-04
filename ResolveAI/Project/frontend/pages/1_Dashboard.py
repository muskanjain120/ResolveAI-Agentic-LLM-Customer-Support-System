import os
import sys
from datetime import timedelta

import pandas as pd
import requests
import streamlit as st

_FRONTEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _FRONTEND not in sys.path:
    sys.path.insert(0, _FRONTEND)

from utils.ui import (  # noqa: E402
    API,
    CATEGORIES,
    empty_state,
    esc,
    fetch_tickets,
    fetch_tickets_live,
    init_page,
    kpi_row,
    open_ticket,
    page_header,
    priority_badge,
    section_title,
    status_badge,
)
from utils.auth import auth_headers, ensure_role  # noqa: E402

init_page("Dashboard — ResolveAI", "📋", nav="dashboard")
ensure_role("agent")

page_header(
    "Live Ticket Queue",
    "Real-time AI triage · sub-second cached loads",
    badge="LIVE" if st.session_state.get("dash_live", True) else "PAUSED",
)


@st.fragment(run_every=timedelta(seconds=5))
def live_controls():
    st.markdown("<div class='glass-container pro-glass filter-bar'>", unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns([2.2, 1, 1, 0.7])
    with c1:
        search = st.text_input("🔍 Search", placeholder="ID, subject, status, category…")
    with c2:
        status_filter = st.selectbox("Status", ["all", "open", "pending_review", "resolved", "classifying", "drafting"])
    with c3:
        category_filter = st.selectbox("Category", ["all"] + CATEGORIES)
    with c4:
        st.session_state["dash_live"] = st.toggle("Live", value=st.session_state.get("dash_live", True))
    st.markdown("</div>", unsafe_allow_html=True)
    return search, status_filter, category_filter


search, status_filter, category_filter = live_controls()

params = {"limit": 100}
if status_filter != "all":
    params["status"] = status_filter
if category_filter != "all":
    params["category"] = category_filter


def _filter_tickets(raw: list[dict]) -> list[dict]:
    if not search.strip():
        return raw
    q = search.strip().lower()
    return [
        t
        for t in raw
        if q in str(t.get("id", ""))
        or q in (t.get("subject") or "").lower()
        or q in (t.get("category") or "").lower()
        or q in (t.get("status") or "").lower()
    ]


@st.fragment(run_every=timedelta(seconds=4))
def dashboard_live() -> None:
    if st.session_state.get("dash_live", True):
        tickets_raw = fetch_tickets_live(params)
    else:
        tickets_raw = fetch_tickets(params)

    tickets = _filter_tickets(tickets_raw)

    processing = sum(1 for t in tickets if t["status"] in ("classifying", "drafting"))
    review = sum(1 for t in tickets if t["status"] == "pending_review")
    resolved = sum(1 for t in tickets if t["status"] == "resolved")

    kpi_row([
        ("In view", len(tickets), "Filtered results", "accent-purple", "🎯"),
        ("AI active", processing, "Processing now", "accent-amber", "🤖"),
        ("Review queue", review, "Human action", "accent-cyan", "📥"),
        ("Resolved", resolved, "Completed", "accent-green", "🏁"),
    ])

    tab_queue, tab_analytics = st.tabs(["📋 Queue", "📈 Analytics"])

    with tab_analytics:
        section_title("Pipeline analytics", "Distribution across statuses & categories", icon="📊")
        if tickets:
            status_counts = {}
            for t in tickets:
                s = t["status"]
                status_counts[s] = status_counts.get(s, 0) + 1
            st.markdown("<div class='chart-wrap'>", unsafe_allow_html=True)
            status_labels = [k.replace("_", " ") for k in status_counts]
            status_df = pd.DataFrame(
                {"tickets": [status_counts[k] for k in status_counts]},
                index=status_labels,
            )
            st.bar_chart(status_df)
            st.markdown("</div>", unsafe_allow_html=True)
            cat_counts = {}
            for t in tickets:
                c = t.get("category") or "unclassified"
                cat_counts[c] = cat_counts.get(c, 0) + 1
            if len(cat_counts) > 1:
                st.caption("By category")
                cat_df = pd.DataFrame(
                    {"tickets": [cat_counts[k] for k in cat_counts]},
                    index=[str(k) for k in cat_counts],
                )
                st.bar_chart(cat_df)
        else:
            empty_state("📊", "No chart data", "Adjust filters or submit tickets.")

    with tab_queue:
        section_title("Ticket stream", "Click Open to review AI drafts", icon="⚡")
        if not tickets:
            empty_state("🔍", "No matches", "Broaden filters or create a new ticket.")
        else:
            mode = "live" if st.session_state.get("dash_live", True) else "paused"
            st.markdown(
                f'<p class="live-pill">{len(tickets)} tickets · {mode}</p>',
                unsafe_allow_html=True,
            )
            for t in tickets:
                pri = t.get("priority")
                cat = t.get("category") or "—"
                st.markdown(
                    f"""
                    <div class="ticket-card">
                        <span class="ticket-id">#{esc(t['id'])}</span>
                        <span class="ticket-subject">{esc(t['subject'])}</span>
                        <div class="ticket-meta">
                            <span class="muted">{esc(cat.title() if cat != '—' else '—')}</span>
                            {priority_badge(pri)}
                            {status_badge(t['status'])}
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                c_open, c_del = st.columns([4, 1])
                with c_open:
                    if st.button("Open →", key=f"open_{t['id']}", use_container_width=True):
                        open_ticket(t["id"])
                with c_del:
                    if st.button("Delete", key=f"del_{t['id']}", type="secondary", use_container_width=True):
                        r = requests.delete(f"{API}/tickets/{t['id']}", headers=auth_headers(), timeout=8)
                        if r.status_code in (200, 204):
                            st.toast(f"Deleted ticket #{t['id']}")
                            st.rerun()


dashboard_live()
