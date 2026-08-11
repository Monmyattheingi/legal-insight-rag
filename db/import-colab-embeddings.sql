BEGIN;

CREATE TEMP TABLE colab_legal_chunks (
  document_id uuid NOT NULL,
  chunk_index integer NOT NULL,
  chapter text,
  section text,
  subsection text,
  content text NOT NULL,
  embedding text NOT NULL,
  metadata text NOT NULL
);

COPY colab_legal_chunks (
  document_id,
  chunk_index,
  chapter,
  section,
  subsection,
  content,
  embedding,
  metadata
)
FROM '/tmp/legal_chunks_embedded.csv'
WITH (FORMAT csv, HEADER true, ENCODING 'UTF8');

DO $$
DECLARE
  imported_count integer;
BEGIN
  SELECT count(*) INTO imported_count FROM colab_legal_chunks;
  IF imported_count < 1 THEN
    RAISE EXCEPTION 'No embedded chunks were received.';
  END IF;
END;
$$;

INSERT INTO legal_chunks (
  document_id,
  chunk_index,
  chapter,
  section,
  subsection,
  content,
  embedding,
  metadata
)
SELECT
  document_id,
  chunk_index,
  NULLIF(chapter, ''),
  NULLIF(section, ''),
  NULLIF(subsection, ''),
  content,
  embedding::vector(1024),
  metadata::jsonb
FROM colab_legal_chunks
ON CONFLICT (document_id, chunk_index) DO UPDATE SET
  chapter = EXCLUDED.chapter,
  section = EXCLUDED.section,
  subsection = EXCLUDED.subsection,
  content = EXCLUDED.content,
  embedding = EXCLUDED.embedding,
  metadata = EXCLUDED.metadata;

SELECT
  document_id,
  count(*) AS stored_chunks,
  count(embedding) AS stored_embeddings
FROM legal_chunks
WHERE document_id IN (SELECT DISTINCT document_id FROM colab_legal_chunks)
GROUP BY document_id;

COMMIT;
