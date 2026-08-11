# BGE-M3 GPU embedding with Google Colab

This path uses the exact same checksummed `bge-m3-q4` GGUF in Colab and local
Ollama, with 1,024-dimensional vectors. Only the heavy bulk computation moves
from the laptop CPU to a Colab GPU.

## Run the GPU embedding

1. Open <https://colab.research.google.com/>.
2. Choose **File > Upload notebook** and upload `colab-bge-m3-embed.ipynb`.
3. Choose **Runtime > Change runtime type > T4 GPU**.
4. Choose **Runtime > Run all**.
5. When prompted, upload `workflows/legal_chunks_for_colab.json`.
6. Wait for the progress bar. The notebook validates every vector and then
   downloads `legal_chunks_embedded.csv`.

## Import the completed vectors

Move the downloaded CSV into this project folder, then run PowerShell from the
project folder:

```powershell
.\import-colab-embeddings.ps1 -CsvPath .\legal_chunks_embedded.csv
```

The importer accepts any non-empty law export, but still refuses vectors that
are not 1,024 dimensions. It also embeds a sample chunk locally and requires
identical-text cosine similarity of at least 0.98 before PostgreSQL is changed.
PostgreSQL then upserts every chunk and reports the final stored chunk and
embedding counts for the imported document ids.
