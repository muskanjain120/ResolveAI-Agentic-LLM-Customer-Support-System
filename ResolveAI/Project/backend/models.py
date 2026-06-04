from sqlalchemy import (
    Column, Integer, String, Text, DateTime,
    ForeignKey, Enum as SAEnum, Boolean, Float
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
from backend.database import Base


class TicketStatus(str, enum.Enum):
    open = "open"
    classifying = "classifying"
    drafting = "drafting"
    pending_review = "pending_review"
    approved = "approved"
    resolved = "resolved"
    closed = "closed"


class TicketPriority(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class TicketCategory(str, enum.Enum):
    billing = "billing"
    technical = "technical"
    account = "account"
    general = "general"
    refund = "refund"
    feature_request = "feature_request"
    other = "other"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=False)
    email = Column(String(200), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=True)
    google_sub = Column(String(255), unique=True, nullable=True, index=True)
    picture = Column(String(512), nullable=True)
    company = Column(String(200), nullable=True)
    plan = Column(String(50), default="free")        # free / pro / enterprise
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    tickets = relationship("Ticket", back_populates="user")


class Agent(Base):
    __tablename__ = "agents"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    name = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Ticket(Base):
    __tablename__ = "tickets"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    subject = Column(String(300), nullable=False)
    body = Column(Text, nullable=False)

    # LLM-assigned fields
    category = Column(SAEnum(TicketCategory), nullable=True)
    priority = Column(SAEnum(TicketPriority), nullable=True)
    classification_reasoning = Column(Text, nullable=True)

    # RAG-drafted fields
    draft_response = Column(Text, nullable=True)
    approved_response = Column(Text, nullable=True)    # After human edits/approval
    kb_articles_used = Column(Text, nullable=True)     # JSON list of KB article IDs

    # Status tracking
    status = Column(SAEnum(TicketStatus), default=TicketStatus.open, index=True)
    is_approved = Column(Boolean, default=False)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    resolved_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="tickets")
    agent_logs = relationship("AgentLog", back_populates="ticket", cascade="all, delete")


class KnowledgeBase(Base):
    __tablename__ = "knowledge_base"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(300), nullable=False)
    content = Column(Text, nullable=False)
    category = Column(SAEnum(TicketCategory), nullable=False, index=True)
    tags = Column(Text, nullable=True)                 # Comma-separated tags
    relevance_score = Column(Float, default=1.0)       # Manual boost factor
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class AgentLog(Base):
    __tablename__ = "agent_logs"

    id = Column(Integer, primary_key=True, index=True)
    ticket_id = Column(Integer, ForeignKey("tickets.id"), nullable=False)
    agent_name = Column(String(100), nullable=False)   # "ClassificationAgent" | "RAGSolutionAgent"
    step = Column(String(200), nullable=False)         # e.g. "Extracting keywords..."
    detail = Column(Text, nullable=True)               # Full thought / intermediate output
    is_error = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    ticket = relationship("Ticket", back_populates="agent_logs")
