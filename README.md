# Supernova Search

Supernova Search is a local Python web search engine with a polished dark interface. It crawls public websites, stores pages in SQLite, indexes keywords with FTS5, ranks with BM25-style scoring and reciprocal-rank fusion, and optionally adds semantic vectors and a neural cross-encoder reranker.

## Install and launch the web UI

```bash
python -m venv .venv
# Linux/macOS
source .venv/bin/activate
# Windows PowerShell: .venv\\Scripts\\Activate.ps1
pip install -r requirements.txt
python app.py
```

Open <http://127.0.0.1:5000>. Search indexed pages from the home page, or enter a public website URL in **Bring a website into orbit**. UI crawls are intentionally bounded to 25 pages and one link depth, are restricted to the seed host, and honor robots.txt. The app binds to localhost by default. Use `SUPERNOVA_DB` to change the SQLite database path, or `SUPERNOVA_PORT` to change the port.

## Crawl from the command line

```bash
python main.py crawl https://example.com --max-pages 100 --max-depth 2 --delay 1
python main.py search "python search engine" --top-k 10
```

Use only on sites you own or have permission to crawl. The crawler uses a descriptive user agent, checks robots.txt, limits response sizes and timeouts, avoids non-public IP destinations, and stays on each seed's host.

## Optional semantic retrieval and reranking

```bash
pip install -r requirements-semantic.txt
python main.py --semantic --rerank search "how does a search engine rank pages"
```

The first semantic run downloads `sentence-transformers/all-MiniLM-L6-v2`; reranking uses `cross-encoder/ms-marco-MiniLM-L-6-v2`. Embeddings are stored in SQLite alongside the separate FTS5 keyword index. This lightweight implementation scans local vectors and is designed for personal/small collections, not web-scale search.

## Tests

```bash
python -m unittest discover -s tests -v
```
