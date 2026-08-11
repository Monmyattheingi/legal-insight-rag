BEGIN;

UPDATE workflow_entity
SET
  nodes = replace(
    replace(
      nodes::text,
      $$model: 'bge-m3'$$,
      $$model: 'bge-m3-q4'$$
    ),
    'const batchSize = 16;',
    'const batchSize = 4;'
  )::json,
  "updatedAt" = CURRENT_TIMESTAMP
WHERE id = 'pLqU0gZ5ILYNUlD6'
  AND nodes::text LIKE '%bge-m3%'
RETURNING id, name;

COMMIT;
