param(
  [string]$CsvPath = ".\legal_chunks_embedded.csv"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ResolvedCsv = (Resolve-Path -LiteralPath $CsvPath).Path
$ImportSql = Join-Path $ProjectRoot "db\import-colab-embeddings.sql"

$rows = Import-Csv -LiteralPath $ResolvedCsv
$rows = @($rows)
if ($rows.Count -lt 1) {
  throw "The CSV does not contain any embedded chunks."
}

$firstEmbedding = $rows[0].embedding | ConvertFrom-Json
if ($firstEmbedding.Count -ne 1024) {
  throw "Expected 1024 embedding dimensions, found $($firstEmbedding.Count)."
}

$sample = $rows | Where-Object { [int]$_.chunk_index -eq 10 } | Select-Object -First 1
if (-not $sample) {
  $sample = $rows[0]
}

$requestBody = @{
  model = "bge-m3-q4"
  input = $sample.content
  truncate = $true
  keep_alive = "30m"
} | ConvertTo-Json
$requestBodyBytes = [System.Text.Encoding]::UTF8.GetBytes($requestBody)

$localResponse = Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:11434/api/embed" `
  -ContentType "application/json" `
  -Body $requestBodyBytes `
  -TimeoutSec 300

$csvVector = $sample.embedding | ConvertFrom-Json
$localVector = $localResponse.embeddings[0]
$dot = 0.0
$csvNorm = 0.0
$localNorm = 0.0
for ($i = 0; $i -lt 1024; $i++) {
  $csvValue = [double]$csvVector[$i]
  $localValue = [double]$localVector[$i]
  $dot += $csvValue * $localValue
  $csvNorm += $csvValue * $csvValue
  $localNorm += $localValue * $localValue
}
$compatibility = $dot / ([Math]::Sqrt($csvNorm) * [Math]::Sqrt($localNorm))
if ($compatibility -lt 0.98) {
  throw "Embedding model mismatch: identical-text cosine similarity is $([Math]::Round($compatibility, 4)); expected at least 0.98."
}
Write-Host "Embedding compatibility passed:" ([Math]::Round($compatibility, 4))
Write-Host "Importing $($rows.Count) embedded chunks from Colab."

Push-Location $ProjectRoot
try {
  docker compose cp $ResolvedCsv postgres:/tmp/legal_chunks_embedded.csv
  if ($LASTEXITCODE -ne 0) { throw "Failed to copy embeddings CSV into PostgreSQL." }

  docker compose cp $ImportSql postgres:/tmp/import-colab-embeddings.sql
  if ($LASTEXITCODE -ne 0) { throw "Failed to copy import SQL into PostgreSQL." }

  docker compose exec -T postgres psql -v ON_ERROR_STOP=1 -U legal_rag -d legal_rag -f /tmp/import-colab-embeddings.sql
  if ($LASTEXITCODE -ne 0) { throw "PostgreSQL import failed." }
}
finally {
  Pop-Location
}
