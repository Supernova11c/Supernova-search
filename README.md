# Supernova Search

Supernova Search is a local Python search application with a Flask UI, a FastAPI JSON API, SQLite FTS5 keyword retrieval, BM25-style ranking, rank fusion, optional local semantic vectors/reranking, and an authenticated admin panel for curated URL injection and bounded ranking boosts.

## Run locally

```bash
python -m venv .venv
# Linux/macOS: source .venv/bin/activate
# Windows PowerShell: .venv\\Scripts\\Activate.ps1
pip install -r requirements.txt
export SUPERNOVA_SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
export SUPERNOVA_ADMIN_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
python app.py
```

Open <http://127.0.0.1:5000>. The API runs separately with `uvicorn api:app --host 127.0.0.1 --port 8000`; its interactive docs are at `/docs`.

## Admin URL injection and ranking

Configure `SUPERNOVA_ADMIN_TOKEN`, open `/admin/login`, and sign in with that token. The admin panel accepts a single public HTTP(S) URL and a priority from 1–100. It performs a bounded one-page crawl, respects robots.txt, and rejects non-public host addresses. A URL is not force-indexed if the site denies crawling or does not return indexable HTML. Priority is only a bounded ranking boost for matching documents, not a way to make irrelevant pages match every query. Set a page's priority to 0 to remove its boost.

Admin API equivalent:

```bash
curl -X POST http://127.0.0.1:8000/admin/inject \\
  -H "Authorization: Bearer $SUPERNOVA_ADMIN_TOKEN" \\
  -H "Content-Type: application/json" \\
  -d '{"url":"https://example.com/guide","priority":85}'
```

## Docker

Copy `.env.example` to `.env`, replace both secrets with strong random values, then run:

```bash
docker compose up --build
```

The Flask UI is on `127.0.0.1:5000`; FastAPI is on `127.0.0.1:8000`. Both share a persistent SQLite database volume. Put a TLS-terminating reverse proxy in front before exposing externally and set `SUPERNOVA_COOKIE_SECURE=1` behind HTTPS.

## Indexing and ranking

The keyword index and document metadata are in SQLite/FTS5; the optional semantic embeddings are stored separately in SQLite. Ranking combines BM25-style lexical scores, reciprocal-rank fusion, an optional sentence-transformers vector candidate set and cross-encoder reranking, plus the admin priority boost. Install optional ML support with `pip install -r requirements-semantic.txt`.

This setup is intended for a single-machine, small-to-medium corpus. PostgreSQL/Qdrant are not enabled in this deployment yet; the storage interfaces should be migrated before using a distributed or high-volume production deployment. URL crawling should only target sites you own or are authorized to crawl.

## Tests

```bash
python -m unittest discover -s tests -v
```
