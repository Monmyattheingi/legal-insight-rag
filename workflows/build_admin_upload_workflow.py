import copy
import json
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent
source = json.loads((ROOT / "legal-admin-current.json").read_text(encoding="utf-8"))[0]
by_name = {node["name"]: node for node in source["nodes"]}


def node_id():
    return str(uuid.uuid4())


webhook = {
    "parameters": {
        "httpMethod": "POST",
        "path": "admin-law-upload",
        "responseMode": "responseNode",
        "options": {},
    },
    "type": "n8n-nodes-base.webhook",
    "typeVersion": 2,
    "position": [-620, 0],
    "id": node_id(),
    "name": "Admin Upload Webhook",
    "webhookId": "e9d38361-ae3a-4c8a-96e2-4cfe50c2d055",
}

extract = copy.deepcopy(by_name["HTTP Request"])
extract.update(id=node_id(), name="Extract DOCX", position=[-400, 0])

merge = {
    "parameters": {
        "jsCode": """const extracted = $input.first().json;
const upload = $('Admin Upload Webhook').first();
const body = upload.json.body || {};

return [{
  json: {
    ...extracted,
    law_name: body.law_name,
    law_number: body.law_number || null,
    category: body.category || null,
    language: body.language || 'my',
    source_url: body.source_url || '',
    source_file_name: extracted.filename || upload.binary?.document?.fileName || null,
  },
}];"""
    },
    "type": "n8n-nodes-base.code",
    "typeVersion": 2,
    "position": [-180, 0],
    "id": node_id(),
    "name": "Merge Upload Metadata",
}

create_document = copy.deepcopy(by_name["Execute a SQL query"])
create_document.update(id=node_id(), name="Create Document", position=[40, 0])

prepare = {
    "parameters": {
        "jsCode": """const document = $input.first().json;
const extracted = $('Merge Upload Metadata').first().json;
return [{ json: { ...extracted, document_id: document.id } }];"""
    },
    "type": "n8n-nodes-base.code",
    "typeVersion": 2,
    "position": [260, 0],
    "id": node_id(),
    "name": "Prepare Chunker Input",
}

chunk = copy.deepcopy(by_name["Code in JavaScript"])
chunk.update(id=node_id(), name="Create Legal Chunks", position=[480, 0])

respond = {
    "parameters": {
        "respondWith": "json",
        "responseBody": "={{ { document_id: $('Create Document').first().json.id, chunks: $input.all().map(item => item.json) } }}",
        "options": {},
    },
    "type": "n8n-nodes-base.respondToWebhook",
    "typeVersion": 1.4,
    "position": [700, 0],
    "id": node_id(),
    "name": "Return Chunks to Admin",
}

nodes = [webhook, extract, merge, create_document, prepare, chunk, respond]
names = [node["name"] for node in nodes]
connections = {
    name: {"main": [[{"node": names[index + 1], "type": "main", "index": 0}]]}
    for index, name in enumerate(names[:-1])
}

workflow = {
    "id": "LegalAdminUpload01",
    "name": "Legal Insight Admin - DOCX to Chunks",
    "nodes": nodes,
    "connections": connections,
    "active": False,
    "settings": {"executionOrder": "v1"},
    "versionId": str(uuid.uuid4()),
    "meta": {"templateCredsSetupCompleted": True},
    "tags": [],
}

(ROOT / "admin-law-upload.json").write_text(
    json.dumps([workflow], ensure_ascii=False, indent=2), encoding="utf-8"
)
print("Created workflows/admin-law-upload.json")
