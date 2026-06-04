"""Bootstrap demo user, default agent, and knowledge-base articles."""

import os

from backend.auth import hash_password, verify_password
from backend.database import SessionLocal
from backend.models import Agent, KnowledgeBase, User


def seed_if_empty() -> None:
    db = SessionLocal()
    try:
        _ensure_default_agent(db)
        if db.query(User).count() > 0:
            return

        demo = User(
            name="Alex Morgan",
            email="alex.morgan@example.com",
            company="Acme Corp",
            plan="pro",
        )
        db.add(demo)
        db.flush()

        articles = [
            KnowledgeBase(
                title="Refund policy — 30-day guarantee",
                category="refund",
                tags="refund,billing,policy",
                content=(
                    "Customers on Pro or Enterprise plans may request a full refund within 30 days "
                    "of purchase. Process refunds within 3–5 business days. Ask for order ID and "
                    "account email before approving."
                ),
            ),
            KnowledgeBase(
                title="Password reset and account lockout",
                category="account",
                tags="password,login,security",
                content=(
                    "Direct users to Settings → Security → Reset password. If locked out after 5 "
                    "failed attempts, unlock automatically after 15 minutes or send a one-time "
                    "unlock link from the admin console."
                ),
            ),
            KnowledgeBase(
                title="API rate limits and 429 errors",
                category="technical",
                tags="api,rate limit,429",
                content=(
                    "Free tier: 100 requests/minute. Pro: 1,000/minute. On 429, advise exponential "
                    "backoff and checking the X-RateLimit-Reset header. Upgrade path: Billing → Plans."
                ),
            ),
            KnowledgeBase(
                title="Invoice download and billing portal",
                category="billing",
                tags="invoice,billing,receipt",
                content=(
                    "Invoices are under Billing → History → Download PDF. Enterprise customers "
                    "can request consolidated monthly statements via support with account ID."
                ),
            ),
        ]
        db.add_all(articles)
        db.commit()
    finally:
        db.close()


def _ensure_default_agent(db) -> None:
    email = os.getenv("AGENT_EMAIL", "agent@resolveai.com").strip().lower()
    password = os.getenv("AGENT_PASSWORD", "ChangeMe123!")
    name = os.getenv("AGENT_NAME", "Support Agent")
    agent = db.query(Agent).filter(Agent.email == email).first()
    if agent:
        changed = False
        if agent.name != name:
            agent.name = name
            changed = True
        if not verify_password(password, agent.password_hash):
            agent.password_hash = hash_password(password)
            changed = True
        if changed:
            db.commit()
        return
    db.add(
        Agent(
            email=email,
            password_hash=hash_password(password),
            name=name,
            is_active=True,
        )
    )
    db.commit()
