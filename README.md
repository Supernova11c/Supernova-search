# Supernova Search

A small, local web search engine written in Python. It crawls public websites, stores pages in SQLite, builds a keyword index, ranks with BM25, and can optionally use vector similarity and a cross-encoder reranker.

## Install

```bash
python -m venv .venv
# Linux/macOS
source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Semantic vectors and neural reranking are optional because they download machine-learning models on first use:

```bash
pip install -r requirements-semantic.txt
```

## Crawl and index

Start with a site you own or are allowed to crawl:

```bash
python main.py crawl https://example.com --max-pages 100 --max-depth 2 --delay 1
```

Several seed URLs can be provided. Crawling is limited to each seed's host, observes `robots.txt`, uses a descriptive user agent, and applies page, depth, delay, response-size, and timeout limits. The SQLite database (`supernova.db` by default) persists between runs. Change it with `--db path/to/index.db`.

## Search

```bash
python main.py search "python search engine" --top-k 10
```

Enable semantic vector retrieval:

```bash
python main.py --semantic search "how do search rankings work"
```

Use the cross-encoder reranker too (more compute-intensive):

```bash
python main.py --semantic --rerank search "python search engine"
```

The first semantic run downloads the `all-MiniLM-L6-v2` embedding model; reranking uses `cross-encoder/ms-marco-MiniLM-L-6-v2`. Embeddings are stored in the `vectors` SQLite table. Keyword postings live in SQLite FTS5, with BM25 scores fused with keyword/vector ranks using reciprocal rank fusion. The reranker is applied to the fused candidate set.

## Notes

This is a practical single-machine starter, not a web-scale crawler: search candidates and vectors are processed locally, and the optional vector index currently scans stored vectors. For large collections, move the vector table to a dedicated vector database and add distributed crawling, deduplication, canonical URL handling, and operational monitoring. Always follow site terms, robots directives, and applicable law.
