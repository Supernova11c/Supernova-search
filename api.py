"""FastAPI JSON API for Supernova Search's existing local index."""

from __future__ import annotations

import hmac
import os
from typing import Optional
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from pydantic import BaseModel, HttpUrl, Field

from crawler import Crawler
from search_engine import SearchEngine

app = FastAPI(title="Supernova Search API", version="1.0.0", description="Search and index an authorized local web corpus.")
DATABASE = os.environ.get("SUPERNOVA_DB", "supernova.db")
ADMIN_TOKEN = os.environ.get("SUPERNOVA_ADMIN_TOKEN", "")


class InjectRequest(BaseModel):
    url: HttpUrl
    priority: int = Field(default=75, ge=1, le=100)


def verify_admin(authorization: Optional[str] = Header(default=None)):
    if not ADMIN_TOKEN:
        raise HTTPException(status_code=503, detail="Admin API is disabled; configure SUPERNOVA_ADMIN_TOKEN.")
    supplied = authorization or ""
    if not supplied.startswith("Bearer ") or not hmac.compare_digest(supplied[7:], ADMIN_TOKEN):
        raise HTTPException(status_code=401, detail="A valid admin bearer token is required.")


@app.get("/health")
def health():
    with SearchEngine(DATABASE) as engine:
        return {"status": "ok", "documents": engine.count()}


@app.get("/search")
def search(q: str = Query(min_length=1, max_length=300), top_k: int = Query(10, ge=1, le=50),
           category: str = "all", sort: str = "relevance"):
    with SearchEngine(DATABASE) as engine:
        results = engine.search(q, top_k=top_k, category=category, sort=sort)
        engine.record_search(q, category, sort, len(results))
    return {"query": q, "results": [result.__dict__ for result in results]}


@app.get("/dashboard")
def dashboard():
    with SearchEngine(DATABASE) as engine:
        data = engine.get_dashboard_stats()
        data["recent_crawls"] = engine.get_recent_crawls()
        data["collections_count"] = engine.collection_count()
    return data


@app.post("/admin/inject", dependencies=[Depends(verify_admin)])
def inject_url(payload: InjectRequest):
    url = Crawler._normalize(str(payload.url))
    host = urlparse(url or "").hostname
    if not url or not host or not Crawler._public_host(host):
        raise HTTPException(status_code=400, detail="Only publicly routable HTTP(S) URLs are accepted.")
    # Deliberately bounded direct fetch: one URL, no link expansion.
    with SearchEngine(DATABASE) as engine:
        crawler = Crawler(engine, max_pages=1, max_depth=0, delay=1.0)
        indexed = crawler.crawl([url])
        if indexed:
            engine.set_document_priority(url, payload.priority)
        engine.record_crawl(url, indexed, "complete" if indexed else "no_pages")
        return {"url": url, "indexed": indexed, "priority": payload.priority,
                "message": "Indexed if permitted by robots.txt and the site response."}
