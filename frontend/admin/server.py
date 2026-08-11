import cgi
import json
import re
import subprocess
import uuid
import mimetypes
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parents[1]
UPLOAD_DIR = BASE_DIR / "uploads"
QUEUE_FILE = UPLOAD_DIR / "queue.json"
MAX_UPLOAD_BYTES = 25 * 1024 * 1024
MAX_CSV_BYTES = 100 * 1024 * 1024
N8N_UPLOAD_URL = "http://127.0.0.1:5678/webhook/admin-law-upload"
IMPORT_SCRIPT = PROJECT_DIR / "import-colab-embeddings.ps1"

DOCUMENT_QUERY = r"""
SELECT COALESCE(json_agg(row_to_json(result)), '[]'::json)
FROM (
  SELECT d.id, d.law_name,
         COALESCE(
           NULLIF(d.metadata->>'format', ''),
           NULLIF(lower(regexp_replace(d.source_file_name, '^.*\.', '')), ''),
           'document'
         ) AS format,
         count(c.id)::int AS chunks,
         count(c.embedding)::int AS embeddings
    FROM legal_documents d
    LEFT JOIN legal_chunks c ON c.document_id = d.id
   GROUP BY d.id, d.law_name, d.metadata, d.source_file_name, d.imported_at
   ORDER BY d.imported_at DESC
) result;
"""

QUALITY_QUERY = r"""
SELECT COALESCE(json_agg(row_to_json(result)), '[]'::json)
FROM (
  SELECT d.id, d.law_name, d.law_number, d.source_url,
         count(c.id)::int AS chunks,
         count(c.embedding)::int AS embeddings,
         count(*) FILTER (WHERE c.id IS NOT NULL AND c.section IS NULL)::int AS missing_sections,
         count(*) FILTER (WHERE c.id IS NOT NULL AND length(trim(c.content)) < 40)::int AS short_chunks
    FROM legal_documents d
    LEFT JOIN legal_chunks c ON c.document_id = d.id
   GROUP BY d.id, d.law_name, d.law_number, d.source_url, d.imported_at
   ORDER BY d.imported_at DESC
) result;
"""

QUERY_RUNS_QUERY = r"""
SELECT COALESCE(json_agg(row_to_json(result)), '[]'::json)
FROM (
  SELECT id, question, case_type, selected_law, selected_section,
         punishment_section, response_mode, answerable, top_score,
         total_ms, created_at
    FROM query_runs
   ORDER BY created_at DESC
   LIMIT 100
) result;
"""


def database_query(query):
    process = subprocess.run(
        [
            "docker", "compose", "exec", "-T", "postgres", "psql",
            "-U", "legal_rag", "-d", "legal_rag", "-t", "-A", "-c", query,
        ],
        cwd=PROJECT_DIR,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=20,
        check=True,
    )
    return json.loads(process.stdout.strip() or "[]")


def database_documents():
    return database_query(DOCUMENT_QUERY)


