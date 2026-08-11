# Legal Insight Admin

This is a separate admin interface. It does not modify or replace the existing user frontend.

## Run

From the project root:

```powershell
python .\frontend\admin\server.py
```

Then open `http://127.0.0.1:8001`.

The first version is read-only and shows database, document, chunk, and embedding health.
