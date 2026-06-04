"""
Two-agent pipeline:
  1. ClassificationAgent  → assigns Category + Priority + reasoning
  2. RAGSolutionAgent     → retrieves KB articles + drafts response
"""

import asyncio
import json
import os
import re

import httpx
from sqlalchemy.orm import Session

from backend.database import SessionLocal
from backend.models import (
    AgentLog,
    KnowledgeBase,
    Ticket,
    TicketCategory,
    TicketPriority,
    TicketStatus,
)
from backend.rag import search_knowledge_base

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_FALLBACK_MODELS = [
    m.strip()
    for m in os.environ.get(
        "GEMINI_FALLBACK_MODELS",
        "gemini-flash-lite-latest,gemini-2.0-flash-lite",
    ).split(",")
    if m.strip()
]


def _gemini_url(model: str) -> str:
    return (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={GEMINI_API_KEY}"
    )


def _models_to_try() -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for name in [GEMINI_MODEL, *GEMINI_FALLBACK_MODELS]:
        if name and name not in seen:
            seen.add(name)
            ordered.append(name)
    return ordered


def gemini_configured() -> bool:
    return bool(GEMINI_API_KEY)


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

def _log(db: Session, ticket_id: int, agent: str, step: str,
         detail: str = None, is_error: bool = False):
    entry = AgentLog(
        ticket_id=ticket_id,
        agent_name=agent,
        step=step,
        detail=detail,
        is_error=is_error,
    )
    db.add(entry)
    db.commit()


def _auto_kb_from_ticket(ticket: Ticket, db: Session) -> None:
    """
    Create a lightweight KB article from a classified ticket so that
    future RAG calls can treat past tickets as additional context.

    We keep relevance_score low so hand-crafted KB articles still dominate.
    """
    try:
        category = ticket.category or TicketCategory.other
        title = f"[Auto] {ticket.subject[:250]}"
        tags = ",".join(
            v
            for v in [
                category.value if isinstance(category, TicketCategory) else str(category),
                ticket.priority.value if ticket.priority else "",
                "auto_ticket",
            ]
            if v
        )
        body_lines = [
            "Source: customer ticket",
            "",
            f"Subject: {ticket.subject}",
            "",
            "Body:",
            ticket.body or "",
        ]
        if ticket.classification_reasoning:
            body_lines.extend(
                [
                    "",
                    "Classification reasoning:",
                    ticket.classification_reasoning,
                ]
            )
        content = "\n".join(body_lines)
        article = KnowledgeBase(
            title=title,
            content=content,
            category=category,
            tags=tags,
            relevance_score=0.3,
        )
        db.add(article)
        db.commit()
        _log(
            db,
            ticket.id,
            "ClassificationAgent",
            "Appended auto KB article from ticket",
            detail=title,
        )
    except Exception as e:  # best-effort, never break pipeline
        _log(
            db,
            ticket.id,
            "ClassificationAgent",
            "Failed to append auto KB article",
            detail=str(e),
            is_error=True,
        )


def _strip_json_fences(raw: str) -> str:
    raw_text = raw.strip()
    if raw_text.startswith("```"):
        raw_text = re.sub(r"^```(?:json)?\s*", "", raw_text)
        raw_text = re.sub(r"\s*```$", "", raw_text)
    return raw_text.strip()


async def _gemini(prompt: str) -> str:
    if not GEMINI_API_KEY:
        raise RuntimeError(
            "GEMINI_API_KEY is not set. Add it to the project .env file and restart the API."
        )
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 2048},
    }
    last_error = ""
    async with httpx.AsyncClient(timeout=60) as client:
        for model in _models_to_try():
            r = await client.post(_gemini_url(model), json=payload)
            if r.status_code == 200:
                data = r.json()
                return data["candidates"][0]["content"]["parts"][0]["text"]
            last_error = f"{model}: HTTP {r.status_code} — {r.text[:300]}"
            # Retry/fallback for transient and also "model not found" cases.
            # 404 commonly means the requested model name isn't available for this API key.
            if r.status_code not in (404, 429, 503, 500, 502, 504):
                break
    raise RuntimeError(f"Gemini API failed — {last_error}")


# ─────────────────────────────────────────────────────────────
# Agent 1 — Classification
# ─────────────────────────────────────────────────────────────

async def run_classification_agent(ticket: Ticket, db: Session):
    agent = "ClassificationAgent"
    _log(db, ticket.id, agent, "Starting classification")

    _log(db, ticket.id, agent, "Building classification prompt")
    prompt = f"""
You are a customer support ticket classifier. Analyze the ticket below and return
a JSON object with exactly these keys:
  - category: one of [billing, technical, account, general, refund, feature_request, other]
  - priority:  one of [low, medium, high, critical]
  - reasoning: a 2-3 sentence explanation of your decision

TICKET SUBJECT: {ticket.subject}
TICKET BODY:
{ticket.body}

Respond ONLY with valid JSON. No markdown fences, no preamble.
"""

    _log(db, ticket.id, agent, "Calling Gemini for classification")
    try:
        raw = await _gemini(prompt)
        _log(db, ticket.id, agent, "Received Gemini response", detail=raw[:2000])
    except Exception as e:
        _log(db, ticket.id, agent, "Gemini call failed", detail=str(e), is_error=True)
        raise

    _log(db, ticket.id, agent, "Parsing classification result")
    try:
        result = json.loads(_strip_json_fences(raw))
        category = TicketCategory(result["category"])
        priority = TicketPriority(result["priority"])
        reasoning = result["reasoning"]
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        _log(db, ticket.id, agent, "Parse error", detail=str(e), is_error=True)
        raise ValueError(f"Classification parse error: {e}") from e

    ticket.category = category
    ticket.priority = priority
    ticket.classification_reasoning = reasoning
    ticket.status = TicketStatus.drafting
    db.commit()

    # Feed this ticket back into the knowledge base for future RAG calls.
    _auto_kb_from_ticket(ticket, db)

    _log(
        db, ticket.id, agent, "Classification complete",
        detail=f"Category={category.value}, Priority={priority.value}",
    )


