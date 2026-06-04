import os

from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks, status, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from typing import Optional

from backend.database import get_db, init_db
from backend.auth import AuthUser, require_agent, require_customer
from backend.auth_routes import router as auth_router
from backend.models import Ticket, User, KnowledgeBase, AgentLog, TicketStatus
from backend.schemas import (
    CustomerTicketCreate,
    CustomerTicketRead,
    TicketCreate, TicketRead, TicketUpdate,
    UserCreate, UserRead,
    KBArticleCreate, KBArticleRead,
    AgentLogRead,
    ApproveRequest,
)
from backend.agent import gemini_configured, run_process_ticket

app = FastAPI(
    title="Support Agent API",
    version="1.0.0",
    description="Agentic LLM-powered customer support system",
)
app.include_router(auth_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def on_startup():
    init_db()


@app.get("/health")
def health():
    return {
        "status": "ok",
        "gemini_configured": gemini_configured(),
        "gemini_model": os.environ.get("GEMINI_MODEL", "gemini-2.0-flash-lite"),
    }


# ── Users ──────────────────────────────────────────────────────────────────────

@app.post("/users", response_model=UserRead, status_code=201)
def create_user(payload: UserCreate, db: Session = Depends(get_db)):
    user = User(**payload.model_dump())
    db.add(user)
    db.commit()
    db.refresh(user)
    return user

@app.get("/users/{user_id}", response_model=UserRead)
def get_user(user_id: int, db: Session = Depends(get_db)):
    user = db.query(User).get(user_id)
    if not user:
        raise HTTPException(404, "User not found")
    return user


# ── Tickets ────────────────────────────────────────────────────────────────────

@app.post("/tickets", response_model=TicketRead, status_code=201)
def create_ticket(
    payload: TicketCreate,
    background_tasks: BackgroundTasks,
    _: AuthUser = Depends(require_agent),
    db: Session = Depends(get_db),
):
    """Submit a new ticket. Triggers the agent pipeline asynchronously."""
    # Verify user exists
    user = db.query(User).get(payload.user_id)
    if not user:
        raise HTTPException(404, "User not found")

    ticket = Ticket(**payload.model_dump())
    db.add(ticket)
    db.commit()
    db.refresh(ticket)

    # Kick off agent pipeline in background
    if not gemini_configured():
        raise HTTPException(
            503,
            "GEMINI_API_KEY is not configured. Add it to .env and restart the server.",
        )
    background_tasks.add_task(run_process_ticket, ticket.id)

    return ticket

@app.get("/tickets", response_model=list[TicketRead])
def list_tickets(
    status: Optional[str] = None,
    category: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    _: AuthUser = Depends(require_agent),
    db: Session = Depends(get_db),
):
    q = db.query(Ticket)
    if status:
        q = q.filter(Ticket.status == status)
    if category:
        q = q.filter(Ticket.category == category)
    return q.order_by(Ticket.created_at.desc()).offset(offset).limit(limit).all()

@app.get("/tickets/{ticket_id}", response_model=TicketRead)
def get_ticket(
    ticket_id: int,
    _: AuthUser = Depends(require_agent),
    db: Session = Depends(get_db),
):
    ticket = db.query(Ticket).get(ticket_id)
    if not ticket:
        raise HTTPException(404, "Ticket not found")
    return ticket

@app.delete("/tickets/{ticket_id}", status_code=204)
def delete_ticket(
    ticket_id: int,
    _: AuthUser = Depends(require_agent),
    db: Session = Depends(get_db),
):
    """Delete a ticket (and its related logs via cascade)."""
    ticket = db.query(Ticket).get(ticket_id)
    if not ticket:
        raise HTTPException(404, "Ticket not found")
    db.delete(ticket)
    db.commit()
    return Response(status_code=204)

@app.patch("/tickets/{ticket_id}", response_model=TicketRead)
def update_ticket(
    ticket_id: int,
    payload: TicketUpdate,
    _: AuthUser = Depends(require_agent),
    db: Session = Depends(get_db),
):
    ticket = db.query(Ticket).get(ticket_id)
    if not ticket:
        raise HTTPException(404, "Ticket not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(ticket, field, value)
    db.commit()
    db.refresh(ticket)
    return ticket

@app.post("/tickets/{ticket_id}/approve", response_model=TicketRead)
def approve_ticket(
    ticket_id: int,
    payload: ApproveRequest,
    _: AuthUser = Depends(require_agent),
    db: Session = Depends(get_db),
):
    """
    Human approval endpoint. Accepts an optional edited response.
    If response_text is None, the existing draft is approved as-is.
    """
    ticket = db.query(Ticket).get(ticket_id)
    if not ticket:
        raise HTTPException(404, "Ticket not found")
    if ticket.status != TicketStatus.pending_review:
        raise HTTPException(400, f"Ticket is not pending review (current: {ticket.status})")

    ticket.approved_response = payload.response_text or ticket.draft_response
    ticket.is_approved = True
    ticket.status = TicketStatus.resolved
    from datetime import datetime, timezone
    ticket.resolved_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(ticket)
    return ticket

@app.post("/tickets/{ticket_id}/reprocess", status_code=202)
def reprocess_ticket(
    ticket_id: int,
    background_tasks: BackgroundTasks,
    _: AuthUser = Depends(require_agent),
    db: Session = Depends(get_db),
):
    """Re-trigger the agent pipeline for a ticket (e.g. after KB update)."""
    ticket = db.query(Ticket).get(ticket_id)
    if not ticket:
        raise HTTPException(404, "Ticket not found")
    ticket.status = TicketStatus.open
    ticket.category = None
    ticket.priority = None
    ticket.draft_response = None
    db.commit()
    if not gemini_configured():
        raise HTTPException(503, "GEMINI_API_KEY is not configured.")
    background_tasks.add_task(run_process_ticket, ticket_id)
    return {"message": "Reprocessing started"}


# ── Knowledge Base ─────────────────────────────────────────────────────────────

@app.post("/knowledge-base", response_model=KBArticleRead, status_code=201)
def create_kb_article(
    payload: KBArticleCreate,
    _: AuthUser = Depends(require_agent),
    db: Session = Depends(get_db),
):
    article = KnowledgeBase(**payload.model_dump())
    db.add(article)
    db.commit()
    db.refresh(article)
    return article

@app.get("/knowledge-base", response_model=list[KBArticleRead])
def list_kb_articles(
    category: Optional[str] = None,
    _: AuthUser = Depends(require_agent),
    db: Session = Depends(get_db)
):
    q = db.query(KnowledgeBase).filter(KnowledgeBase.is_active == True)
    if category:
        q = q.filter(KnowledgeBase.category == category)
    return q.order_by(KnowledgeBase.id.desc()).all()

@app.delete("/knowledge-base/{article_id}", status_code=204)
def delete_kb_article(
    article_id: int,
    _: AuthUser = Depends(require_agent),
    db: Session = Depends(get_db),
):
    article = db.query(KnowledgeBase).get(article_id)
    if not article:
        raise HTTPException(404, "Article not found")
    article.is_active = False
    db.commit()


# ── Agent Logs ─────────────────────────────────────────────────────────────────

@app.get("/tickets/{ticket_id}/logs", response_model=list[AgentLogRead])
def get_ticket_logs(
    ticket_id: int,
    _: AuthUser = Depends(require_agent),
    db: Session = Depends(get_db),
):
    return (
        db.query(AgentLog)
        .filter(AgentLog.ticket_id == ticket_id)
        .order_by(AgentLog.created_at.asc())
        .all()
    )

@app.get("/logs/recent", response_model=list[AgentLogRead])
def get_recent_logs(
    limit: int = 100,
    _: AuthUser = Depends(require_agent),
    db: Session = Depends(get_db),
):
    return (
        db.query(AgentLog)
        .order_by(AgentLog.created_at.desc())
        .limit(limit)
        .all()
    )


# ── Customer Portal ────────────────────────────────────────────────────────────

@app.post("/customer/tickets", response_model=CustomerTicketRead, status_code=201)
def create_customer_ticket(
    payload: CustomerTicketCreate,
    background_tasks: BackgroundTasks,
    user: AuthUser = Depends(require_customer),
    db: Session = Depends(get_db),
):
    ticket = Ticket(user_id=user.user_id, subject=payload.subject, body=payload.body)
    db.add(ticket)
    db.commit()
    db.refresh(ticket)
    if not gemini_configured():
        raise HTTPException(503, "GEMINI_API_KEY is not configured.")
    background_tasks.add_task(run_process_ticket, ticket.id)
    return ticket


@app.get("/customer/tickets", response_model=list[CustomerTicketRead])
def list_customer_tickets(
    limit: int = 100,
    offset: int = 0,
    user: AuthUser = Depends(require_customer),
    db: Session = Depends(get_db),
):
    return (
        db.query(Ticket)
        .filter(Ticket.user_id == user.user_id)
        .order_by(Ticket.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
