from pydantic import BaseModel, EmailStr, Field
from typing import Optional, Literal
from datetime import datetime


class GoogleTokenRequest(BaseModel):
    credential: str


class AgentLoginRequest(BaseModel):
    email: str = Field(min_length=3)
    password: str = Field(min_length=6)


class CustomerRegisterRequest(BaseModel):
    name: str = Field(min_length=2)
    email: EmailStr
    password: str = Field(min_length=6)


class CustomerLoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)


class UserCreate(BaseModel):
    name: str
    email: EmailStr
    company: Optional[str] = None
    plan: str = "free"

class UserRead(UserCreate):
    id: int
    created_at: datetime
    model_config = {"from_attributes": True}


class AuthTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: Literal["customer", "agent"]
    user: Optional[UserRead] = None
    agent_id: Optional[int] = None
    email: Optional[str] = None
    name: Optional[str] = None


class TicketCreate(BaseModel):
    user_id: int
    subject: str
    body: str


class CustomerTicketCreate(BaseModel):
    subject: str
    body: str


class CustomerTicketRead(BaseModel):
    id: int
    subject: str
    body: str
    status: str
    approved_response: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    model_config = {"from_attributes": True}

class TicketUpdate(BaseModel):
    subject: Optional[str] = None
    body: Optional[str] = None
    category: Optional[str] = None
    priority: Optional[str] = None

class TicketRead(BaseModel):
    id: int
    user_id: int
    subject: str
    body: str
    category: Optional[str] = None
    priority: Optional[str] = None
    classification_reasoning: Optional[str] = None
    draft_response: Optional[str] = None
    approved_response: Optional[str] = None
    kb_articles_used: Optional[str] = None
    status: str
    is_approved: bool
    created_at: datetime
    updated_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    model_config = {"from_attributes": True}


class ApproveRequest(BaseModel):
    response_text: Optional[str] = None  # None = approve draft as-is


class KBArticleCreate(BaseModel):
    title: str
    content: str
    category: str
    tags: Optional[str] = None
    relevance_score: float = 1.0

class KBArticleRead(KBArticleCreate):
    id: int
    is_active: bool
    created_at: datetime
    model_config = {"from_attributes": True}


class AgentLogRead(BaseModel):
    id: int
    ticket_id: int
    agent_name: str
    step: str
    detail: Optional[str] = None
    is_error: bool
    created_at: datetime
    model_config = {"from_attributes": True}
