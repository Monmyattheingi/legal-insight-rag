# Local Burmese OCR in n8n

The OCR service runs only inside the Docker Compose network. It is intentionally not published to the host.

## Start or rebuild

```cmd
cd /d E:\Final_Project\legal_rag_starter
docker compose up -d --build
docker compose ps
```

The `ocr` service should become healthy. Verify from inside n8n's container:

```cmd
docker compose exec n8n wget -qO- http://ocr:8000/health
```

## Add the OCR node

After **On form submission**, add an **HTTP Request** node:

- Method: `POST`
- URL: `http://ocr:8000/ocr`
- Authentication: `None`
- Send Body: enabled
- Body Content Type: `Form-Data`
- Add parameter:
  - Parameter Type: `n8n Binary File`
  - Name: `file`
  - Input Data Field Name: `document`
- For the first quality test, add a second form-data parameter:
  - Parameter Type: `Form Data`
  - Name: `max_pages`
  - Value: `2`
- Add three more Form Data parameters for the improved Burmese profile:
  - Name: `languages`, Value: `mya`
  - Name: `dpi`, Value: `400`
  - Name: `psm`, Value: `3`
- Timeout: `900000` ms

Execute the workflow and upload the PDF again. Only the first two pages will be
processed for this test. Remove `max_pages` after confirming OCR quality.

```json
{
  "text": "Unicode OCR text...",
  "pages": [{"page": 1, "text": "..."}],
  "page_count": 47,
  "languages": "mya+eng",
  "dpi": 300
}
```

Keep the original **Extract From File** route for Unicode PDFs. Use this OCR route for corrupted or scanned PDFs. Manually compare several sections and numbers against the PDF before embedding a new source.
