"""Flask web interface and admin tools for Supernova Search."""

from __future__ import annotations

import hmac
import os
import secrets
import threading
import uuid
from functools import wraps
from urllib.parse import urlparse

from flask import Flask, flash, jsonify, redirect, render_template, request, session, url_for

from crawler import Crawler
from search_engine import SearchEngine

CATEGORIES = [
    ("all", "All"), ("tech", "Tech"), ("science", "Science"),
    ("business", "Business"), ("health", "Health"), ("news", "News"),
]


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SUPERNOVA_SECRET_KEY", "local-development-only"),
        ADMIN_TOKEN=os.environ.get("SUPERNOVA_ADMIN_TOKEN", ""),
        DATABASE=os.environ.get("SUPERNOVA_DB", "supernova.db"),
        MAX_CONTENT_LENGTH=16 * 1024,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("SUPERNOVA_COOKIE_SECURE", "0") == "1",
    )
    if test_config:
        app.config.update(test_config)

    jobs = {}
    jobs_lock = threading.Lock()
    crawl_lock = threading.Lock()

    def csrf_token():
        if "csrf_token" not in session:
            session["csrf_token"] = secrets.token_urlsafe(32)
        return session["csrf_token"]

    app.jinja_env.globals["csrf_token"] = csrf_token

    def require_csrf():
        expected = session.get("csrf_token", "")
        provided = request.form.get("csrf_token", "")
        return bool(expected and provided and hmac.compare_digest(expected, provided))

    def admin_required(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not app.config["ADMIN_TOKEN"]:
                return "Admin access is disabled. Configure SUPERNOVA_ADMIN_TOKEN.", 503
            if not session.get("is_admin"):
                return redirect(url_for("admin_login", next=request.path))
            return view(*args, **kwargs)
        return wrapped

    def count_documents():
        try:
            with SearchEngine(app.config["DATABASE"]) as engine:
                return engine.count()
        except (OSError, RuntimeError):
            return 0

    def run_crawl(job_id, seed_url, priority=0):
        try:
            with crawl_lock:
                with SearchEngine(app.config["DATABASE"]) as engine:
                    crawler = Crawler(engine, max_pages=25 if priority == 0 else 1,
                                      max_depth=1 if priority == 0 else 0, delay=1.0)
                    indexed = crawler.crawl([seed_url])
                    if priority and indexed:
                        engine.set_document_priority(seed_url, priority)
                    total = engine.count()
                    engine.record_crawl(seed_url, indexed, "complete" if indexed else "no_pages")
            with jobs_lock:
                jobs[job_id].update(status="complete", indexed=indexed, total=total)
        except Exception as exc:  # background job errors are shown to the operator
            try:
                with SearchEngine(app.config["DATABASE"]) as engine:
                    engine.record_crawl(seed_url, 0, "failed")
            except Exception:
                pass
            with jobs_lock:
                jobs[job_id].update(status="failed", error=str(exc))

    @app.get("/")
    def index():
        query = request.args.get("q", "").strip()[:300]
        category = request.args.get("category", "all").strip().lower()
        if category not in {key for key, _ in CATEGORIES}:
            category = "all"
        sort = request.args.get("sort", "relevance").strip().lower()
        if sort not in {"relevance", "latest", "site"}:
            sort = "relevance"
        results, error = [], None
        document_count = count_documents()
        if query:
            try:
                with SearchEngine(app.config["DATABASE"]) as engine:
                    results = engine.search(query, top_k=10, category=category, sort=sort)
                    engine.record_search(query, category, sort, len(results))
                    document_count = engine.count()
            except (OSError, RuntimeError) as exc:
                error, document_count = str(exc), 0
        return render_template("index.html", query=query, results=results,
                               document_count=document_count, error=error,
                               categories=CATEGORIES, selected_category=category,
                               selected_sort=sort)

    @app.get("/dashboard")
    def dashboard():
        stats = {"total_documents": 0, "total_searches": 0, "top_queries": [],
                 "recent_queries": [], "recent_crawls": [], "collections_count": 0,
                 "category_breakdown": []}
        try:
            with SearchEngine(app.config["DATABASE"]) as engine:
                stats = engine.get_dashboard_stats()
                stats["collections_count"] = engine.collection_count()
                stats["recent_crawls"] = engine.get_recent_crawls(limit=8)
        except (OSError, RuntimeError):
            pass
        with jobs_lock:
            recent_jobs = list(jobs.values())[-6:][::-1]
        return render_template("dashboard.html", **stats, recent_jobs=recent_jobs)

    @app.get("/collections")
    def collections_page():
        with SearchEngine(app.config["DATABASE"]) as engine:
            collections, document_count = engine.list_collections(), engine.count()
        return render_template("collections.html", collections=collections,
                               document_count=document_count)

    @app.post("/collections")
    def save_collection():
        if not require_csrf():
            return "Invalid CSRF token", 400
        name, query = request.form.get("name", "").strip(), request.form.get("query", "").strip()
        if name and query:
            with SearchEngine(app.config["DATABASE"]) as engine:
                engine.save_collection(name, query)
        return redirect(url_for("collections_page"))

    @app.post("/collections/<int:collection_id>/delete")
    def delete_collection(collection_id):
        if not require_csrf():
            return "Invalid CSRF token", 400
        with SearchEngine(app.config["DATABASE"]) as engine:
            engine.delete_collection(collection_id)
        return redirect(url_for("collections_page"))

    @app.post("/crawl")
    def start_crawl():
        normalized = Crawler._normalize(request.form.get("url", "").strip())
        if not normalized or len(normalized) > 2048:
            flash("Enter a valid HTTP or HTTPS website URL.", "error")
            return redirect(url_for("index"))
        with jobs_lock:
            if any(job["status"] == "running" for job in jobs.values()):
                flash("A crawl is already running. Please wait for it to finish.", "error")
                return redirect(url_for("index")), 409
            job_id = uuid.uuid4().hex
            jobs[job_id] = {"status": "running", "url": normalized, "indexed": 0}
        threading.Thread(target=run_crawl, args=(job_id, normalized), daemon=True).start()
        return redirect(url_for("crawl_status", job_id=job_id))

    @app.get("/crawl/<job_id>")
    def crawl_status(job_id):
        with jobs_lock:
            job = dict(jobs[job_id]) if job_id in jobs else None
        if not job:
            return redirect(url_for("index"))
        return render_template("crawl_status.html", job=job, job_id=job_id,
                               document_count=count_documents())

    @app.get("/api/crawl/<job_id>")
    def crawl_status_api(job_id):
        with jobs_lock:
            job = jobs.get(job_id)
            return (jsonify(dict(job)), 200) if job else (jsonify({"error": "Crawl job not found"}), 404)

    @app.route("/admin/login", methods=["GET", "POST"])
    def admin_login():
        if not app.config["ADMIN_TOKEN"]:
            return render_template("admin_login.html", error="Admin panel is disabled. Set SUPERNOVA_ADMIN_TOKEN."), 503
        error = None
        if request.method == "POST":
            if not require_csrf():
                error = "Security token expired; reload and try again."
            elif hmac.compare_digest(request.form.get("token", ""), app.config["ADMIN_TOKEN"]):
                session.clear()
                session["is_admin"] = True
                session["csrf_token"] = secrets.token_urlsafe(32)
                next_url = request.args.get("next", "")
                # Restrict post-login redirects to local paths.
                if next_url.startswith("/") and not next_url.startswith("//"):
                    return redirect(next_url)
                return redirect(url_for("admin_panel"))
            else:
                error = "That admin token was not accepted."
        return render_template("admin_login.html", error=error)

    @app.post("/admin/logout")
    @admin_required
    def admin_logout():
        if not require_csrf():
            return "Invalid CSRF token", 400
        session.clear()
        return redirect(url_for("index"))

    @app.get("/admin")
    @admin_required
    def admin_panel():
        with SearchEngine(app.config["DATABASE"]) as engine:
            stats = engine.get_dashboard_stats()
            documents = engine.list_priority_documents(limit=30)
            crawls = engine.get_recent_crawls(limit=10)
        with jobs_lock:
            recent_jobs = list(jobs.values())[-10:][::-1]
        return render_template("admin.html", stats=stats, documents=documents,
                               crawls=crawls, recent_jobs=recent_jobs,
                               document_count=count_documents())

    @app.post("/admin/inject")
    @admin_required
    def admin_inject_url():
        if not require_csrf():
            return "Invalid CSRF token", 400
        normalized = Crawler._normalize(request.form.get("url", "").strip())
        try:
            priority = int(request.form.get("priority", "75"))
        except ValueError:
            priority = -1
        if not normalized or len(normalized) > 2048 or not 1 <= priority <= 100:
            flash("Provide a valid HTTP(S) URL and a priority from 1 to 100.", "error")
            return redirect(url_for("admin_panel"))
        host = urlparse(normalized).hostname
        # Reject local/private destinations before scheduling any request.
        if not host or not Crawler._public_host(host):
            flash("Only publicly routable hosts can be submitted.", "error")
            return redirect(url_for("admin_panel"))
        with jobs_lock:
            if any(job["status"] == "running" for job in jobs.values()):
                flash("A crawl is already running. Wait before injecting another URL.", "error")
                return redirect(url_for("admin_panel")), 409
            job_id = uuid.uuid4().hex
            jobs[job_id] = {"status": "running", "url": normalized, "indexed": 0,
                            "priority": priority, "source": "admin"}
        threading.Thread(target=run_crawl, args=(job_id, normalized, priority), daemon=True).start()
        flash("URL queued. It will be indexed only if the site permits crawling.", "success")
        return redirect(url_for("admin_panel"))

    @app.post("/admin/priority/<int:document_id>")
    @admin_required
    def update_priority(document_id):
        if not require_csrf():
            return "Invalid CSRF token", 400
        try:
            priority = int(request.form.get("priority", "0"))
        except ValueError:
            priority = -1
        if not 0 <= priority <= 100:
            flash("Priority must be between 0 and 100.", "error")
        else:
            with SearchEngine(app.config["DATABASE"]) as engine:
                engine.set_document_priority_by_id(document_id, priority)
            flash("Ranking priority updated.", "success")
        return redirect(url_for("admin_panel"))

    @app.get("/api/search")
    def api_search():
        query = request.args.get("q", "").strip()[:300]
        if not query:
            return jsonify({"query": "", "results": []})
        try:
            top_k = max(1, min(50, int(request.args.get("top_k", "10"))))
        except ValueError:
            return jsonify({"error": "top_k must be an integer"}), 400
        category = request.args.get("category", "all").lower()
        sort = request.args.get("sort", "relevance").lower()
        with SearchEngine(app.config["DATABASE"]) as engine:
            results = engine.search(query, top_k=top_k, category=category, sort=sort)
        return jsonify({"query": query, "results": [result.__dict__ for result in results]})

    @app.get("/api/collections")
    def api_collections():
        with SearchEngine(app.config["DATABASE"]) as engine:
            return jsonify({"collections": engine.list_collections()})

    @app.get("/api/dashboard")
    def dashboard_api():
        with SearchEngine(app.config["DATABASE"]) as engine:
            stats = engine.get_dashboard_stats()
            stats["collections_count"] = engine.collection_count()
            stats["recent_crawls"] = engine.get_recent_crawls(limit=8)
        return jsonify(stats)

    @app.get("/api/health")
    def health_check():
        return jsonify({"status": "ok", "documents": count_documents()})

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host=os.environ.get("SUPERNOVA_HOST", "127.0.0.1"),
            port=int(os.environ.get("SUPERNOVA_PORT", "5000")), debug=False)
