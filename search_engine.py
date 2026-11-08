"""SQLite-backed hybrid search with FTS5, BM25, optional embeddings and reranking."""

from __future__ import annotations

import json
import math
import re
import sqlite3
from dataclasses import dataclass
from urllib.parse import urlparse

TOKEN_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)

CATEGORIES = {
    "tech": ["python", "programming", "software", "code", "web", "api", "developer", "machine", "data", "ai", "database", "server", "backend", "frontend"],
    "science": ["science", "research", "physics", "chemistry", "biology", "lab", "astronomy", "genetics", "equation"],
    "business": ["business", "startup", "marketing", "sales", "team", "product", "growth", "finance", "brand"],
    "health": ["health", "fitness", "wellness", "nutrition", "medicine", "doctor", "medical", "sleep", "training"],
    "news": ["news", "politics", "world", "report", "current", "economy", "media", "publication"],
}


@dataclass
class SearchResult:
    url: str
    title: str
    snippet: str
    score: float
    category: str = "general"
    site: str = ""


class SearchEngine:
    """Persistent hybrid search engine backed by SQLite FTS5."""

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
                category TEXT NOT NULL DEFAULT 'general',
                site TEXT NOT NULL DEFAULT '',
                fetched_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
                title, text, category, site, content='documents', content_rowid='id', tokenize='unicode61'
            );
            CREATE TABLE IF NOT EXISTS vectors (
                document_id INTEGER PRIMARY KEY REFERENCES documents(id) ON DELETE CASCADE,
                model TEXT NOT NULL,
                embedding TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS search_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                query TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'all',
                sort TEXT NOT NULL DEFAULT 'relevance',
                result_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS crawl_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT NOT NULL,
                status TEXT NOT NULL,
                pages INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS collections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                query TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS documents_url_idx ON documents(url);
            CREATE INDEX IF NOT EXISTS search_logs_created_idx ON search_logs(created_at);
            CREATE INDEX IF NOT EXISTS crawl_logs_created_idx ON crawl_logs(created_at);
        """)
        self.connection.commit()

    @staticmethod
    def tokenize(text):
        return TOKEN_RE.findall((text or "").lower())

    @staticmethod
    def infer_category(value):
        text = (value or "").lower()
        for category, keywords in CATEGORIES.items():
            if any(keyword in text for keyword in keywords):
                return category
        return "general"

    @staticmethod
    def infer_site(url):
        parsed = urlparse(url)
        return (parsed.netloc or "").split(":")[0].lower()

    def add_document(self, url, title, text):
        title = (title or "").strip()[:1000]
        text = (text or "").strip()
        if not url or not text:
            return

        category = self.infer_category(f"{title} {text}")
        site = self.infer_site(url)

        existing = self.connection.execute("SELECT id FROM documents WHERE url = ?", (url,)).fetchone()
        if existing:
            doc_id = existing["id"]
            self.connection.execute("DELETE FROM documents_fts WHERE rowid = ?", (doc_id,))
            self.connection.execute("DELETE FROM vectors WHERE document_id = ?", (doc_id,))
            self.connection.execute(
                "UPDATE documents SET title = ?, text = ?, category = ?, site = ?, fetched_at = CURRENT_TIMESTAMP WHERE id = ?",
                (title, text, category, site, doc_id),
            )
        else:
            cursor = self.connection.execute(
                "INSERT INTO documents(url, title, text, category, site) VALUES (?, ?, ?, ?, ?)",
                (url, title, text, category, site),
            )
            doc_id = cursor.lastrowid

        self.connection.execute(
            "INSERT INTO documents_fts(rowid, title, text, category, site) VALUES (?, ?, ?, ?, ?)",
            (doc_id, title, text, category, site),
        )

        if self._encoder is not None:
            embedding = self._encoder.encode(f"{title}\n{text[:12000]}", normalize_embeddings=True)
            self.connection.execute(
                "INSERT OR REPLACE INTO vectors(document_id, model, embedding) VALUES (?, ?, ?)",
                (doc_id, "all-MiniLM-L6-v2", json.dumps(embedding.tolist())),
            )
        self.connection.commit()

    def record_search(self, query, category, sort, result_count):
        self.connection.execute(
            "INSERT INTO search_logs(query, category, sort, result_count) VALUES (?, ?, ?, ?)",
            (query.strip()[:300], category or "all", sort or "relevance", result_count),
        )
        self.connection.commit()

    def record_crawl(self, url, pages, status):
        self.connection.execute(
            "INSERT INTO crawl_logs(url, pages, status) VALUES (?, ?, ?)",
            (url or "", int(max(0, pages)), status or "failed"),
        )
        self.connection.commit()

    def save_collection(self, name, query):
        cleaned_name = (name or "").strip()[:80]
        cleaned_query = (query or "").strip()[:300]
        if not cleaned_name or not cleaned_query:
            return None
        cursor = self.connection.execute(
            "INSERT INTO collections(name, query) VALUES (?, ?) ON CONFLICT(name) DO UPDATE SET query=excluded.query, created_at=CURRENT_TIMESTAMP",
            (cleaned_name, cleaned_query),
        )
        self.connection.commit()
        return cursor.lastrowid

    def list_collections(self):
        rows = self.connection.execute(
            "SELECT id, name, query, created_at FROM collections ORDER BY created_at DESC LIMIT 20"
        ).fetchall()
        return [dict(row) for row in rows]

    def delete_collection(self, collection_id):
        self.connection.execute("DELETE FROM collections WHERE id = ?", (collection_id,))
        self.connection.commit()

    def collection_count(self):
        return self.connection.execute("SELECT COUNT(*) FROM collections").fetchone()[0]

    def get_dashboard_stats(self):
        total_documents = self.count()
        total_searches = self.connection.execute("SELECT COUNT(*) FROM search_logs").fetchone()[0]
        top_queries = self.connection.execute(
            "SELECT query, COUNT(*) AS count FROM search_logs GROUP BY query ORDER BY count DESC, query ASC LIMIT 5"
        ).fetchall()
        recent_queries = self.connection.execute(
            "SELECT query, category, result_count, created_at FROM search_logs ORDER BY created_at DESC LIMIT 6"
        ).fetchall()
        category_breakdown = self.connection.execute(
            "SELECT category, COUNT(*) AS count FROM search_logs GROUP BY category ORDER BY count DESC LIMIT 5"
        ).fetchall()
        return {
            "total_documents": total_documents,
            "total_searches": total_searches,
            "top_queries": [dict(row) for row in top_queries],
            "recent_queries": [dict(row) for row in recent_queries],
            "category_breakdown": [dict(row) for row in category_breakdown],
        }

    def get_recent_crawls(self, limit=8):
        rows = self.connection.execute(
            "SELECT url, status, pages, created_at FROM crawl_logs ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]

    def _vector_candidates(self, query, limit):
        if self._encoder is None:
            return []
        rows = self.connection.execute(
            "SELECT d.id, d.url, d.title, d.text, d.category, d.site, v.embedding FROM vectors v "
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

    def search(self, query, top_k=10, category="all", sort="relevance"):
        terms = self.tokenize(query)
        if not terms or top_k <= 0:
            return []

        fts_query = " OR ".join('"' + term.replace('"', '""') + '"' for term in terms)
        keyword_rows = self.connection.execute(
            "SELECT d.id, d.url, d.title, d.text, d.category, d.site FROM documents_fts f "
            "JOIN documents d ON d.id = f.rowid WHERE documents_fts MATCH ? LIMIT 1000",
            (fts_query,),
        ).fetchall()
        vector_rows = self._vector_candidates(query, 250)
        candidates = {row["id"]: row for row in keyword_rows}
        candidates.update({row["id"]: row for row in vector_rows})
        if not candidates:
            return []

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
        fused = {}
        for source, ordered_ids in {"bm25": bm25_order, "keyword": keyword_order, "vector": vector_order}.items():
            weight = 1.0 if source == "bm25" else (0.8 if source == "vector" else 0.7)
            for rank, doc_id in enumerate(ordered_ids, start=1):
                fused[doc_id] = fused.get(doc_id, 0.0) + weight / (60 + rank)

        ordered = sorted(candidates.values(), key=lambda row: fused.get(row["id"], 0), reverse=True)[: max(top_k * 5, top_k)]
        if self._cross_encoder is not None and ordered:
            pairs = [(query, (row["title"] + " " + row["text"])[:3000]) for row in ordered]
            scores = self._cross_encoder.predict(pairs)
            ordered = [row for _, row in sorted(zip(scores, ordered), key=lambda item: float(item[0]), reverse=True)]

        filtered = []
        for row in ordered:
            row_category = (row["category"] or "general").lower()
            if category and category != "all" and row_category != category:
                continue
            filtered.append(row)

        if not filtered:
            if category and category != "all":
                filtered = list(ordered)
            else:
                return []

        if sort == "latest":
            filtered.sort(key=lambda row: row["id"], reverse=True)
        elif sort == "site":
            filtered.sort(key=lambda row: (row["site"] or "", row["title"].lower()))
        else:
            filtered.sort(key=lambda row: fused.get(row["id"], 0.0), reverse=True)

        results = []
        for row in filtered[:top_k]:
            plain_text = re.sub(r"\s+", " ", row["text"]).strip()
            snippet = plain_text[:260] + ("…" if len(plain_text) > 260 else "")
            row_category = (row["category"] or "general").lower()
            results.append(
                SearchResult(
                    url=row["url"],
                    title=row["title"],
                    snippet=snippet,
                    score=float(fused.get(row["id"], 0.0)),
                    category=row_category,
                    site=row["site"],
                )
            )
        return results

    def count(self):
        return self.connection.execute("SELECT COUNT(*) FROM documents").fetchone()[0]

    def close(self):
        self.connection.close()

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        self.close()
