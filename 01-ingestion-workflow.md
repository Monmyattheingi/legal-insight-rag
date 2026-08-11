# n8n Workflow 01 — Legal-document ingestion

Create these nodes in order:

1. **Schedule Trigger** — hourly during development.
2. **Postgres: claim one pending document**

```sql
UPDATE ingestion_queue
SET status='processing', attempts=attempts+1
WHERE id=(
  SELECT id FROM ingestion_queue
  WHERE status='pending'
  ORDER BY created_at
  LIMIT 1
  FOR UPDATE SKIP LOCKED
)
RETURNING *;
```

3. **HTTP Request**
   - URL: `{{ $json.source_url }}`
   - Response: File
   - Binary field: `data`
   - Only allow reviewed source hosts.
4. **Crypto** — compute SHA-256 for binary `data`.
5. **Postgres duplicate check** — skip if `source_url + document_hash` already exists.
6. **Extract From File** — extract PDF text from `data`; route image-only PDFs through OCR.
7. **Postgres** — insert a version in `legal_documents` and return `id`.
8. **Edit Fields** — combine extracted `text`, document ID and queue metadata.
9. **Code** — paste `section-chunker.js`; select “Run Once for All Items”.
10. **HTTP Request: Ollama embeddings** — POST each chunk to `http://host.docker.internal:11434/api/embed` with model `bge-m3`.
11. **Postgres parameterized chunk insert**

```sql
INSERT INTO legal_chunks(
 document_id,chunk_index,chapter,section,subsection,content,embedding,metadata
)
VALUES($1,$2,$3,$4,$5,$6,$7::vector,$8::jsonb)
ON CONFLICT(document_id,chunk_index) DO NOTHING;
```

12. **Postgres completion update**

```sql
UPDATE ingestion_queue
SET status='completed',processed_at=now(),last_error=NULL
WHERE id=$1;
```

Add an Error Trigger workflow that marks the current queue record `failed` and stores a sanitized error. Never concatenate extracted law text into SQL. Inspect Myanmar Unicode extraction before embedding the first document.
