SELECT
  e.id,
  e.status,
  length(d.data) AS data_chars,
  position('Code in JavaScript' IN d.data) > 0 AS has_chunker,
  position('557 items' IN d.data) > 0 AS has_557_label
FROM execution_entity e
JOIN execution_data d ON d."executionId" = e.id
WHERE e."workflowId" = 'pLqU0gZ5ILYNUlD6'
ORDER BY e.id DESC;
