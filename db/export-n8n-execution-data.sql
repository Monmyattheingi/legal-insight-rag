COPY (
  SELECT data
  FROM execution_data
  WHERE "executionId" = 51
) TO '/tmp/legal-rag-execution-51.csv' WITH (FORMAT csv, ENCODING 'UTF8');

COPY (
  SELECT data
  FROM execution_data
  WHERE "executionId" = 52
) TO '/tmp/legal-rag-execution-52.csv' WITH (FORMAT csv, ENCODING 'UTF8');
