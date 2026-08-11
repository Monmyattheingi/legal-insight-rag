# Myanmar Legal RAG — MVP Starter

An expandable Myanmar legal retrieval system using n8n, PostgreSQL, and pgvector. It uses a reviewed-document queue instead of attempting to crawl all of MLIS.

## Architecture

```text
Approved PDF URL
  -> n8n download
  -> PDF text extraction or OCR
  -> section-aware splitting
  -> embeddings
  -> PostgreSQL/pgvector

User question
  -> query embedding
  -> hybrid semantic + keyword retrieval
  -> grounded answer with exact sources
```

## Start

1. Copy `.env.example` to `.env` and replace all placeholder secrets.
2. Run `docker compose up -d`.
3. Open `http://localhost:5678` and create the n8n owner account.
4. In n8n, create PostgreSQL credentials:
   - Host: `postgres`
   - Port: `5432`
   - Database/user/password: values from `.env`
5. Start the local Ollama service and pull `bge-m3` for multilingual embeddings.
6. Add 5–10 verified direct legal-document URLs to `ingestion_queue`.
7. Build the workflows from `01-ingestion-workflow.md` and
   `02-question-answering-workflow.md`.

The database schema is loaded automatically the first time PostgreSQL starts.

## Add the first law

```sql
INSERT INTO ingestion_queue
  (source_url, law_name, law_number, language, category, legal_status)
VALUES
  ('DIRECT_PDF_URL', 'ကလေးသူငယ် အခွင့်အရေးများဆိုင်ရာဥပဒေ',
   '22/2019', 'my', 'child-law', 'active');
```

Only use verified direct links and confirm that automated downloading is allowed. Start manually; add discovery/scheduling only after the MVP is accurate.

## Important decisions

- The schema assumes local Ollama `bge-m3` embeddings with 1024 dimensions.
- Legal documents are versioned by SHA-256 hash and never silently overwritten.
- Similarity is a retrieval score, not a guilt score, legal-confidence score, or predicted sentence.
- Scanned PDFs must pass through OCR and Myanmar Unicode must be reviewed.
- For broken MLIS PDF fonts, use the local Tesseract service documented in
  `03-local-ocr-setup.md`.
- Answers must expose sources and return “insufficient evidence” when retrieval is weak.

## First-demo acceptance criteria

- Five verified laws indexed
- Exact law name, section, status and source URL in results
- Ten human-reviewed evaluation questions
- No unsupported legal conclusion
- Legal-information disclaimer visible
