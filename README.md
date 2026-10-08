# Myanmar Legal Insight RAG

A source-grounded retrieval system for Myanmar legal information. It connects natural-language questions with reviewed legal sources, preserves section-level provenance, and returns an insufficient-evidence response when the retrieved material cannot support an answer.

> This is an academic prototype for legal-information retrieval. It does not provide legal advice or replace review by a qualified professional.

## What it demonstrates

- Section-aware ingestion with document metadata and source URLs
- Multilingual embeddings using BGE-M3 through a local Ollama service
- Hybrid semantic and keyword retrieval with PostgreSQL and pgvector
- Exact source attribution and conservative answer composition
- OCR support for scanned Myanmar and English documents
- Docker-based local development with PostgreSQL, n8n, and the OCR/API service
- Automated tests for grounding, query intent, penalty matching, and provenance

## Architecture

```text
Reviewed legal document
        |
        v
OCR / text extraction -> section-aware chunking -> BGE-M3 embeddings
                                                   |
                                                   v
                                          PostgreSQL + pgvector
                                                   ^
                                                   |
Question -> query embedding -> hybrid retrieval -> grounded response
                                                 + exact citations
                                                 + insufficient-evidence guard
```

## Technology

Python, JavaScript, n8n, PostgreSQL, pgvector, Docker Compose, Ollama, BGE-M3, FastAPI-compatible HTTP services, Tesseract OCR, and a lightweight HTML/CSS/JavaScript interface.

## Run locally

### Requirements

- Docker Desktop with Docker Compose
- Ollama running on the host
- A BGE-M3-compatible embedding model in Ollama

### Setup

```bash
cp .env.example .env
docker compose up --build -d
```

On Windows PowerShell, use:

```powershell
Copy-Item .env.example .env
docker compose up --build -d
```

Then open:

- Legal Insight interface/API: `http://localhost:8000`
- n8n workflow editor: `http://localhost:5678`
- PostgreSQL from the host: `localhost:5433`

Create the n8n owner account, then add PostgreSQL credentials with host `postgres`, port `5432`, and the database values from `.env`.

## Project structure

```text
frontend_static/          Browser interface served by the Python service
db/                       Incremental database schema files
n8n-code/                 Reusable workflow code nodes
tests/                    Grounding and retrieval-related unit tests
docker-compose.yml        Local service orchestration
Dockerfile.ocr            OCR and API service image
ocr_service.py            OCR, retrieval, and HTTP endpoints
legal_analysis.py         Query and legal-text analysis
grounded_answer.py        Evidence-constrained response composition
penalty_matching.py       Structured penalty and provenance matching
schema.sql                PostgreSQL/pgvector schema loaded by Docker
```

## Data policy

This public repository intentionally excludes:

- Real `.env` files and credentials
- Generated embedding CSV files
- Uploaded legal documents and administrative queues
- Local database volumes, execution exports, and build artifacts
- Model binaries

Use only reviewed sources that you are permitted to process. Keep document status, version, section, and source URL metadata with every indexed chunk.

## Testing

Install the Python test dependency and run:

```bash
python -m pip install pytest
python -m pytest tests
```

## Design principles

1. Retrieval similarity is not legal confidence.
2. Every material claim must remain traceable to a reviewed source.
3. Weak evidence should produce an insufficient-evidence response, not a guess.
4. OCR output and Myanmar Unicode text require human review.
5. The system presents legal information, not diagnosis, judgment, or legal advice.
