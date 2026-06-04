import os
import sys
from datetime import timedelta

import streamlit as st

_FRONTEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _FRONTEND not in sys.path:
    sys.path.insert(0, _FRONTEND)

from utils.ui import (  # noqa: E402
    cached_get,
    empty_state,
    esc,
    format_time,
    glass_close,
    glass_open,
    init_page,
    kpi_row,
    open_ticket,
    page_header,
    section_title,
)
from utils.auth import ensure_role  # noqa: E402

init_page("Agent Logs — ResolveAI", "🧠", nav="logs")
ensure_role("agent")

page_header("Agent Thought Logs", "Neural trace · cached · fragment refresh")


@st.fragment(run_every=timedelta(seconds=3))
def log_filters():
    c1, c2, c3 = st.columns([1, 1, 1])
    with c1:
        agent_filter = st.selectbox(
            "Agent",
            ["all", "ClassificationAgent", "RAGSolutionAgent", "Orchestrator"],
        )
    with c2:
        ticket_filter = st.text_input("Ticket ID", placeholder="e.g. 3")
    with c3:
        errors_only = st.toggle("Errors only", value=False)
    return agent_filter, ticket_filter, errors_only


agent_filter, ticket_filter, errors_only = log_filters()

logs, ok = cached_get("/logs/recent", {"limit": 80}, st.session_state.get("access_token", ""))
if not ok or not isinstance(logs, list):
    logs = []
    st.error("Could not fetch logs.")

if agent_filter != "all":
    logs = [l for l in logs if l.get("agent_name") == agent_filter]
if ticket_filter.strip().isdigit():
    tid = int(ticket_filter.strip())
    logs = [l for l in logs if l.get("ticket_id") == tid]
if errors_only:
    logs = [l for l in logs if l.get("is_error")]

errors = sum(1 for l in logs if l.get("is_error"))
kpi_row([
    ("Entries", len(logs), "In view", "accent-purple", "📝"),
    ("Agents", len({l.get("agent_name") for l in logs}), "Unique", "accent-cyan", "🤖"),
    ("Errors", errors, "Failures", "accent-amber" if errors else "accent-green", "⚠️"),
])

section_title("Orchestration trace", "Expand any step for raw JSON detail", icon="🔬")

glass_open()
if not logs:
    empty_state("🧠", "No logs yet", "Submit a ticket to see agents think.")
else:
    for i, log in enumerate(logs):
        err = "error" if log.get("is_error") else ""
        st.markdown(
            f"""
            <div class="log-step {err}">
                <span class="agent-name">{esc(log['agent_name'])} · #{esc(log['ticket_id'])}</span>
                <div style="display:flex;justify-content:space-between;gap:12px;">
                    <span>{esc(log['step'])}</span>
                    <span class="muted" style="font-size:11px">{esc(format_time(log.get('created_at')))}</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        c1, c2 = st.columns([5, 1])
        with c1:
            if log.get("detail"):
                detail_text = esc(str(log["detail"]))
                # Native HTML accordion to avoid Streamlit expander/icon glitches
                st.markdown(
                    f"""
                    <details class="kb-details log-details">
                      <summary>Detail</summary>
                      <div class="kb-details-body">
                        <pre>{detail_text}</pre>
                      </div>
                    </details>
                    """,
                    unsafe_allow_html=True,
                )
        with c2:
            if st.button("→", key=f"log_{log.get('id', i)}", help="Open ticket"):
                open_ticket(log["ticket_id"])
glass_close()
