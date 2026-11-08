# Supernova Search

A simple Python search engine that indexes a set of documents and ranks matches by TF-IDF cosine similarity.

## Features

- Tokenization and normalization
- Lightweight in-memory indexing
- Ranked search results by relevance
- Simple command-line interface

## Run locally

```bash
python main.py
```

Example:

```text
Search> python language

1. 0.68 - Python is a high-level programming language used for web development.
2. 0.41 - Developers use Python for automation, data science, and backend APIs.
```

You can also run a one-off search:

```bash
python main.py "python programming"
```
