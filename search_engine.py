"""SQLite-backed hybrid search with BM25, reciprocal-rank fusion, and admin boosts."""

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
    def __init__(self, db_path="supernova.db", semantic=False, rerank=False):
        self.db_path = str(db_path)
        self.connection = sqlite3.connect(self.db_path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA journal_mode=WAL")
        self._encoder = None
        self._cross_encoder = None
        self._setup()
        if semantic or rerank:
            try:
                from sentence_transformers import CrossEncoder, SentenceTransformer
            except ImportError as exc:
                raise RuntimeError("Semantic search requires: pip install -r requirements-semantic.txt") from exc
            if semantic:
                self._encoder = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
            if rerank:
                self._cross_encoder = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")

    def _setup(self):
        self.connection.executescript("""
            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY, url TEXT NOT NULL UNIQUE,
                title TEXT NOT NULL DEFAULT '', text TEXT NOT NULL DEFAULT '',
                category TEXT NOT NULL DEFAULT 'general', site TEXT NOT NULL DEFAULT '',
                priority INTEGER NOT NULL DEFAULT 0,
                fetched_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
                title, text, category, site, content='documents', content_rowid='id', tokenize='unicode61'
            );
            CREATE TABLE IF NOT EXISTS vectors (
                document_id INTEGER PRIMARY KEY REFERENCES documents(id) ON DELETE CASCADE,
                model TEXT NOT NULL, embedding TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS search_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT, query TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'all', sort TEXT NOT NULL DEFAULT 'relevance',
                result_count INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS crawl_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT, url TEXT NOT NULL, status TEXT NOT NULL,
                pages INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS collections (
                id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE,
                query TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS documents_url_idx ON documents(url);
            CREATE INDEX IF NOT EXISTS documents_priority_idx ON documents(priority);
            CREATE INDEX IF NOT EXISTS search_logs_created_idx ON search_logs(created_at);
            CREATE INDEX IF NOT EXISTS crawl_logs_created_idx ON crawl_logs(created_at);
        """)
        # Upgrade databases created by earlier Supernova Search versions.
        columns = {row["name"] for row in self.connection.execute("PRAGMA table_info(documents)")}
        if "priority" not in columns:
            self.connection.execute("ALTER TABLE documents ADD COLUMN priority INTEGER NOT NULL DEFAULT 0")
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
        return (urlparse(url).hostname or "").lower()

    def add_document(self, url, title, text):
        title, text = (title or "").strip()[:1000], (text or "").strip()
        if not url or not text:
            return
        category, site = self.infer_category(f"{title} {text}"), self.infer_site(url)
        existing = self.connection.execute("SELECT id FROM documents WHERE url=?", (url,)).fetchone()
        if existing:
            doc_id = existing["id"]
            self.connection.execute("DELETE FROM documents_fts WHERE rowid=?", (doc_id,))
            self.connection.execute("DELETE FROM vectors WHERE document_id=?", (doc_id,))
            self.connection.execute(
                "UPDATE documents SET title=?,text=?,category=?,site=?,fetched_at=CURRENT_TIMESTAMP WHERE id=?",
                (title, text, category, site, doc_id),
            )
        else:
            cursor = self.connection.execute(
                "INSERT INTO documents(url,title,text,category,site) VALUES(?,?,?,?,?)",
                (url, title, text, category, site),
            )
            doc_id = cursor.lastrowid
        self.connection.execute("INSERT INTO documents_fts(rowid,title,text,category,site) VALUES(?,?,?,?,?)",
                                (doc_id, title, text, category, site))
        if self._encoder is not None:
            embedding = self._encoder.encode(f"{title}\n{text[:12000]}", normalize_embeddings=True)
            self.connection.execute("INSERT OR REPLACE INTO vectors(document_id,model,embedding) VALUES(?,?,?)",
                                    (doc_id, "all-MiniLM-L6-v2", json.dumps(embedding.tolist())))
        self.connection.commit()

    def set_document_priority(self, url, priority):
        self.connection.execute("UPDATE documents SET priority=? WHERE url=?", (int(priority), url))
        self.connection.commit()

    def set_document_priority_by_id(self, document_id, priority):
        self.connection.execute("UPDATE documents SET priority=? WHERE id=?", (int(priority), document_id))
        self.connection.commit()

    def list_priority_documents(self, limit=30):
        rows = self.connection.execute(
            "SELECT id,url,title,priority,fetched_at FROM documents ORDER BY priority DESC,fetched_at DESC LIMIT ?",
            (max(1, min(int(limit), 100)),),
        ).fetchall()
        return [dict(row) for row in rows]

    def record_search(self, query, category, sort, result_count):
        self.connection.execute("INSERT INTO search_logs(query,category,sort,result_count) VALUES(?,?,?,?)",
                                (query.strip()[:300], category or "all", sort or "relevance", result_count))
        self.connection.commit()

    def record_crawl(self, url, pages, status):
        self.connection.execute("INSERT INTO crawl_logs(url,pages,status) VALUES(?,?,?)",
                                (url or "", max(0, int(pages)), status or "failed"))
        self.connection.commit()

    def save_collection(self, name, query):
        name, query = (name or "").strip()[:80], (query or "").strip()[:300]
        if not name or not query:
            return None
        cursor = self.connection.execute(
            "INSERT INTO collections(name,query) VALUES(?,?) ON CONFLICT(name) DO UPDATE SET query=excluded.query,created_at=CURRENT_TIMESTAMP",
            (name, query),
        )
        self.connection.commit()
        return cursor.lastrowid

    def list_collections(self):
        return [dict(row) for row in self.connection.execute(
            "SELECT id,name,query,created_at FROM collections ORDER BY created_at DESC LIMIT 20").fetchall()]

    def delete_collection(self, collection_id):
        self.connection.execute("DELETE FROM collections WHERE id=?", (collection_id,))
        self.connection.commit()

    def collection_count(self):
        return self.connection.execute("SELECT COUNT(*) FROM collections").fetchone()[0]

    def get_dashboard_stats(self):
        top = self.connection.execute("SELECT query,COUNT(*) AS count FROM search_logs GROUP BY query ORDER BY count DESC,query LIMIT 5").fetchall()
        recent = self.connection.execute("SELECT query,category,result_count,created_at FROM search_logs ORDER BY id DESC LIMIT 6").fetchall()
        categories = self.connection.execute("SELECT category,COUNT(*) AS count FROM search_logs GROUP BY category ORDER BY count DESC LIMIT 5").fetchall()
        return {"total_documents": self.count(),
                "total_searches": self.connection.execute("SELECT COUNT(*) FROM search_logs").fetchone()[0],
                "top_queries": [dict(row) for row in top], "recent_queries": [dict(row) for row in recent],
                "category_breakdown": [dict(row) for row in categories]}

    def get_recent_crawls(self, limit=8):
        rows = self.connection.execute("SELECT url,status,pages,created_at FROM crawl_logs ORDER BY id DESC LIMIT ?",
                                        (max(1, min(int(limit), 100)),)).fetchall()
        return [dict(row) for row in rows]

    def _vector_candidates(self, query, limit):
        if self._encoder is None:
            return []
        rows = self.connection.execute(
            "SELECT d.id,d.url,d.title,d.text,d.category,d.site,d.priority,v.embedding FROM vectors v "
            "JOIN documents d ON d.id=v.document_id WHERE v.model=?", ("all-MiniLM-L6-v2",)).fetchall()
        if not rows:
            return []
        query_vector = self._encoder.encode(query, normalize_embeddings=True)
        scored = [(row, sum(float(a)*float(b) for a,b in zip(query_vector, json.loads(row["embedding"])))) for row in rows]
        return [row for row, _ in sorted(scored, key=lambda pair: pair[1], reverse=True)[:limit]]

    def search(self, query, top_k=10, category="all", sort="relevance"):
        terms = self.tokenize(query)
        if not terms or top_k <= 0:
            return []
        fts_query = " OR ".join('"' + term.replace('"', '""') + '"' for term in terms)
        keyword_rows = self.connection.execute(
            "SELECT d.id,d.url,d.title,d.text,d.category,d.site,d.priority FROM documents_fts f "
            "JOIN documents d ON d.id=f.rowid WHERE documents_fts MATCH ? LIMIT 1000", (fts_query,)).fetchall()
        vector_rows = self._vector_candidates(query, 250)
        candidates = {row["id"]: row for row in keyword_rows}
        candidates.update({row["id"]: row for row in vector_rows})
        if not candidates:
            return []

        docs = list(candidates.values())
        token_docs = [self.tokenize(row["title"] + " " + row["text"]) for row in docs]
        avg_len = sum(map(len, token_docs)) / max(1, len(token_docs))
        df = {}
        for tokens in token_docs:
            for token in set(tokens):
                df[token] = df.get(token, 0) + 1
        scores, k1, b = {}, 1.5, 0.75
        for row, tokens in zip(docs, token_docs):
            counts = {}
            for token in tokens:
                counts[token] = counts.get(token, 0) + 1
            score = 0.0
            for term in set(terms):
                freq = counts.get(term, 0)
                if freq:
                    term_df = df.get(term, 0)
                    idf = math.log(1 + (len(docs) - term_df + 0.5) / (term_df + 0.5))
                    score += idf * freq * (k1 + 1) / (freq + k1 * (1 - b + b * len(tokens) / max(1, avg_len)))
            scores[row["id"]] = score

        orders = {
            "bm25": sorted(scores, key=scores.get, reverse=True),
            "keyword": [row["id"] for row in keyword_rows],
            "vector": [row["id"] for row in vector_rows],
        }
        fused = {}
        for source, ordered_ids in orders.items():
            weight = {"bm25": 1.0, "keyword": 0.7, "vector": 0.8}[source]
            for rank, doc_id in enumerate(ordered_ids, 1):
                fused[doc_id] = fused.get(doc_id, 0.0) + weight / (60 + rank)
        # Editorial boosts are bounded and apply only after a document matches retrieval.
        for row in docs:
            fused[row["id"]] = fused.get(row["id"], 0.0) + max(0, min(100, row["priority"])) * 0.0002

        ordered = sorted(candidates.values(), key=lambda row: fused.get(row["id"], 0), reverse=True)[:max(top_k*5, top_k)]
        if self._cross_encoder is not None and ordered:
            model_scores = self._cross_encoder.predict([(query, (row["title"] + " " + row["text"])[:3000]) for row in ordered])
            ordered = [row for _, row in sorted(zip(model_scores, ordered), key=lambda pair: float(pair[0]), reverse=True)]
        filtered = [row for row in ordered if category == "all" or (row["category"] or "general").lower() == category]
        if not filtered and category != "all":
            return []
        if sort == "latest":
            filtered.sort(key=lambda row: row["id"], reverse=True)
        elif sort == "site":
            filtered.sort(key=lambda row: ((row["site"] or ""), row["title"].lower()))
        else:
            filtered.sort(key=lambda row: fused.get(row["id"], 0), reverse=True)
        results = []
        for row in filtered[:top_k]:
            text = re.sub(r"\s+", " ", row["text"]).strip()
            results.append(SearchResult(row["url"], row["title"], text[:260] + ("…" if len(text)>260 else ""),
                                        float(fused.get(row["id"], 0)), row["category"] or "general", row["site"] or ""))
        return results

    def count(self):
        return self.connection.execute("SELECT COUNT(*) FROM documents").fetchone()[0]

    def close(self):
        self.connection.close()

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        self.close()