def read_queue():
    if not QUEUE_FILE.exists():
        return []
    try:
        return json.loads(QUEUE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def write_queue(items):
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    QUEUE_FILE.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def send_to_n8n(file_path, fields):
    boundary = f"----LegalInsight{uuid.uuid4().hex}"
    body = bytearray()
    for name, value in fields.items():
        body.extend(f"--{boundary}\r\n".encode())
        body.extend(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        body.extend(str(value or "").encode("utf-8"))
        body.extend(b"\r\n")
    body.extend(f"--{boundary}\r\n".encode())
    body.extend(f'Content-Disposition: form-data; name="document"; filename="{file_path.name}"\r\n'.encode())
    body.extend(f"Content-Type: {mimetypes.guess_type(file_path.name)[0] or 'application/octet-stream'}\r\n\r\n".encode())
    body.extend(file_path.read_bytes())
    body.extend(b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode())
    request = Request(N8N_UPLOAD_URL, data=bytes(body), headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}, method="POST")
    with urlopen(request, timeout=900) as response:
        return json.loads(response.read().decode("utf-8"))


class AdminHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(BASE_DIR), **kwargs)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/admin/overview":
            return self.send_overview()
        if path == "/api/admin/processing":
            return self.send_processing()
        if path == "/api/admin/quality":
            return self.send_quality()
        if path == "/api/admin/query-runs":
            return self.send_query_runs()
        if path.startswith("/api/admin/query-runs/"):
            return self.send_query_run(path.rsplit("/", 1)[-1])
        if path.startswith("/api/admin/download/"):
            return self.send_chunk_download(path.rsplit("/", 1)[-1])
        if path == "/":
            self.path = "/index.html"
        return super().do_GET()

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/api/admin/upload":
            return self.receive_upload()
        if path == "/api/admin/import-csv":
            return self.receive_embedding_csv()
        self.send_json({"error": "not found"}, 404)

    def send_overview(self):
        try:
            documents = database_documents()
            chunks = sum(int(item["chunks"]) for item in documents)
            embeddings = sum(int(item["embeddings"]) for item in documents)
            warnings = sum(
                1 for item in documents
                if not item["chunks"] or int(item["chunks"]) != int(item["embeddings"])
            )
            payload = {
                "summary": {
                    "documents": len(documents), "chunks": chunks,
                    "embeddings": embeddings, "warnings": warnings,
                },
                "documents": documents,
            }
            self.send_json(payload, 200)
        except (subprocess.SubprocessError, json.JSONDecodeError, OSError) as exc:
            self.send_json({"error": "database unavailable", "detail": str(exc)}, 503)

    def send_processing(self):
        try:
            documents = database_documents()
            items = []
            for item in documents:
                chunks, embeddings = int(item["chunks"]), int(item["embeddings"])
                stage = "Indexed" if chunks and chunks == embeddings else "Embedded" if embeddings else "Chunked" if chunks else "Uploaded"
                items.append({**item, "stage": stage})
            known_names = {item.get("law_name", "").strip() for item in documents if int(item.get("chunks", 0)) > 0}
            for queued in reversed(read_queue()):
                if queued.get("law_name", "").strip() not in known_names:
                    stage = "Chunked" if queued.get("status") == "chunked" else "Uploaded"
                    items.insert(0, {**queued, "chunks": queued.get("chunk_count", 0), "embeddings": 0, "stage": stage})
            self.send_json({"items": items}, 200)
        except (subprocess.SubprocessError, json.JSONDecodeError, OSError) as exc:
            self.send_json({"error": "processing data unavailable", "detail": str(exc)}, 503)

    def send_quality(self):
        try:
            documents = database_query(QUALITY_QUERY)
            issue_count = 0
            review_count = 0
            for item in documents:
                chunks, embeddings = int(item["chunks"]), int(item["embeddings"])
                issues = []
                if chunks == 0: issues.append("Chunks မရှိပါ")
                if embeddings < chunks: issues.append(f"Embedding မပြည့်ပါ ({embeddings}/{chunks})")
                if int(item["short_chunks"]): issues.append(f"အလွန်တိုသော chunk {item['short_chunks']} ခု")
                if chunks and int(item["missing_sections"]) == chunks: issues.append("Section metadata မရှိပါ")
                if not item.get("law_number"): issues.append("ဥပဒေအမှတ် metadata မရှိပါ")
                item["issues"] = issues
                issue_count += len(issues)
                review_count += bool(issues)
            self.send_json({"summary": {"healthy": len(documents) - review_count, "review": review_count, "issues": issue_count}, "documents": documents}, 200)
        except (subprocess.SubprocessError, json.JSONDecodeError, OSError) as exc:
            self.send_json({"error": "quality data unavailable", "detail": str(exc)}, 503)

    def send_query_runs(self):
        try:
            self.send_json({"items": database_query(QUERY_RUNS_QUERY)}, 200)
        except (subprocess.SubprocessError, json.JSONDecodeError, OSError) as exc:
            self.send_json({"error": "query trace data unavailable", "detail": str(exc)}, 503)

    def send_query_run(self, run_id):
        try:
            numeric_id = int(run_id)
            query = f"""
            SELECT COALESCE(row_to_json(result), '{{}}'::json)
            FROM (
              SELECT r.*,
                     COALESCE((
                       SELECT json_agg(row_to_json(step_result) ORDER BY step_result.step_order)
                       FROM (
                         SELECT step_order, step_name, status, duration_ms, details
                         FROM query_trace_steps
                         WHERE query_run_id = r.id
                         ORDER BY step_order
                       ) step_result
                     ), '[]'::json) AS steps
              FROM query_runs r
              WHERE r.id = {numeric_id}
            ) result;
            """
            item = database_query(query)
            if not item:
                return self.send_json({"error": "query trace not found"}, 404)
            self.send_json(item, 200)
        except ValueError:
            self.send_json({"error": "invalid query trace id"}, 400)
        except (subprocess.SubprocessError, json.JSONDecodeError, OSError) as exc:
            self.send_json({"error": "query trace data unavailable", "detail": str(exc)}, 503)

    def receive_upload(self):
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            if content_length <= 0 or content_length > MAX_UPLOAD_BYTES:
                return self.send_json({"error": "ဖိုင်အရွယ်အစား 25 MB ထက်မကျော်ရပါ"}, 400)
            form = cgi.FieldStorage(fp=self.rfile, headers=self.headers, environ={"REQUEST_METHOD": "POST", "CONTENT_TYPE": self.headers.get("Content-Type", ""), "CONTENT_LENGTH": str(content_length)})
            law_name = form.getfirst("law_name", "").strip()
            file_item = form["file"] if "file" in form else None
            if not law_name or file_item is None or not getattr(file_item, "filename", ""):
                return self.send_json({"error": "ဥပဒေအမည်နှင့် DOCX/PDF ဖိုင်လိုအပ်ပါသည်"}, 400)
            original_name = Path(file_item.filename).name
            suffix = Path(original_name).suffix.lower()
            if suffix != ".docx":
                return self.send_json({"error": "လက်ရှိ n8n ချိတ်ဆက်မှုတွင် DOCX ဖိုင်သာ လက်ခံပါသည်"}, 400)
            safe_stem = re.sub(r"[^A-Za-z0-9_-]+", "-", Path(original_name).stem).strip("-") or "legal-document"
            stored_name = f"{datetime.now():%Y%m%d-%H%M%S}-{safe_stem}{suffix}"
            UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
            destination = UPLOAD_DIR / stored_name
            with destination.open("wb") as output:
                while chunk := file_item.file.read(1024 * 1024): output.write(chunk)
            entry = {"id": str(uuid.uuid4()), "law_name": law_name, "law_number": form.getfirst("law_number", "").strip(), "category": form.getfirst("category", "").strip(), "source_url": form.getfirst("source_url", "").strip(), "file_name": original_name, "stored_name": stored_name, "format": suffix[1:], "uploaded_at": datetime.now(timezone.utc).isoformat(), "status": "staged"}
            queue = read_queue(); queue.append(entry); write_queue(queue)
            try:
                entry["status"] = "processing"
                write_queue(queue)
                result = send_to_n8n(destination, {
                    "law_name": law_name, "law_number": entry["law_number"],
                    "category": entry["category"], "source_url": entry["source_url"],
                    "language": "my",
                })
                chunks = result.get("chunks", [])
                chunks_name = f"{entry['id']}-chunks.json"
                (UPLOAD_DIR / chunks_name).write_text(json.dumps(chunks, ensure_ascii=False, indent=2), encoding="utf-8")
                entry.update({"status": "chunked", "document_id": result.get("document_id"), "chunk_count": len(chunks), "chunks_file": chunks_name})
                write_queue(queue)
                self.send_json({"message": f"DOCX ကို n8n ဖြင့် chunk {len(chunks)} ခု ပြုလုပ်ပြီးပါပြီ။ Processing စာမျက်နှာမှ JSON download လုပ်ပြီး Colab သို့တင်ပါ။", "item": entry}, 201)
            except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
                entry.update({"status": "n8n_error", "error": str(exc)})
                write_queue(queue)
                self.send_json({"error": "ဖိုင်ကိုသိမ်းပြီးပါပြီ၊ သို့သော် n8n processing မအောင်မြင်ပါ", "detail": str(exc), "item": entry}, 502)
        except (OSError, ValueError, KeyError) as exc:
            self.send_json({"error": "upload failed", "detail": str(exc)}, 500)

    def send_chunk_download(self, item_id):
        entry = next((item for item in read_queue() if item.get("id") == item_id), None)
        if not entry or not entry.get("chunks_file"):
            return self.send_json({"error": "chunk JSON မတွေ့ပါ"}, 404)
        path = UPLOAD_DIR / Path(entry["chunks_file"]).name
        if not path.exists():
            return self.send_json({"error": "chunk JSON ဖိုင်မရှိပါ"}, 404)
        content = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Disposition", f'attachment; filename="{entry["id"]}-chunks.json"')
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def receive_embedding_csv(self):
        csv_path = None
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            if content_length <= 0 or content_length > MAX_CSV_BYTES:
                return self.send_json({"error": "CSV ဖိုင်အရွယ်အစား 100 MB ထက်မကျော်ရပါ"}, 400)
            form = cgi.FieldStorage(fp=self.rfile, headers=self.headers, environ={"REQUEST_METHOD": "POST", "CONTENT_TYPE": self.headers.get("Content-Type", ""), "CONTENT_LENGTH": str(content_length)})
            file_item = form["file"] if "file" in form else None
            if file_item is None or not getattr(file_item, "filename", ""):
                return self.send_json({"error": "Colab မှရသော embedded CSV ဖိုင်လိုအပ်ပါသည်"}, 400)
            original_name = Path(file_item.filename).name
            if Path(original_name).suffix.lower() != ".csv":
                return self.send_json({"error": "CSV ဖိုင်သာ လက်ခံပါသည်"}, 400)
            UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
            csv_path = UPLOAD_DIR / f"{datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:8]}-embedded.csv"
            with csv_path.open("wb") as output:
                while chunk := file_item.file.read(1024 * 1024):
                    output.write(chunk)
            process = subprocess.run(
                ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(IMPORT_SCRIPT), "-CsvPath", str(csv_path)],
                cwd=PROJECT_DIR, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=1800,
            )
            if process.returncode != 0:
                detail = (process.stderr or process.stdout or "CSV import failed").strip()
                return self.send_json({"error": "Embedding CSV import မအောင်မြင်ပါ", "detail": detail[-3000:]}, 400)
            documents = database_documents()
            self.send_json({
                "message": "Embedding CSV ကို database ထဲသို့ အောင်မြင်စွာ import လုပ်ပြီးပါပြီ။",
                "detail": process.stdout.strip()[-3000:],
                "summary": {"documents": len(documents), "chunks": sum(int(x["chunks"]) for x in documents), "embeddings": sum(int(x["embeddings"]) for x in documents)},
            }, 200)
        except subprocess.TimeoutExpired:
            self.send_json({"error": "CSV import အချိန်ကျော်သွားပါသည်", "detail": "Ollama နှင့် Docker services ကို စစ်ဆေးပါ။"}, 504)
        except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
            self.send_json({"error": "CSV import failed", "detail": str(exc)}, 500)

    def send_json(self, payload, status):
        content = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, message, *args):
        print(f"[admin] {message % args}")


if __name__ == "__main__":
    address = ("127.0.0.1", 8001)
    print("Legal Insight Admin: http://127.0.0.1:8001")
    ThreadingHTTPServer(address, AdminHandler).serve_forever()
