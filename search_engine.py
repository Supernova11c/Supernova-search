"""SQLite-backed hybrid search with FTS5, BM25, optional embeddings and reranking."""

from __future__ import annotations

import json
import math
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

TOKEN_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)


@dataclass
class SearchResult:
    url: str
    title: str
    snippet: str
    score: float


class SearchEngine:
    """Persistent hybrid index. SQLite FTS5 stores keyword postings and vectors are persisted separately."""

    def __init__(self, db_path="supernova.db", semantic=False, rerank=False):
        self.db_path = str(db_path)
        self.connection = sqlite3.connect(self.db_path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA journal_mode=WAL")
        self._encoder = None
        self._cross_encoder = None
        self._setup()
        if semantic:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:
                raise RuntimeError("Semantic search requires optional dependencies: pip install -r requirements-semantic.txt") from exc
            self._encoder = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
        if rerank:
            try:
                from sentence_transformers import CrossEncoder
            except ImportError as exc:
                raise RuntimeError("Reranking requires optional dependencies: pip install -r requirements-semantic.txt") from exc
            self._cross_encoder = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")

    def _setup(self):
        self.connection.executescript("""
            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY,
                url TEXT NOT NULL UNIQUE,
                title TEXT NOT NULL DEFAULT '',
                text TEXT NOT NULL DEFAULT '',
                fetched_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
                title, text, content='documents', content_rowid='id', tokenize='unicode61'
            );
            CREATE TABLE IF NOT EXISTS vectors (
                document_id INTEGER PRIMARY KEY REFERENCES documents(id) ON DELETE CASCADE,
                model TEXT NOT NULL,
                embedding TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS documents_url_idx ON documents(url);
        """)
        self.connection.commit()

    @staticmethod
    def tokenize(text):
        return TOKEN_RE.findall((text or "").lower())

    def add_document(self, url, title, text):
        """Insert or refresh one crawled page and update both indexes."""
        title = (title or "").strip()[:1000]
        text = (text or "").strip()
        if not url or not text:
            return
        existing = self.connection.execute("SELECT id FROM documents WHERE url = ?", (url,)).fetchone()
        if existing:
            doc_id = existing["id"]
            self.connection.execute("DELETE FROM documents_fts WHERE rowid = ?", (doc_id,))
            self.connection.execute("DELETE FROM vectors WHERE document_id = ?", (doc_id,))
            self.connection.execute(
                "UPDATE documents SET title = ?, text = ?, fetched_at = CURRENT_TIMESTAMP WHERE id = ?",
                (title, text, doc_id),
            )
        else:
            cursor = self.connection.execute("INSERT INTO documents(url, title, text) VALUES (?, ?, ?)", (url, title, text))
            doc_id = cursor.lastrowid
        self.connection.execute("INSERT INTO documents_fts(rowid, title, text) VALUES (?, ?, ?)", (doc_id, title, text))
        if self._encoder is not None:
            embedding = self._encoder.encode(f"{title}\n{text[:12000]}", normalize_embeddings=True)
            self.connection.execute(
                "INSERT OR REPLACE INTO vectors(document_id, model, embedding) VALUES (?, ?, ?)",
                (doc_id, "all-MiniLM-L6-v2", json.dumps(embedding.tolist())),
            )
        self.connection.commit()

    def _vector_candidates(self, query, limit):
        if self._encoder is None:
            return []
        rows = self.connection.execute(
            "SELECT d.id, d.url, d.title, d.text, v.embedding FROM vectors v "
            "JOIN documents d ON d.id = v.document_id WHERE v.model = ?",
            ("all-MiniLM-L6-v2",),
        ).fetchall()
        if not rows:
            return []
        query_vector = self._encoder.encode(query, normalize_embeddings=True)
        scored = []
        for row in rows:
            vector = json.loads(row["embedding"])
            score = sum(float(a) * float(b) for a, b in zip(query_vector, vector))
            scored.append((row, score))
        return [row for row, _ in sorted(scored, key=lambda pair: pair[1], reverse=True)[:limit]]

    def search(self, query, top_k=10):
        terms = self.tokenize(query)
        if not terms or top_k <= 0:
            return []
        # Quote each token so user-entered FTS operators cannot alter the query grammar.
        fts_query = " OR ".join('"' + term.replace('"', '""') + '"' for term in terms)
        keyword_rows = self.connection.execute(
            "SELECT d.id, d.url, d.title, d.text FROM documents_fts f "
            "JOIN documents d ON d.id = f.rowid WHERE documents_fts MATCH ? LIMIT 1000",
            (fts_query,),
        ).fetchall()
        vector_rows = self._vector_candidates(query, 200)
        candidates = {row["id"]: row for row in keyword_rows}
        candidates.update({row["id"]: row for row in vector_rows})
        if not candidates:
            return []

        # BM25 scoring over the candidate set, combined with vector/keyword ranks via RRF.
        docs = list(candidates.values())
        token_docs = [self.tokenize(row["title"] + " " + row["text"]) for row in docs]
        avg_len = sum(map(len, token_docs)) / max(len(token_docs), 1)
        doc_freq = {}
        for tokens in token_docs:
            for token in set(tokens):
                doc_freq[token] = doc_freq.get(token, 0) + 1
        query_terms = set(terms)
        bm25_scores = {}
        k1, b = 1.5, 0.75
        for row, tokens in zip(docs, token_docs):
            frequencies = {}
            for token in tokens:
                frequencies[token] = frequencies.get(token, 0) + 1
            score = 0.0
            for term in query_terms:
                frequency = frequencies.get(term, 0)
                if not frequency:
                    continue
                idf = math.log(1 + (len(docs) - doc_freq.get(term, 0) + 0.5) / (doc_freq.get(term, 0) + 0.5))
                denominator = frequency + k1 * (1 - b + b * len(tokens) / max(avg_len, 1))
                score += idf * (frequency * (k1 + 1)) / denominator
            bm25_scores[row["id"]] = score
        bm25_order = sorted(bm25_scores, key=bm25_scores.get, reverse=True)
        keyword_order = [row["id"] for row in keyword_rows]
        vector_order = [row["id"] for row in vector_rows]
        ranks = {"bm25": bm25_order, "keyword": keyword_order, "vector": vector_order}
        fused = {}
        for source, ordered_ids in ranks.items():
            weight = 1.0 if source == "bm25" else (0.8 if source == "vector" else 0.7)
            for rank, doc_id in enumerate(ordered_ids, start=1):
                fused[doc_id] = fused.get(doc_id, 0.0) + weight / (60 + rank)

        ordered = sorted(candidates.values(), key=lambda row: fused.get(row["id"], 0), reverse=True)[:max(top_k * 5, top_k)]
        if self._cross_encoder is not None and ordered:
            pairs = [(query, (row["title"] + " " + row["text"])[:3000]) for row in ordered]
            scores = self._cross_encoder.predict(pairs)
            ordered = [row for _, row in sorted(zip(scores, ordered), key=lambda item: float(item[0]), reverse=True)]

        results = []
        for row in ordered[:top_k]:
            plain_text = re.sub(r"\s+", " ", row["text"]).strip()
            results.append(SearchResult(row["url"], row["title"], plain_text[:280] + ("…" if len(plain_text) > 280 else ""), fused.get(row["id"], 0.0)))
        return results

    def count(self):
        return self.connection.execute("SELECT COUNT(*) FROM documents").fetchone()[0]

    def close(self):
        self.connection.close()

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        self.close()
