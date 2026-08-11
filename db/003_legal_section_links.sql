BEGIN;

CREATE TABLE IF NOT EXISTS legal_section_links (
  id bigserial PRIMARY KEY,
  document_id uuid NOT NULL REFERENCES legal_documents(id) ON DELETE CASCADE,
  source_chunk_id bigint NOT NULL REFERENCES legal_chunks(id) ON DELETE CASCADE,
  target_chunk_id bigint NOT NULL REFERENCES legal_chunks(id) ON DELETE CASCADE,
  source_section text,
  target_section text,
  link_type text NOT NULL,
  confidence numeric(5,4) NOT NULL DEFAULT 0.75,
  reason text NOT NULL DEFAULT '',
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (source_chunk_id, target_chunk_id, link_type),
  CHECK (link_type IN ('punishment'))
);

CREATE INDEX IF NOT EXISTS legal_section_links_source_idx
  ON legal_section_links (source_chunk_id, link_type);

CREATE INDEX IF NOT EXISTS legal_section_links_document_idx
  ON legal_section_links (document_id, link_type);

CREATE INDEX IF NOT EXISTS legal_section_links_target_idx
  ON legal_section_links (target_chunk_id, link_type);

DELETE FROM legal_section_links WHERE link_type = 'punishment';

WITH punishment_chunks AS (
  SELECT *
  FROM legal_chunks
  WHERE
    content LIKE '%ထောင်ဒဏ်%'
    OR content LIKE '%ငွေဒဏ်%'
    OR content LIKE '%ဒဏ်ငွေ%'
    OR content LIKE '%ကျခံစေရမည်%'
    OR content LIKE '%ဒဏ်နှစ်ရပ်လုံး%'
),
offense_chunks AS (
  SELECT *
  FROM legal_chunks
  WHERE section IS NOT NULL
    AND (
      content LIKE '%မပြုရ%'
      OR content LIKE '%တားမြစ်%'
      OR content LIKE '%ကျူးလွန်%'
      OR content LIKE '%ဖောက်ဖျက်%'
    )
    AND NOT (
      content LIKE '%ထောင်ဒဏ်%'
      OR content LIKE '%ငွေဒဏ်%'
      OR content LIKE '%ဒဏ်ငွေ%'
      OR content LIKE '%ကျခံစေရမည်%'
      OR content LIKE '%ဒဏ်နှစ်ရပ်လုံး%'
    )
),
same_section_links AS (
  SELECT DISTINCT ON (o.id)
    o.document_id,
    o.id AS source_chunk_id,
    p.id AS target_chunk_id,
    'ပုဒ်မ ' || o.section || COALESCE('(' || o.subsection || ')', '') AS source_section,
    'ပုဒ်မ ' || p.section || COALESCE('(' || p.subsection || ')', '') AS target_section,
    0.9200::numeric AS confidence,
    'same-section punishment keyword link' AS reason
  FROM offense_chunks o
  JOIN LATERAL (
    SELECT p.*
    FROM punishment_chunks p
    WHERE p.document_id = o.document_id
      AND p.section = o.section
      AND p.id <> o.id
    ORDER BY
      CASE WHEN p.chunk_index <= o.chunk_index THEN 0 ELSE 1 END,
      abs(p.chunk_index - o.chunk_index),
      p.chunk_index
    LIMIT 1
  ) p ON true
),
nearby_links AS (
  SELECT DISTINCT ON (o.id)
    o.document_id,
    o.id AS source_chunk_id,
    p.id AS target_chunk_id,
    'ပုဒ်မ ' || o.section || COALESCE('(' || o.subsection || ')', '') AS source_section,
    'ပုဒ်မ ' || p.section || COALESCE('(' || p.subsection || ')', '') AS target_section,
    0.7000::numeric AS confidence,
    'nearby punishment keyword link' AS reason
  FROM offense_chunks o
  JOIN LATERAL (
    SELECT p.*
    FROM punishment_chunks p
    WHERE p.document_id = o.document_id
      AND p.id <> o.id
      AND p.chunk_index BETWEEN greatest(0, o.chunk_index - 8) AND o.chunk_index + 8
    ORDER BY
      CASE WHEN p.section = o.section THEN 0 ELSE 1 END,
      abs(p.chunk_index - o.chunk_index),
      p.chunk_index
    LIMIT 1
  ) p ON true
  WHERE NOT EXISTS (
    SELECT 1 FROM same_section_links s WHERE s.source_chunk_id = o.id
  )
),
cross_reference_links AS (
  SELECT DISTINCT ON (o.id, p.id)
    o.document_id,
    o.id AS source_chunk_id,
    p.id AS target_chunk_id,
    'ပုဒ်မ ' || o.section || COALESCE('(' || o.subsection || ')', '') AS source_section,
    'ပုဒ်မ ' || p.section || COALESCE('(' || p.subsection || ')', '') AS target_section,
    0.9800::numeric AS confidence,
    'explicit cross-reference punishment link' AS reason
  FROM offense_chunks o
  JOIN punishment_chunks p
    ON p.document_id = o.document_id
   AND p.id <> o.id
   AND p.content LIKE ('%ပုဒ်မ ' || o.section || '%')
   AND (
     o.subsection IS NULL
     OR p.content LIKE ('%(' || o.subsection || ')%')
     OR p.content LIKE ('%(' || o.subsection || ') ပါ%')
     OR p.content LIKE ('%(' || o.subsection || ')ပါ%')
   )
  ORDER BY o.id, p.id, p.chunk_index
),
all_links AS (
  SELECT * FROM same_section_links
  UNION ALL
  SELECT * FROM cross_reference_links
  UNION ALL
  SELECT * FROM nearby_links
)
INSERT INTO legal_section_links (
  document_id,
  source_chunk_id,
  target_chunk_id,
  source_section,
  target_section,
  link_type,
  confidence,
  reason
)
SELECT
  document_id,
  source_chunk_id,
  target_chunk_id,
  source_section,
  target_section,
  'punishment',
  confidence,
  reason
FROM all_links
ON CONFLICT (source_chunk_id, target_chunk_id, link_type) DO UPDATE
SET
  source_section = EXCLUDED.source_section,
  target_section = EXCLUDED.target_section,
  confidence = EXCLUDED.confidence,
  reason = EXCLUDED.reason;

SELECT
  d.law_name,
  count(l.*) AS punishment_links
FROM legal_documents d
LEFT JOIN legal_section_links l
  ON l.document_id = d.id
 AND l.link_type = 'punishment'
GROUP BY d.id
ORDER BY d.imported_at DESC;

COMMIT;
