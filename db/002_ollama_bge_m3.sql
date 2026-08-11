-- Migrate an existing OpenAI-sized embedding column to Ollama BGE-M3.
-- Run before embeddings are inserted, or rebuild any existing embeddings.
DROP INDEX IF EXISTS chunks_embedding_hnsw;
DROP FUNCTION IF EXISTS match_legal_chunks(vector, text, integer, text);

ALTER TABLE legal_chunks
  ALTER COLUMN embedding TYPE vector(1024);

CREATE INDEX chunks_embedding_hnsw
  ON legal_chunks USING hnsw (embedding vector_cosine_ops);

CREATE OR REPLACE FUNCTION match_legal_chunks(
 query_embedding vector(1024), query_text text,
 match_count integer DEFAULT 10, category_filter text DEFAULT NULL)
RETURNS TABLE(chunk_id bigint,law_name text,law_number text,section text,subsection text,
 content text,source_url text,vector_score double precision,keyword_score real,
 combined_score double precision)
LANGUAGE sql STABLE AS $$
 WITH ranked AS (
  SELECT c.id chunk_id,d.law_name,d.law_number,c.section,c.subsection,c.content,d.source_url,
   1-(c.embedding <=> query_embedding) vector_score,
   ts_rank_cd(c.content_tsv,plainto_tsquery('simple',query_text)) keyword_score
  FROM legal_chunks c JOIN legal_documents d ON d.id=c.document_id
  WHERE category_filter IS NULL OR d.category=category_filter)
 SELECT *,0.75*vector_score+0.25*LEAST(keyword_score,1.0) combined_score
 FROM ranked ORDER BY combined_score DESC LIMIT match_count;
$$;
