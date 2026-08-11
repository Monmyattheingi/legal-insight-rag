CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE TYPE ingestion_status AS ENUM ('pending','processing','completed','failed','skipped');
CREATE TYPE legal_document_status AS ENUM ('active','amended','repealed','unknown');

CREATE TABLE legal_documents (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), law_name text NOT NULL, law_number text,
 language text NOT NULL DEFAULT 'my', category text, source_url text NOT NULL,
 source_file_name text, document_hash text NOT NULL, enactment_date date, effective_date date,
 legal_status legal_document_status NOT NULL DEFAULT 'unknown',
 supersedes_document_id uuid REFERENCES legal_documents(id),
 imported_at timestamptz NOT NULL DEFAULT now(), metadata jsonb NOT NULL DEFAULT '{}',
 UNIQUE(source_url,document_hash)
);
CREATE TABLE legal_chunks (
 id bigserial PRIMARY KEY, document_id uuid NOT NULL REFERENCES legal_documents(id) ON DELETE CASCADE,
 chunk_index integer NOT NULL, chapter text, section text, subsection text, content text NOT NULL,
 content_tsv tsvector GENERATED ALWAYS AS (to_tsvector('simple',content)) STORED,
 embedding vector(1024) NOT NULL, metadata jsonb NOT NULL DEFAULT '{}',
 created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(document_id,chunk_index)
);
CREATE INDEX chunks_embedding_hnsw ON legal_chunks USING hnsw (embedding vector_cosine_ops);
CREATE INDEX chunks_content_tsv_gin ON legal_chunks USING gin (content_tsv);
CREATE INDEX chunks_section_idx ON legal_chunks(section);

CREATE TABLE ingestion_queue (
 id bigserial PRIMARY KEY, source_url text NOT NULL UNIQUE, law_name text NOT NULL,
 law_number text, language text NOT NULL DEFAULT 'my', category text, enactment_date date,
 effective_date date, legal_status legal_document_status NOT NULL DEFAULT 'unknown',
 status ingestion_status NOT NULL DEFAULT 'pending', attempts integer NOT NULL DEFAULT 0,
 last_error text, created_at timestamptz NOT NULL DEFAULT now(), processed_at timestamptz
);
CREATE TABLE retrieval_audit (
 id bigserial PRIMARY KEY, question text NOT NULL,
 retrieved_chunk_ids bigint[] NOT NULL DEFAULT '{}', answer text,
 created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE query_runs (
 id bigserial PRIMARY KEY, question text NOT NULL, normalized_question text NOT NULL,
 case_type text, selected_law text, selected_section text, punishment_section text,
 response_mode text NOT NULL, answerable boolean NOT NULL DEFAULT false,
 top_score double precision, total_ms integer NOT NULL DEFAULT 0,
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE query_trace_steps (
 id bigserial PRIMARY KEY, query_run_id bigint NOT NULL REFERENCES query_runs(id) ON DELETE CASCADE,
 step_order smallint NOT NULL, step_name text NOT NULL, status text NOT NULL,
 duration_ms integer NOT NULL DEFAULT 0, details jsonb NOT NULL DEFAULT '{}',
 created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(query_run_id,step_order),
 CHECK (status IN ('completed','failed','skipped'))
);
CREATE INDEX query_runs_created_at_idx ON query_runs(created_at DESC);
CREATE INDEX query_trace_steps_run_idx ON query_trace_steps(query_run_id,step_order);

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
