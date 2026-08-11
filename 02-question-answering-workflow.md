# n8n Workflow 02 — Cited question answering

1. **Webhook** — POST `/legal-question`:

```json
{"question":"အသက် ၈ နှစ်အရွယ် ကလေးတစ်ဦးက...","category":"child-law"}
```

2. **Validate input** — reject empty/oversized questions.
3. **HTTP Request: Ollama embeddings** — use the same local `bge-m3` model as ingestion.
4. **Postgres hybrid retrieval**

```sql
SELECT * FROM match_legal_chunks($1::vector,$2,10,$3);
```

Parameters: query embedding, question, optional category.

5. **Evidence gate** — return “insufficient evidence” when no useful result exists. Calibrate a minimum score using the evaluation set; do not guess a universal threshold.
6. **Basic LLM Chain** — use the prompt below.
7. **Postgres audit** — store question, retrieved chunk IDs and answer.
8. **Respond to Webhook** — return generated answer and source records separately.

## Grounded prompt

```text
You are a Myanmar legal information retrieval assistant, not a lawyer or court.

Use ONLY the supplied legal excerpts. Never invent a law, section, punishment,
effective date, precedent or missing fact. Separate user-stated facts from
assumptions. If evidence is insufficient, say so and list missing information.

Do not declare guilt or predict a final sentence or court outcome.
Cite every legal proposition as [law name, law number, section, source URL].
Mention amended, repealed, conflicting or unknown status.

USER REPORT:
{{ $json.question }}

RETRIEVED LEGAL EXCERPTS:
{{ $json.evidence }}

Return JSON:
summary
stated_facts[]
possible_legal_mappings[]
missing_facts[]
sources[]
disclaimer
```
