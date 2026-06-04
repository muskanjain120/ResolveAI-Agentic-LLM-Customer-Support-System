import os
import sys

import requests
import streamlit as st

_FRONTEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _FRONTEND not in sys.path:
    sys.path.insert(0, _FRONTEND)

from utils.ui import (  # noqa: E402
    API,
    CATEGORIES,
    cached_get,
    empty_state,
    esc,
    glass_close,
    glass_open,
    init_page,
    invalidate_cache,
    page_header,
    section_title,
)
from utils.auth import auth_headers, ensure_role  # noqa: E402

init_page("Knowledge Base — ResolveAI", "📚", nav="kb")
ensure_role("agent")

page_header(
    "Knowledge Base",
    "Articles powering the RAG solution agent",
    badge=f"{len(CATEGORIES)} categories",
)

articles, ok = cached_get("/knowledge-base", token=st.session_state.get("access_token", ""))
if not ok or not isinstance(articles, list):
    articles = []
    if not ok:
        st.error("Could not load articles. Is the API running?")

search = st.text_input("Search articles", placeholder="Title, tags, content…")
cat_filter = st.selectbox("Filter by category", ["all"] + CATEGORIES, label_visibility="visible")

if search.strip():
    q = search.strip().lower()
    articles = [
        a
        for a in articles
        if q in (a.get("title") or "").lower()
        or q in (a.get("content") or "").lower()
        or q in (a.get("tags") or "").lower()
    ]
if cat_filter != "all":
    articles = [a for a in articles if a.get("category") == cat_filter]

col_list, col_form = st.columns([3, 2])

with col_list:
    section_title(f"Articles ({len(articles)})", "RAG retrieval source documents", icon="📚")
    if not articles:
        empty_state("📚", "No articles", "Add your first article using the form on the right.")
    else:
        for a in articles:
            st.markdown(
                f"""
                <div class="kb-card">
                    <div class="kb-card-title">#{esc(a['id'])} — {esc(a['title'])}</div>
                    <div class="kb-card-meta">
                        <span class="badge badge-medium">{esc(a.get('category', 'general'))}</span>
                        &nbsp;· Tags: {esc(a.get('tags') or 'none')}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            # Streamlit's `st.expander` arrow/icon is affected by our CSS and can show `_arr:` text.
            # Use a native HTML accordion so the UI is stable.
            content_html = esc(a["content"]).replace("\n", "<br/>")
            with st.container():
                st.markdown(
                    f"""
                    <details class="kb-details">
                      <summary>Read: {esc(a['title'][:40])}…</summary>
                      <div class="kb-details-body">{content_html}</div>
                    </details>
                    """,
                    unsafe_allow_html=True,
                )
                if st.button("Delete article", key=f"del_{a['id']}", type="secondary"):
                    requests.delete(f"{API}/knowledge-base/{a['id']}", headers=auth_headers(), timeout=8)
                    invalidate_cache()
                    st.toast("Article removed")
                    st.rerun()

with col_form:
    glass_open()
    st.markdown("#### Add new article")
    with st.form("new_article", clear_on_submit=True):
        title = st.text_input("Title *")
        category = st.selectbox("Category", CATEGORIES)
        tags = st.text_input("Tags", placeholder="refund, billing, sla")
        content = st.text_area("Content *", height=220, placeholder="Resolution steps, policies, FAQs…")
        submitted = st.form_submit_button("Publish article", type="primary", use_container_width=True)
        if submitted:
            if title.strip() and content.strip():
                res = requests.post(
                    f"{API}/knowledge-base",
                    json={
                        "title": title.strip(),
                        "content": content.strip(),
                        "category": category,
                        "tags": tags.strip(),
                    },
                    headers=auth_headers(),
                    timeout=10,
                )
                if res.status_code == 201:
                    invalidate_cache()
                    st.success("Article published!")
                    st.rerun()
                else:
                    st.error(res.text[:200])
            else:
                st.error("Title and content are required.")
    glass_close()
