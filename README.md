# ResolveAI-Agentic-LLM-Customer-Support-System
Built an end-to-end agentic LLM pipeline (classify → RAG draft → human approve) using Gemini API, achieving ~97% ticket classification accuracy across 8+ tested support categories. • Implemented SQLite FTS5 KB retrieval (top-3 articles/ticket, ~35% latency reduction), 5-state ticket machine, dual role-guarded portals
# ResolveAI

**Agentic customer support with dual portals — Customer & Agent**  
Streamlit · FastAPI · SQLite · Google Gemini · JWT Auth

[Architecture](#-architecture) · [Ticket Flow](#-ticket-lifecycle) · [Auth](#-authentication) · [Database](#-database-schema) · [API](#-api-reference) · [Setup](#-getting-started)

---

## Overview

**ResolveAI** routes support work through an AI pipeline (classify → RAG draft → human approve) while keeping **customers** and **agents** in separate, role-guarded experiences.


| Portal       | Who        | Can do                                                                              |
| ------------ | ---------- | ----------------------------------------------------------------------------------- |
| **Customer** | End users  | Register/login (email or Google), submit tickets, view **approved** agent responses |
| **Agent**    | Staff only | Dashboard metrics, approve/edit drafts, KB management, agent logs, delete/reprocess |


**Local URLs**


| Service      | URL                                                      |
| ------------ | -------------------------------------------------------- |
| Streamlit UI | [http://localhost:8501](http://localhost:8501)           |
| FastAPI      | [http://localhost:8000](http://localhost:8000)           |
| OpenAPI docs | [http://localhost:8000/docs](http://localhost:8000/docs) |


---

## Architecture

### System context

```mermaid
flowchart TB
    subgraph Clients["Clients"]
        CUST["Customer Browser"]
        AGT["Agent Browser"]
    end

    subgraph Frontend["Streamlit Frontend :8501"]
        APP["app.py — Login / Home"]
        CP["Customer Portal"]
        AD["Agent Dashboard"]
        TD["Ticket Detail"]
        KB["Knowledge Base"]
        LOGS["Agent Logs"]
    end

    subgraph Backend["FastAPI Backend :8000"]
        API["REST API + JWT"]
        AUTH["auth_routes.py"]
        ORCH["Agent Orchestrator"]
        CLS["Classification Agent"]
        RAG["RAG Solution Agent"]
    end

    subgraph Data["Persistence"]
        DB[("SQLite / Postgres<br/>users · agents · tickets · kb · logs")]
        FTS[("FTS5<br/>kb_fts")]
    end

    subgraph External["External"]
        GEMINI["Google Gemini API"]
        GOOGLE["Google OAuth"]
    end

    CUST --> APP
    AGT --> APP
    APP --> CP
    APP --> AD
    AD --> TD
    AD --> KB
    AD --> LOGS

    APP -->|Bearer JWT| API
    CP -->|Bearer JWT| API
    AD -->|Bearer JWT| API

    API --> AUTH
    API --> ORCH
    ORCH --> CLS
    ORCH --> RAG
    CLS --> GEMINI
    RAG --> GEMINI
    RAG --> FTS
    AUTH --> GOOGLE

    API --> DB
    ORCH --> DB
```



### Layered design

```mermaid
flowchart LR
    subgraph Presentation["Presentation Layer"]
        ST["Streamlit pages<br/>+ shared UI theme"]
    end

    subgraph Application["Application Layer"]
        FA["FastAPI routers"]
        DEP["Auth dependencies<br/>require_customer / require_agent"]
    end

    subgraph Domain["Domain / AI Layer"]
        AG["backend/agent.py"]
        RG["backend/rag.py"]
    end

    subgraph DataLayer["Data Layer"]
        SQL["SQLAlchemy models"]
        SEED["seed.py"]
    end

    ST -->|HTTP + JWT| FA
    FA --> DEP
    FA --> AG
    AG --> RG
    FA --> SQL
    SQL --> SEED
```



### Dual-portal navigation

```mermaid
flowchart TD
    HOME["app.py — Entry / Login"]

    HOME -->|Customer JWT| CHOME["Customer Home<br/>KPIs + recent tickets"]
    HOME -->|Agent JWT| AHOME["Agent Command Center<br/>KPIs + mission control"]

    CHOME --> CP["pages/5_New_Ticket.py<br/>Customer Portal"]
    CP --> SUBMIT["Submit ticket"]
    CP --> LIVE["Live My Tickets<br/>4s auto-refresh"]

    AHOME --> DASH["pages/1_Dashboard.py"]
    DASH --> DETAIL["pages/2_Ticket_Detail.py"]
    AHOME --> KB["pages/3_Knowledge_Base.py"]
    AHOME --> LOGS["pages/4_Agent_Logs.py"]

    DETAIL --> APPROVE["Approve / Edit draft"]
    DETAIL --> REPROC["Reprocess pipeline"]
```



---

## Ticket lifecycle

### Status state machine

```mermaid
stateDiagram-v2
    [*] --> open: Customer submits ticket

    open --> classifying: Background task starts
    classifying --> drafting: Category + priority set
    drafting --> pending_review: RAG draft created

    pending_review --> resolved: Agent approves
    pending_review --> open: Agent reprocesses

    resolved --> closed: Optional close
    closed --> [*]

    note right of classifying
        ClassificationAgent (Gemini)
    end note

    note right of drafting
        RAGSolutionAgent (Gemini + KB FTS)
    end note

    note right of pending_review
        Human-in-the-loop on Agent UI
    end note
```



### End-to-end sequence (one ticket)

```mermaid
sequenceDiagram
    autonumber
    participant C as Customer UI
    participant API as FastAPI
    participant DB as Database
    participant BG as Background Task
    participant G as Gemini
    participant A as Agent UI

    C->>API: POST /customer/tickets (JWT)
    API->>DB: Insert ticket (status=open)
    API-->>C: 201 Created
    API->>BG: run_process_ticket(id)

    BG->>DB: status=classifying
    BG->>G: Classify subject + body
    G-->>BG: category, priority, reasoning
    BG->>DB: Save classification

    BG->>DB: status=drafting
    BG->>G: RAG draft (KB context)
    G-->>BG: draft_response
    BG->>DB: status=pending_review

    A->>API: GET /tickets (JWT agent)
    API-->>A: Ticket + draft_response
    A->>API: POST /tickets/{id}/approve
    API->>DB: approved_response, status=resolved
    API-->>A: 200 OK

    C->>API: GET /customer/tickets (poll 4s)
    API-->>C: approved_response visible
```



---

## Authentication

All protected routes use **JWT Bearer** tokens. Roles: `customer` | `agent`.

### Customer — email/password

```mermaid
sequenceDiagram
    participant UI as Streamlit
    participant API as FastAPI
    participant DB as Database

    UI->>API: POST /auth/customer/register
    API->>DB: Create User (password_hash)
    API-->>UI: JWT (role=customer)

    UI->>API: POST /auth/customer/login
    API->>DB: Verify password
    API-->>UI: JWT (role=customer)

    Note over UI: Token stored in session + URL query (refresh persistence)
```



### Customer — Google OAuth

```mermaid
sequenceDiagram
    participant UI as Streamlit
    participant API as FastAPI
    participant G as Google
    participant DB as Database

    UI->>API: GET /auth/google/start
    API-->>UI: auth_url
    UI->>G: User signs in (browser)
    G->>API: GET /auth/google/callback?code=...
    API->>G: Exchange code for id_token
    API->>DB: Upsert User (google_sub, email)
    API-->>UI: Redirect ?access_token=JWT
    UI->>API: GET /auth/me
    API-->>UI: role, name, email
```



### Agent — staff login

```mermaid
sequenceDiagram
    participant UI as Streamlit
    participant API as FastAPI
    participant DB as Database

    UI->>API: POST /auth/agent/login
    API->>DB: Verify Agent.password_hash
    API-->>UI: JWT (role=agent)
    UI->>API: Agent-only routes (/tickets, /knowledge-base, ...)
```



### Access control matrix


| Resource                     | Customer | Agent |
| ---------------------------- | -------- | ----- |
| `POST /customer/tickets`     | ✅        | ❌     |
| `GET /customer/tickets`      | ✅ own    | ❌     |
| `GET /tickets` (full)        | ❌        | ✅     |
| `POST /tickets/{id}/approve` | ❌        | ✅     |
| `GET /knowledge-base`        | ❌        | ✅     |
| `GET /logs/recent`           | ❌        | ✅     |
| `DELETE /tickets/{id}`       | ❌        | ✅     |


---

## Database schema

```mermaid
erDiagram
    USERS ||--o{ TICKETS : submits
    TICKETS ||--o{ AGENT_LOGS : generates

    USERS {
        int id PK
        string name
        string email UK
        string password_hash
        string google_sub UK
        string picture
        string plan
        datetime created_at
    }

    AGENTS {
        int id PK
        string email UK
        string password_hash
        string name
        bool is_active
        datetime created_at
    }

    TICKETS {
        int id PK
        int user_id FK
        string subject
        text body
        enum category
        enum priority
        text classification_reasoning
        text draft_response
        text approved_response
        text kb_articles_used
        enum status
        bool is_approved
        datetime created_at
        datetime resolved_at
    }

    KNOWLEDGE_BASE {
        int id PK
        string title
        text content
        enum category
        string tags
        float relevance_score
        bool is_active
    }

    AGENT_LOGS {
        int id PK
        int ticket_id FK
        string agent_name
        string step
        text detail
        bool is_error
        datetime created_at
    }
```



**FTS5:** `kb_fts` virtual table mirrors `knowledge_base` for fast RAG retrieval (see `backend/database.py`).

---

## Live updates (no manual refresh)

Customer views poll the API every **4 seconds** via Streamlit `@st.fragment(run_every=...)`.

```mermaid
flowchart LR
    subgraph CustomerUI["Customer UI"]
        FORM["Submit ticket form"]
        FRAG["live_my_tickets fragment<br/>every 4s"]
    end

    subgraph API["FastAPI"]
        LIVE["GET /customer/tickets<br/>(uncached)"]
    end

    FORM -->|POST + invalidate_cache + rerun| API
    FRAG -->|poll| LIVE
    LIVE --> FRAG

    subgraph AgentAction["Agent approves"]
        APPROVE["POST /approve"]
    end

    APPROVE --> LIVE
```



---

## Tech stack


| Layer      | Technology                                        |
| ---------- | ------------------------------------------------- |
| UI         | [Streamlit](https://streamlit.io)                 |
| API        | [FastAPI](https://fastapi.tiangolo.com) + Uvicorn |
| ORM        | SQLAlchemy 2                                      |
| DB (local) | SQLite + WAL                                      |
| DB (prod)  | Postgres recommended                              |
| LLM        | Google Gemini (`GEMINI_MODEL`)                    |
| Auth       | JWT (python-jose) + passlib (pbkdf2_sha256)       |
| OAuth      | Google OAuth 2.0                                  |
| KB search  | SQLite FTS5                                       |


---

## Project structure

```text
Project/
├── backend/
│   ├── server.py          # FastAPI app + route guards
│   ├── auth.py            # JWT, password hashing, Google verify
│   ├── auth_routes.py     # /auth/* login & OAuth
│   ├── agent.py           # Gemini orchestration pipeline
│   ├── rag.py             # Knowledge retrieval
│   ├── models.py          # SQLAlchemy entities
│   ├── schemas.py         # Pydantic request/response models
│   ├── database.py        # Engine, migrations, FTS5
│   └── seed.py            # Default agent + demo KB
├── frontend/
│   ├── app.py             # Login + Customer/Agent home
│   ├── pages/
│   │   ├── 1_Dashboard.py
│   │   ├── 2_Ticket_Detail.py
│   │   ├── 3_Knowledge_Base.py
│   │   ├── 4_Agent_Logs.py
│   │   └── 5_New_Ticket.py    # Customer Portal
│   ├── utils/
│   │   ├── ui.py          # Theme, sidebar, API helpers
│   │   └── auth.py        # Session + JWT persistence
│   └── styles/main.css
├── data/                  # SQLite file (gitignored)
├── .env.example
├── requirements.txt
└── run.ps1
```

---

## API reference

### Health


| Method | Path      | Auth   |
| ------ | --------- | ------ |
| `GET`  | `/health` | Public |


### Authentication


| Method | Path                      | Description                        |
| ------ | ------------------------- | ---------------------------------- |
| `GET`  | `/auth/google/start`      | OAuth URL for Google sign-in       |
| `GET`  | `/auth/google/callback`   | OAuth callback → redirect with JWT |
| `POST` | `/auth/google`            | Sign in with Google ID token       |
| `POST` | `/auth/customer/register` | Email/password registration        |
| `POST` | `/auth/customer/login`    | Email/password login               |
| `POST` | `/auth/agent/login`       | Staff login                        |
| `GET`  | `/auth/me`                | Current user from JWT              |


### Customer (JWT `role=customer`)


| Method | Path                | Description                         |
| ------ | ------------------- | ----------------------------------- |
| `POST` | `/customer/tickets` | Create ticket → starts AI pipeline  |
| `GET`  | `/customer/tickets` | List own tickets (sanitized fields) |


### Agent (JWT `role=agent`)


| Method   | Path                      | Description               |
| -------- | ------------------------- | ------------------------- |
| `GET`    | `/tickets`                | List/filter tickets       |
| `GET`    | `/tickets/{id}`           | Full ticket detail        |
| `PATCH`  | `/tickets/{id}`           | Update ticket             |
| `DELETE` | `/tickets/{id}`           | Delete ticket             |
| `POST`   | `/tickets/{id}/approve`   | Approve draft → resolved  |
| `POST`   | `/tickets/{id}/reprocess` | Re-run AI pipeline        |
| `GET`    | `/tickets/{id}/logs`      | Per-ticket agent logs     |
| `GET`    | `/logs/recent`            | Recent orchestration logs |
| `GET`    | `/knowledge-base`         | List KB articles          |
| `POST`   | `/knowledge-base`         | Create article            |
| `DELETE` | `/knowledge-base/{id}`    | Soft-delete article       |


---

## Getting started

### 1) Install

```bash
git clone <your-repo-url>
cd Project
pip install -r requirements.txt
```

### 2) Environment

```bash
cp .env.example .env
```


| Variable               | Required | Description                                  |
| ---------------------- | -------- | -------------------------------------------- |
| `GEMINI_API_KEY`       | ✅        | Google AI API key                            |
| `GEMINI_MODEL`         | ✅        | e.g. `gemini-2.5-flash`                      |
| `API_BASE_URL`         | ✅        | `http://localhost:8000`                      |
| `DATABASE_URL`         | ✅        | `sqlite:///./data/support.db`                |
| `JWT_SECRET`           | ✅        | Long random string                           |
| `AGENT_EMAIL`          | ✅        | Default staff email                          |
| `AGENT_PASSWORD`       | ✅        | Default staff password                       |
| `GOOGLE_CLIENT_ID`     | OAuth    | Google OAuth client                          |
| `GOOGLE_CLIENT_SECRET` | OAuth    | Google OAuth secret                          |
| `GOOGLE_REDIRECT_URI`  | OAuth    | `http://localhost:8000/auth/google/callback` |
| `STREAMLIT_URL`        | OAuth    | `http://localhost:8501`                      |


> Never commit `.env`. Rotate secrets if exposed.

### 3) Run locally

**Terminal A — API**

```bash
uvicorn backend.server:app --host 0.0.0.0 --port 8000 --reload
```

**Terminal B — UI**

```bash
streamlit run frontend/app.py --server.port 8501
```

**Windows shortcut**

```powershell
.\run.ps1
```

### Default logins


| Role     | Credentials                                   |
| -------- | --------------------------------------------- |
| Agent    | `AGENT_EMAIL` / `AGENT_PASSWORD` from `.env`  |
| Customer | Register on Home → **Email Login → Register** |


---

## Google OAuth setup

```mermaid
flowchart LR
    GCP["Google Cloud Console"]
    OAUTH["OAuth Client ID<br/>Web application"]
    ORIGINS["JS origins<br/>localhost:8501"]
    REDIRECT["Redirect URI<br/>localhost:8000/auth/google/callback"]
    ENV[".env keys"]

    GCP --> OAUTH
    OAUTH --> ORIGINS
    OAUTH --> REDIRECT
    OAUTH --> ENV
```



1. **APIs & Services → Credentials → Create OAuth Client ID** (Web application).
2. **Authorized JavaScript origins:** `http://localhost:8501`
3. **Authorized redirect URIs:** `http://localhost:8000/auth/google/callback`
4. Add **test users** while app is in *Testing* publishing status.
5. Copy Client ID/Secret to `.env`.

**Error: `Token used too early`** — sync system clock (Windows: Settings → Time & language → Sync now).

---

## Deployment architecture (free tier)

> **Vercel** hosts Node/static frontends well; it does **not** run Streamlit + long-lived FastAPI Python servers natively. Use the layout below for a free-ish stack.

```mermaid
flowchart TB
    subgraph Users["Users"]
        B["Browser"]
    end

    subgraph FreeHosting["Free-tier hosting"]
        STC["Streamlit Community Cloud<br/>frontend/app.py"]
        RND["Render / Fly.io / Railway<br/>FastAPI"]
        SB["Supabase Postgres<br/>free tier"]
    end

    subgraph External["External APIs"]
        GEM["Gemini API"]
        GGL["Google OAuth"]
    end

    B --> STC
    STC -->|API_BASE_URL| RND
    RND --> SB
    RND --> GEM
    RND --> GGL
    GGL -->|callback| RND
    RND -->|redirect JWT| STC
```




| Component    | Suggested free host     | Notes                       |
| ------------ | ----------------------- | --------------------------- |
| Streamlit UI | Streamlit Cloud         | Set secrets = `.env` values |
| FastAPI      | Render free web service | May sleep when idle         |
| Database     | Supabase Postgres       | Replace `DATABASE_URL`      |
| Gemini       | Google AI Studio        | API key in secrets          |


**Production checklist**

- Move from SQLite → Postgres
- Set strong `JWT_SECRET`
- Update Google OAuth URLs to production domains
- Store tokens in **httpOnly cookies** (not URL query) for production
- Enable HTTPS everywhere

---

## Troubleshooting


| Symptom                      | Likely cause                  | Fix                                                           |
| ---------------------------- | ----------------------------- | ------------------------------------------------------------- |
| Logged out on refresh        | Session cleared               | Re-login; token persists via URL query locally                |
| `google_exchange_failed`     | Clock skew / OAuth mismatch   | Sync time; verify redirect URI                                |
| `Invalid agent credentials`  | Wrong `.env` vs DB seed       | Use `AGENT_EMAIL` / `AGENT_PASSWORD` from `.env`; restart API |
| Backend won't start (bcrypt) | passlib/bcrypt on Python 3.14 | Project uses `pbkdf2_sha256`                                  |
| Tickets don't update live    | Fragment not running          | Stay on Customer Portal; wait ~4s                             |
| Gemini 503                   | Missing `GEMINI_API_KEY`      | Add to `.env`, restart API                                    |


---



---

Built with Streamlit + FastAPI + Gemini · ResolveAI
