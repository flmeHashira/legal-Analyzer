# LegalDoc Analyzer

An AI-assisted legal document analysis platform that processes PDF contracts, extracts structured document content, identifies potentially important clauses, and maps findings back to their original locations in the PDF.

Built as a multi-service application with React, Node.js, PostgreSQL, Python, and an LLM analysis layer.

> **Note:** This project provides automated document analysis and is not a substitute for professional legal advice.

## Architecture

```mermaid
flowchart LR
    U[User] --> F[React + PDF.js]

    F --> API[Node.js / Express]
    API --> DB[(PostgreSQL)]
    API --> V[(Shared Volume)]

    DB --> W[Python Worker]
    V --> W

    W --> P[pdfplumber]
    P --> R[PII Redaction]
    R --> L[Groq LLM]

    L --> J[Structured Findings]
    J --> V

    V --> API
    API --> F

    F --> H[PDF Highlights]
````

## How it works

1. **Upload** — The API stores the PDF and creates a `QUEUED` job in PostgreSQL.
2. **Process** — A Python worker claims queued jobs using PostgreSQL row locking with `FOR UPDATE SKIP LOCKED`.
3. **Parse** — `pdfplumber` extracts text, typography, tables, and PDF coordinates and converts them into structured blocks.
4. **Redact** — Microsoft Presidio and custom Indian recognizers mask selected PII before AI analysis.
5. **Analyze** — The redacted document is sent to Groq using `llama-3.3-70b-versatile`. Findings reference the original `block_id`s.
6. **Render** — The React frontend resolves those block IDs to PDF coordinates and overlays the findings on the original document.

## Key engineering ideas

### PostgreSQL-backed job queue

PostgreSQL acts as both the application database and lightweight work queue.

```sql
SELECT *
FROM jobs
WHERE status = 'QUEUED'
ORDER BY created_at ASC
LIMIT 1
FOR UPDATE SKIP LOCKED;
```

This provides concurrency-safe job claiming without introducing a separate message broker.

### Block-based document grounding

Extracted content receives stable IDs such as:

```text
b000123
```

Each block stores its page and PDF bounding box. LLM findings return the relevant `block_ids`, allowing the frontend to map:

```text
LLM finding
    ↓
block_id
    ↓
PDF bounding box
    ↓
highlight
```

### PII redaction

Sensitive values are replaced with placeholders before AI analysis, including identifiers such as PAN, Aadhaar, passport, IFSC and bank-account numbers.

### Automatic retention

Completed documents are automatically purged after a configurable retention period. The default is 24 hours.

## Features

* PDF contract upload and asynchronous processing
* Structured document extraction
* Heading, paragraph, list and table detection
* PDF coordinate tracking
* PII redaction
* LLM-based clause/risk analysis
* Finding-to-PDF highlighting
* JWT authentication
* Per-user and global upload limits
* Automatic document retention and cleanup

## Tech Stack

**Frontend**

* React
* Vite
* React Router
* Tailwind CSS
* PDF.js

**Backend**

* Node.js
* Express
* PostgreSQL
* Multer
* JWT
* bcryptjs

**Document Processing**

* Python
* pdfplumber
* Microsoft Presidio
* spaCy
* Groq
* Llama 3.3 70B

**Infrastructure**

* Docker
* Docker Compose
* PostgreSQL

## Project Structure

```text
.
├── backend/
├── parser/
├── frontend/
├── db/
└── docker-compose.yml
```

## Run locally

### Prerequisites

* Docker
* Docker Compose
* Node.js / npm

### Environment

Create a root `.env`:

```env
POSTGRES_USER=postgres
POSTGRES_PASSWORD=your_password
POSTGRES_DB=legal_analyzer

JWT_SECRET=your_jwt_secret
GROQ_API_KEY=your_groq_api_key

MAX_FILE_SIZE_MB=5
USER_DAILY_DOC_LIMIT=5
GLOBAL_DAILY_DOC_LIMIT=900
```

Create `frontend/.env`:

```env
VITE_API_URL=http://localhost:3000/api
```

### Start the backend stack

```bash
docker compose up --build
```

### Start the frontend

```bash
cd frontend
npm install
npm run dev
```

Application:

```text
Frontend  → http://localhost:5173
API       → http://localhost:3000
Adminer   → http://localhost:8080
```

## Limitations

* Job status is monitored through polling.
* PostgreSQL is used as the job queue.
* The current worker processes one claimed job at a time.
* Large documents are truncated before LLM analysis.
* PDF files and generated artifacts use local/shared filesystem storage.
* Automated analysis should not be treated as legal advice.

## License

Personal portfolio project.