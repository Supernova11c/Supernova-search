"""Flask web interface for Supernova Search."""

from __future__ import annotations

import os
import threading
import uuid
from urllib.parse import urlparse

from flask import Flask, jsonify, redirect, render_template, request, url_for

from crawler import Crawler
from search_engine import SearchEngine


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SUPERNOVA_SECRET_KEY", "local-development-only"),
        DATABASE=os.environ.get("SUPERNOVA_DB", "supernova.db"),
        MAX_CONTENT_LENGTH=16 * 1024,
    )
    if test_config:
        app.config.update(test_config)

    jobs = {}
    jobs_lock = threading.Lock()
    crawl_lock = threading.Lock()

    def _count_documents():
        try:
            with SearchEngine(app.config["DATABASE"]) as engine:
                return engine.count()
        except (OSError, RuntimeError):
            return 0

    @app.get("/")
    def index():
        query = request.args.get("q", "").strip()[:300]
        category = request.args.get("category", "all").strip().lower()
        sort = request.args.get("sort", "relevance").strip().lower()
        results = []
        error = None
        if query:
            try:
                with SearchEngine(app.config["DATABASE"]) as engine:
                    results = engine.search(query, top_k=10, category=category, sort=sort)
                    document_count = engine.count()
            except (OSError, RuntimeError) as exc:
                document_count = 0
                error = str(exc)
        else:
            try:
                with SearchEngine(app.config["DATABASE"]) as engine:
                    document_count = engine.count()
            except (OSError, RuntimeError):
                document_count = 0

        categories = [
            ("all", "All"),
            ("tech", "Tech"),
            ("science", "Science"),
            ("business", "Business"),
            ("health", "Health"),
            ("news", "News"),
        ]
        return render_template(
            "index.html",
            query=query,
            results=results,
            document_count=document_count,
            error=error,
            categories=categories,
            selected_category=category,
            selected_sort=sort,
        )

    @app.post("/crawl")
    def start_crawl():
        raw_url = request.form.get("url", "").strip()
        normalized = Crawler._normalize(raw_url)
        if not normalized or len(normalized) > 2048:
            return render_template(
                "index.html",
                query="",
                results=[],
                document_count=_count_documents(),
                error="Enter a valid public HTTP or HTTPS website URL.",
                categories=[
                    ("all", "All"),
                    ("tech", "Tech"),
                    ("science", "Science"),
                    ("business", "Business"),
                    ("health", "Health"),
                    ("news", "News"),
                ],
                selected_category="all",
                selected_sort="relevance",
            ), 400

        with jobs_lock:
            if any(job["status"] == "running" for job in jobs.values()):
                return render_template(
                    "index.html",
                    query="",
                    results=[],
                    document_count=_count_documents(),
                    error="A crawl is already running. Please wait for it to finish.",
                    categories=[
                        ("all", "All"),
                        ("tech", "Tech"),
                        ("science", "Science"),
                        ("business", "Business"),
                        ("health", "Health"),
                        ("news", "News"),
                    ],
                    selected_category="all",
                    selected_sort="relevance",
                ), 409
            job_id = uuid.uuid4().hex
            jobs[job_id] = {"status": "running", "url": normalized, "indexed": 0, "error": None}

        thread = threading.Thread(target=run_crawl, args=(job_id, normalized), daemon=True)
        thread.start()
        return redirect(url_for("crawl_status", job_id=job_id))

    def run_crawl(job_id, seed_url):
        try:
            with crawl_lock:
                with SearchEngine(app.config["DATABASE"]) as engine:
                    crawler = Crawler(engine, max_pages=25, max_depth=1, delay=1.0)
                    indexed = crawler.crawl([seed_url])
                    total = engine.count()
            with jobs_lock:
                jobs[job_id].update(status="complete", indexed=indexed, total=total)
        except Exception as exc:
            with jobs_lock:
                jobs[job_id].update(status="failed", error=str(exc))

    @app.get("/crawl/<job_id>")
    def crawl_status(job_id):
        with jobs_lock:
            job = jobs.get(job_id)
            if job:
                job = dict(job)
        if not job:
            return redirect(url_for("index"))
        return render_template(
            "crawl_status.html",
            job=job,
            job_id=job_id,
            document_count=_count_documents(),
        )

    @app.get("/api/crawl/<job_id>")
    def crawl_status_api(job_id):
        with jobs_lock:
            job = jobs.get(job_id)
            if job:
                return jsonify(job)
        return jsonify({"error": "Crawl job not found"}), 404

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host=os.environ.get("SUPERNOVA_HOST", "127.0.0.1"),
            port=int(os.environ.get("SUPERNOVA_PORT", "5000")), debug=False)
