# LegalDoc Analyzer

An AI-assisted legal document analysis platform that processes PDF contracts, extracts structured document content and spatial coordinates, identifies potentially important clauses, and maps analysis findings back to their original locations in the PDF.

The application combines a React frontend, Node.js API, PostgreSQL-backed job queue, Python document-processing worker, PII redaction, and LLM-based analysis.

> **Note:** LegalDoc Analyzer is an automated document-analysis tool and is not a substitute for professional legal advice.

---

## Architecture

```mermaid
flowchart LR
    U[User] --> F[React Frontend]

    F -->|Auth / Upload / Status / Results| API[Node.js + Express API]

    API --> DB[(PostgreSQL)]
    API --> V[(Shared Docker Volume)]

    DB --> W[Python Worker]
    V --> W

    W --> P[pdfplumber Parser]
    P --> R[PII Redaction]
    R --> S[Structured Document]
    S --> L[Groq LLM]

    L --> J[Structured Findings]

    J --> V
    V --> API
    API --> F

    F --> PDF[PDF.js Viewer]
    F --> FC[Finding Cards]

    FC -->|block_id| PDF
````

The backend and parser coordinate through PostgreSQL and a shared Docker volume. Uploaded PDFs and generated artifacts remain on the shared filesystem while PostgreSQL stores job metadata and processing state. 

---

## How it works

The system processes a document asynchronously from upload to analysis and visualization.

### 1. Upload

The user uploads a PDF from the web application.

The Node.js API:

* accepts the PDF through Multer
* stores it under `/app/uploads`
* creates a job record in PostgreSQL
* assigns the job an initial `QUEUED` state
* immediately returns the job ID with HTTP `202 Accepted`

Uploads are subject to configurable file-size and daily usage limits.  

### 2. Queue and asynchronous processing

A Python worker continuously polls PostgreSQL for queued jobs.

Jobs are claimed using:

```sql
SELECT *
FROM jobs
WHERE status = 'QUEUED'
ORDER BY created_at ASC
LIMIT 1
FOR UPDATE SKIP LOCKED;
```

Once claimed, the job transitions to `PROCESSING`. This allows workers to safely compete for queued jobs without selecting the same row simultaneously. 

### 3. PDF parsing

The parser uses `pdfplumber` to extract words together with:

* page number
* x/y coordinates
* font size
* font information

Extracted words are reconstructed into lines and then merged into higher-level document blocks.

The parser also contains dedicated table detection and filtering logic, including validation of table structure and quality before a table is represented as a document block.  

### 4. Document structure

Each extracted block receives a stable identifier such as:

```text
b000123
```

Blocks contain information such as:

```json
{
  "block_id": "b000123",
  "block_type": "PARAGRAPH",
  "text": "...",
  "level": 2,
  "numbering": "1.2",
  "section_path": ["1.2"],
  "positions": {
    "page": 4,
    "bbox_pdf": [72, 540, 420, 32],
    "reading_order": 18
  }
}
```

The parser recognizes:

```text
META
HEADING
PARAGRAPH
LIST_ITEM
TABLE
FOOTNOTE
```

Each block also stores a PDF-space bounding box and reading-order information, allowing the frontend to map findings back to the original document.  

### 5. PII redaction

Before sending document content to the LLM, extracted blocks pass through a redaction layer based on Microsoft Presidio.

The project includes built-in detection for categories such as:

* phone numbers
* email addresses
* IP addresses
* SSNs
* IBANs
* PAN
* Aadhaar
* IFSC
* bank-account numbers
* passports
* driving licences
* age
* sex

Custom recognizers are included for several Indian identifiers. Detected values are replaced with consistent placeholders such as:

```text
[PERSON_1]
[PAN_1]
[AADHAAR_1]
```

A redaction registry stores the original value and detection metadata separately.   

### 6. LLM analysis

The structured document is serialized with block identifiers:

```text
[[ b000123 | PARAGRAPH ]]
The employee shall not disclose confidential information.
```

The analysis request explicitly requires the model to reference existing block IDs rather than returning arbitrary text offsets.

For each finding, the model returns:

* `finding_id`
* `risk`
* `summary`
* `explanation`
* `triggers`
* `block_ids`

The current implementation uses the Groq API with:

```text
Model: llama-3.3-70b-versatile
Temperature: 0.1
Response format: JSON object
```

The parser also limits very large documents before the LLM request to stay within the configured context budget. 

### 7. Result generation

After parsing and analysis, the worker writes:

```text
document.txt
document.json
redaction_map.json
```

The final `document.json` contains the page count, structured blocks, and LLM findings.

Successful jobs are marked `COMPLETED`; processing failures are marked `FAILED`.  

### 8. PDF visualization

The React frontend loads the original PDF through PDF.js.

The document viewer:

1. builds an index of document blocks by `block_id`
2. converts each finding's `block_ids` into page-specific highlights
3. converts PDF-space bounding boxes into viewport coordinates
4. renders the highlight overlays on top of the PDF canvas
5. allows the user to select a finding and jump to the corresponding page

The viewer renders each page individually and maintains the current page based on scroll position. 

---

## Document-to-highlight mapping

One of the core design ideas in the project is keeping the LLM output grounded in the original document.

The mapping is:

```text
PDF
 │
 ▼
