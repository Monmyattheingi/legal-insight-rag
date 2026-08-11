BEGIN;

CREATE TABLE IF NOT EXISTS query_runs (
  id bigserial PRIMARY KEY,
  question text NOT NULL,
  normalized_question text NOT NULL,
  case_type text,
  selected_law text,
  selected_section text,
  punishment_section text,
  response_mode text NOT NULL,
  answerable boolean NOT NULL DEFAULT false,
  top_score double precision,
  total_ms integer NOT NULL DEFAULT 0,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS query_trace_steps (
  id bigserial PRIMARY KEY,
  query_run_id bigint NOT NULL REFERENCES query_runs(id) ON DELETE CASCADE,
  step_order smallint NOT NULL,
  step_name text NOT NULL,
  status text NOT NULL,
  duration_ms integer NOT NULL DEFAULT 0,
  details jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (query_run_id, step_order),
  CHECK (status IN ('completed', 'failed', 'skipped'))
);

CREATE INDEX IF NOT EXISTS query_runs_created_at_idx
  ON query_runs (created_at DESC);

CREATE INDEX IF NOT EXISTS query_trace_steps_run_idx
  ON query_trace_steps (query_run_id, step_order);

COMMIT;