# ─────────────────────────────────────────────────────────────
# Agent 2 — RAG Solution
# ─────────────────────────────────────────────────────────────

async def run_rag_agent(ticket: Ticket, db: Session):
    agent = "RAGSolutionAgent"
    _log(db, ticket.id, agent, "Starting RAG pipeline")

    _log(db, ticket.id, agent, "Extracting keywords from ticket")
    keyword_prompt = f"""
Extract 5 concise search keywords from this support ticket.
Return ONLY a JSON array of strings, e.g. ["keyword1", "keyword2"].

SUBJECT: {ticket.subject}
BODY: {ticket.body}

Respond ONLY with valid JSON array of strings. No markdown fences, no preamble.
"""
    try:
        kw_raw = await _gemini(keyword_prompt)
        keywords = json.loads(_strip_json_fences(kw_raw))
        if not isinstance(keywords, list):
            raise ValueError("Expected list")
        _log(db, ticket.id, agent, "Keywords extracted", detail=str(keywords))
    except Exception as e:
        keywords = ticket.subject.split()[:5]
        _log(db, ticket.id, agent, "Keyword extraction fallback", detail=str(e))

    _log(db, ticket.id, agent, "Searching knowledge base")
    query = " ".join(str(k) for k in keywords)
    articles = search_knowledge_base(db, query, category=ticket.category, top_k=4)
    if not articles:
        _log(db, ticket.id, agent, "No KB articles found — using general context")
    else:
        _log(
            db, ticket.id, agent,
            f"Found {len(articles)} KB articles",
            detail="\n".join(f"[{a.id}] {a.title}" for a in articles),
        )

    _log(db, ticket.id, agent, "Building RAG resolution prompt")
    kb_context = "\n\n".join(
        f"--- Article {a.id}: {a.title} ---\n{a.content}" for a in articles
    ) if articles else "No specific articles found. Use general best practices."

    user_name = ticket.user.name if ticket.user else "Customer"
    user_email = ticket.user.email if ticket.user else ""
    user_plan = ticket.user.plan if ticket.user else "free"
    first_name = user_name.split()[0] if user_name else "there"

    resolution_prompt = f"""
You are a senior customer support specialist. Using the knowledge base articles below,
draft a personalized, accurate, and empathetic resolution email for this ticket.

Customer: {user_name} ({user_email}), Plan: {user_plan}
Ticket Category: {ticket.category.value if ticket.category else "unknown"}
Ticket Priority: {ticket.priority.value if ticket.priority else "unknown"}

TICKET SUBJECT: {ticket.subject}
TICKET BODY:
{ticket.body}

KNOWLEDGE BASE CONTEXT:
{kb_context}

Instructions:
- Address the customer as {first_name}.
- Reference the specific issue they raised.
- Provide clear, step-by-step resolution if applicable.
- Keep the tone professional yet warm.
- End with an offer to follow up.
- Do NOT include a subject line — just the email body.
"""

    _log(db, ticket.id, agent, "Calling Gemini for resolution draft")
    try:
        draft = await _gemini(resolution_prompt)
        _log(db, ticket.id, agent, "Draft generated", detail=draft[:500] + "...")
    except Exception as e:
        _log(db, ticket.id, agent, "Draft generation failed", detail=str(e), is_error=True)
        raise

    ticket.draft_response = draft
    ticket.kb_articles_used = json.dumps([a.id for a in articles])
    ticket.status = TicketStatus.pending_review
    db.commit()

    _log(db, ticket.id, agent, "RAG pipeline complete — ticket ready for human review")


# ─────────────────────────────────────────────────────────────
# Orchestrator
# ─────────────────────────────────────────────────────────────

async def process_ticket(ticket_id: int, db: Session):
    """Full agent pipeline. Uses the provided DB session."""
    ticket = db.query(Ticket).get(ticket_id)
    if not ticket:
        return

    ticket.status = TicketStatus.classifying
    db.commit()

    try:
        await run_classification_agent(ticket, db)
        db.refresh(ticket)
        await run_rag_agent(ticket, db)
    except Exception as e:
        _log(
            db, ticket_id, "Orchestrator",
            "Pipeline failed", detail=str(e), is_error=True,
        )
        ticket.status = TicketStatus.open
        db.commit()
        raise


def run_process_ticket(ticket_id: int) -> None:
    """Sync entry point for FastAPI BackgroundTasks (owns DB session)."""
    db = SessionLocal()
    try:
        asyncio.run(process_ticket(ticket_id, db))
    finally:
        db.close()