Extracted blocks
 │
 │ block_id + bbox_pdf
 ▼
LLM finding
 │
 │ block_ids
 ▼
Frontend block index
 │
 │ page + bounding box
 ▼
PDF-space → viewport-space conversion
 │
 ▼
Highlight overlay
```

This avoids relying on fragile character offsets when locating findings in the rendered PDF.

---

## Frontend

The frontend uses React with protected routes for the document workspace.

The application provides:

* account registration and login
* authenticated document workspace
* PDF upload
* job monitoring
* job search
* document status tracking
* PDF viewing
* zoom controls
* finding cards
* page navigation
* finding-to-PDF highlighting
* PII masking/reveal control
* document deletion

Active jobs are refreshed every 3 seconds while their status is `QUEUED` or `PROCESSING`.

Authentication state is managed with a React context and authenticated requests use cookies. 

---

## Authentication

The backend provides:

```text
POST /api/auth/register
POST /api/auth/login
POST /api/auth/logout
GET  /api/auth/me
```

Passwords are hashed with `bcryptjs`.

After login, the server creates a JWT with a four-hour lifetime and stores it in an HttpOnly cookie. Protected API routes verify that cookie before handling document requests. 

The frontend uses a protected routing layer so the main workspace and document viewer are only accessible to authenticated users.

---

## API

### Authentication

| Method | Endpoint             | Description                  |
| ------ | -------------------- | ---------------------------- |
| `POST` | `/api/auth/register` | Create an account            |
| `POST` | `/api/auth/login`    | Authenticate the user        |
| `POST` | `/api/auth/logout`   | Clear the session cookie     |
| `GET`  | `/api/auth/me`       | Validate the current session |

### Document jobs

| Method   | Endpoint                      | Description                          |
| -------- | ----------------------------- | ------------------------------------ |
| `POST`   | `/api/upload`                 | Upload and queue a PDF               |
| `GET`    | `/api/jobs`                   | List the authenticated user's jobs   |
| `GET`    | `/api/jobs/:id/status`        | Get job status                       |
| `GET`    | `/api/jobs/:id/result`        | Retrieve the processed document JSON |
| `GET`    | `/api/jobs/:id/redaction-map` | Retrieve the redaction map           |
| `GET`    | `/api/jobs/:id/pdf`           | Serve the original PDF               |
| `DELETE` | `/api/jobs/:id`               | Delete a job and its files           |

Document endpoints validate job ownership against the authenticated user before returning files or results.   

---

## Job lifecycle

```text
QUEUED
   │
   ▼
PROCESSING
   │
   ├──────────────► FAILED
   │
   ▼
COMPLETED
   │
   ▼
