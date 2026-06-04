import json
import os
import sys
import time

import requests
import streamlit as st

_FRONTEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _FRONTEND not in sys.path:
    sys.path.insert(0, _FRONTEND)

from utils.ui import (  # noqa: E402
    API,
    STATUS_LABELS,
    cached_get,
    esc,
    format_time,
    glass_close,
    glass_open,
    init_page,
    invalidate_cache,
    page_header,
    section_title,
    priority_badge,
    status_badge,
)
from utils.auth import auth_headers, ensure_role  # noqa: E402

init_page("Ticket Detail — ResolveAI", "🎫", nav="ticket")
ensure_role("agent")

if "selected_ticket" not in st.session_state:
    st.warning("No ticket selected. Pick one from the Dashboard.")
    if st.button("← Back to Dashboard"):
        st.switch_page("pages/1_Dashboard.py")
    st.stop()

ticket_id = st.session_state["selected_ticket"]

ticket, ok = cached_get(f"/tickets/{ticket_id}", token=st.session_state.get("access_token", ""))
if not ok or not ticket:
    st.error("Could not load ticket. It may have been removed.")
    if st.button("← Back to Dashboard"):
        st.switch_page("pages/1_Dashboard.py")
    st.stop()

status = ticket["status"]
pri = ticket.get("priority") or "unknown"
cat = ticket.get("category") or "unknown"

page_header(
    ticket["subject"],
    f"Ticket #{ticket_id} · Created {format_time(ticket.get('created_at'))}",
    badge=STATUS_LABELS.get(status, status),
)

st.markdown(
    f"""
    <div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:20px;align-items:center;">
        {priority_badge(pri if pri != 'unknown' else None)}
        <span class="badge" style="background:rgba(255,255,255,0.08);border:1px solid var(--border);">
            {esc(cat.upper())}
        </span>
        {status_badge(status)}
    </div>
    """,
    unsafe_allow_html=True,
)

# Pipeline timeline
steps = [
    ("open", "Received", "Ticket submitted"),
    ("classifying", "Classification", "AI assigns category & priority"),
    ("drafting", "RAG Draft", "Solution agent drafts response"),
    ("pending_review", "Human Review", "Approve or edit draft"),
    ("resolved", "Resolved", "Response sent to customer"),
]
order = [s[0] for s in steps]
current_idx = order.index(status) if status in order else -1

timeline_html = "<div class='glass-container'><h4 style='margin-top:0'>Pipeline</h4><div class='timeline'>"
for i, (key, title, desc) in enumerate(steps):
    cls = "timeline-step"
    if i < current_idx or status == "resolved" and key == "resolved":
        cls += " done"
    elif key == status or (status == "approved" and key == "resolved"):
        cls += " active"
    timeline_html += f"<div class='{cls}'><h4>{esc(title)}</h4><p>{esc(desc)}</p></div>"
timeline_html += "</div></div>"
st.markdown(timeline_html, unsafe_allow_html=True)

col_main, col_side = st.columns([2, 1])

with col_main:
    tab_msg, tab_resolution, tab_logs = st.tabs(["Customer message", "Resolution", "Agent logs"])

    with tab_msg:
        glass_open()
        st.markdown("#### Customer request")
        st.markdown(
            f"<div style='line-height:1.7;color:var(--text);white-space:pre-wrap'>{esc(ticket['body'])}</div>",
            unsafe_allow_html=True,
        )
        glass_close()

    with tab_resolution:
        if status == "pending_review":
            glass_open()
            st.markdown("#### ✨ AI resolution draft")
            edited = st.text_area(
                "Review and edit before sending",
                value=ticket.get("draft_response") or "",
                height=280,
                label_visibility="collapsed",
            )
            c1, c2, c3 = st.columns(3)
            with c1:
                if st.button("✅ Approve & send", type="primary", use_container_width=True):
                    resp = requests.post(
                        f"{API}/tickets/{ticket_id}/approve",
                        json={"response_text": edited},
                        headers=auth_headers(),
                        timeout=15,
                    )
                    if resp.status_code == 200:
                        invalidate_cache()
                        st.success("Ticket resolved!")
                        time.sleep(0.8)
                        st.rerun()
                    else:
                        st.error(resp.text[:300])
            with c2:
                if st.button("🔄 Reprocess", use_container_width=True):
                    requests.post(f"{API}/tickets/{ticket_id}/reprocess", headers=auth_headers(), timeout=10)
                    st.toast("Pipeline restarted")
                    time.sleep(1)
                    st.switch_page("pages/1_Dashboard.py")
            with c3:
                if st.button("📋 Copy draft", use_container_width=True):
                    st.session_state["_clipboard"] = edited
                    st.toast("Draft copied to session — paste from text area")
            glass_close()
        elif status == "resolved":
            glass_open()
            st.markdown("#### ✅ Sent resolution")
            st.success("This ticket was resolved.")
            st.markdown(
                f"<div style='line-height:1.7;white-space:pre-wrap'>{esc(ticket.get('approved_response') or '')}</div>",
                unsafe_allow_html=True,
            )
            if ticket.get("resolved_at"):
                st.caption(f"Resolved {format_time(ticket['resolved_at'])}")
            glass_close()
        elif status in ("open", "classifying", "drafting"):
            st.info(f"AI agents are currently processing this ticket (Status: {status}). Please wait...")
            auto = st.toggle("Auto-refresh while processing", value=True)
            if auto:
                time.sleep(3)
                st.rerun()
        else:
            st.write(f"Status: **{status}**")

    with tab_logs:
        logs, ok = cached_get(f"/tickets/{ticket_id}/logs", token=st.session_state.get("access_token", ""))
        if not ok or not isinstance(logs, list):
            logs = []
        if not logs:
            st.caption("No logs for this ticket yet.")
        else:
            for log in logs:
                err = "error" if log.get("is_error") else ""
                st.markdown(
                    f"""
                    <div class="log-step {err}">
                        <span class="agent-name">{esc(log['agent_name'])}</span>
                        <div style="display:flex;justify-content:space-between;gap:12px;">
                            <span>{esc(log['step'])}</span>
                            <span class="muted" style="font-size:11px">{esc(format_time(log.get('created_at')))}</span>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                if log.get("detail"):
                    # Streamlit expander caret/icon can render incorrectly with our CSS.
                    # Use native HTML <details>/<summary> for stable UI.
                    detail_text = esc(str(log["detail"]))
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

with col_side:
    glass_open()
    st.markdown("#### Classification reasoning")
    if ticket.get("classification_reasoning"):
        st.info(ticket["classification_reasoning"])
    else:
        st.caption("Waiting for classification agent…")
    glass_close()

    glass_open()
    st.markdown("#### Knowledge base used")
    kb_used = ticket.get("kb_articles_used")
    if kb_used:
        try:
            kb_ids = json.loads(kb_used)
            if kb_ids:
                for kid in kb_ids:
                    st.markdown(f"- Article **#{kid}**")
            else:
                st.caption("No articles referenced.")
        except json.JSONDecodeError:
            st.write(kb_used)
    else:
        st.caption("Pending RAG retrieval…")
    glass_close()

    glass_open()
    st.markdown("#### Metadata")
    st.markdown(
        f"""
        - **User ID:** {ticket['user_id']}
        - **Created:** {format_time(ticket.get('created_at'))}
        - **Updated:** {format_time(ticket.get('updated_at'))}
        - **Approved:** {'Yes' if ticket.get('is_approved') else 'No'}
        """,
    )
    glass_close()

if st.button("← Back to Dashboard"):
    st.switch_page("pages/1_Dashboard.py")