PURGED
```

`PURGED` is used by the retention process after completed jobs exceed the configured retention period.

---

## Data retention

The Python worker also runs a background cleanup process.

By default:

```text
Retention period: 24 hours
Cleanup interval: 5 minutes
```

Expired completed jobs have:

1. the original PDF deleted
2. the output directory deleted
3. the database status changed to `PURGED`

The system therefore keeps document artifacts only for the configured retention window unless the user deletes a job earlier. 

---

## Upload limits

The backend supports configurable usage limits.

Default values are:

```text
Maximum PDF size:        5 MB
Per-user limit:          5 documents / 24 hours
Global limit:            900 documents / 24 hours
```

These limits are checked before a new job is inserted into the queue.  

---

## Technology stack

### Frontend

* React
* Vite
* React Router
* Tailwind CSS
* Radix UI
* Lucide React
* PDF.js (`pdfjs-dist`)

### Backend

* Node.js
* Express
* PostgreSQL
* Multer
* `pg`
* JWT
* bcryptjs
* cookie-parser

### Document processing

* Python
* pdfplumber
* Microsoft Presidio
* spaCy
* custom Indian PII recognizers
* Groq API
* `llama-3.3-70b-versatile`

### Infrastructure

* Docker
* Docker Compose
* PostgreSQL 15
* shared Docker volume
* Adminer

---

## Project structure

```text
.
├── backend/
│   ├── index.js
│   ├── routes.js
│   ├── auth.js
│   ├── authRoutes.js
│   ├── db.js
│   ├── Dockerfile
│   └── package.json
│
├── parser/
│   ├── worker.py
│   ├── parse_document.py
│   ├── redactor.py
│   ├── registry.py
│   ├── indian_recognizers.py
│   ├── MLClassifier.py
│   ├── requirements.txt
│   └── Dockerfile
│
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   ├── hooks/
│   │   ├── lib/
│   │   ├── App.jsx
│   │   ├── AuthContext.jsx
│   │   └── main.jsx
│   ├── public/
│   └── package.json
│
├── db/
│   ├── 01_schema.sql
│   └── 02_seed.sh
│
└── docker-compose.yml
```

---

## Database

PostgreSQL stores application-level metadata rather than the document contents themselves.

### `users`

Stores:

* user ID
* email
* password hash
* creation timestamp

### `jobs`

Stores:

* job ID
* user ID
* original filename
* stored input filename
* output directory
* processing status
* page count
* creation timestamp
* completion timestamp

Indexes are defined for job status and user ownership.

---

## Running locally

### Prerequisites

* Docker
* Docker Compose
* Node.js/npm

### 1. Configure environment variables

Create a `.env` file with values for PostgreSQL, authentication, LLM access, and upload limits.

Example:

```env
POSTGRES_USER=postgres
POSTGRES_PASSWORD=your_password
POSTGRES_DB=legal_analyzer

JWT_SECRET=your_jwt_secret
GROQ_API_KEY=your_groq_api_key

NODE_ENV=development

MAX_FILE_SIZE_MB=5
USER_DAILY_DOC_LIMIT=5
GLOBAL_DAILY_DOC_LIMIT=900
```

For the frontend:

```env
VITE_API_URL=http://localhost:3000/api
```

Do not commit secrets to the repository.

### 2. Start the backend stack

From the project root:

```bash
docker compose up --build
```

This starts:

```text
Backend     → http://localhost:3000
PostgreSQL  → localhost:5432
Adminer     → http://localhost:8080
Parser      → background worker
```

The backend and parser share the `shared-data` volume mounted at:

```text
/app/uploads
```

PostgreSQL data is persisted through the `postgres-data` volume.

### 3. Start the frontend

From `frontend/`:

```bash
npm install
npm run dev
```

The Vite development server runs at:

```text
http://localhost:5173
```

---

## Design decisions

### PostgreSQL as the work queue

The project does not introduce a separate message broker for document-processing jobs.

Instead, PostgreSQL stores the job state and acts as the coordination point for workers.

`FOR UPDATE SKIP LOCKED` allows a worker to claim an available job while avoiding collisions with other workers.

This keeps the architecture relatively small while still providing concurrent job-claim semantics. 

### Shared filesystem between services

The Node.js API and Python worker communicate through a shared Docker volume.

The API writes the uploaded PDF to the volume, while the worker reads that file and writes the parser outputs back to the same location.

PostgreSQL stores the metadata required to locate those artifacts. 

### Block-based LLM grounding

Instead of asking the model to return arbitrary text offsets, the parser assigns identifiers to document blocks and requires every finding to reference those identifiers.

This creates an explicit link between:

```text
LLM output
    ↓
block_id
    ↓
PDF coordinates
    ↓
visual highlight
```

### Redaction before AI analysis

Sensitive values are replaced before the document text is sent to the model.

The redaction registry maintains the original values locally so the application can optionally reveal them in the viewer when requested. 

### Structured model output

The LLM response is requested as JSON with a fixed finding structure rather than free-form text.

That allows the frontend to consume findings directly and associate them with specific document blocks. 

---

## Additional machine-learning experiment

The repository also contains a separate `MLClassifier.py` experiment that trains a Random Forest classifier on document-line features including:

* average font size
* boldness
* uppercase text
* text length

The script produces a serialized model, label mapping, and classification report.

This experiment is separate from the current main parsing path, which performs document classification using deterministic parsing heuristics based on typography, numbering, indentation, and structure.  

---

## Limitations

* The frontend monitors processing through polling rather than a push-based status channel.
* PostgreSQL serves both as the application database and the document-processing queue.
* The current worker claims one queued job at a time per worker process.
* Large documents are truncated before LLM analysis once they exceed the configured character limit.
* The original PII values remain in the local redaction map until the job is deleted or purged.
* PDFs with no extractable text are treated as unsupported.
* There is no separate message broker or durable event log for document-processing jobs.
* LLM output is intended as analysis assistance and should not be treated as legal advice.

---

## License

Personal portfolio project.

