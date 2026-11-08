import time
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET

from search_engine import SearchEngine


@require_GET
def search_page(request):
    query = request.GET.get("q", "").strip()[:300]
    category = request.GET.get("category", "all").lower()
    sort = request.GET.get("sort", "relevance").lower()
    results = []
    elapsed_ms = None
    error = None
    try:
        with SearchEngine() as engine:
            document_count = engine.count()
            if query:
                started = time.perf_counter()
                results = engine.search(query, top_k=10, category=category, sort=sort)
                elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
                engine.record_search(query, category, sort, len(results))
    except (OSError, RuntimeError) as exc:
        document_count, error = 0, str(exc)
    return render(request, "search_ui/search.html", {
        "query": query, "results": results, "document_count": document_count,
        "elapsed_ms": elapsed_ms, "error": error,
        "categories": [("all", "All"), ("tech", "Tech"), ("science", "Science"),
                        ("business", "Business"), ("health", "Health"), ("news", "News")],
        "selected_category": category,
        "selected_sort": sort if sort in {"relevance", "latest", "site"} else "relevance",
    })


@require_GET
def search_api(request):
    query = request.GET.get("q", "").strip()[:300]
    if not query:
        return JsonResponse({"error": "q is required"}, status=400)
    try:
        top_k = max(1, min(50, int(request.GET.get("top_k", "10"))))
    except ValueError:
        return JsonResponse({"error": "top_k must be an integer from 1 to 50"}, status=400)
    category = request.GET.get("category", "all").lower()
    sort = request.GET.get("sort", "relevance").lower()
    with SearchEngine() as engine:
        results = engine.search(query, top_k=top_k, category=category, sort=sort)
        engine.record_search(query, category, sort, len(results))
    return JsonResponse({"query": query, "results": [result.__dict__ for result in results]})


@require_GET
def health(request):
    try:
        with SearchEngine() as engine:
            return JsonResponse({"status": "ok", "documents": engine.count()})
    except (OSError, RuntimeError) as exc:
        return JsonResponse({"status": "error", "detail": str(exc)}, status=503)


@require_GET
def dashboard_api(request):
    with SearchEngine() as engine:
        stats = engine.get_dashboard_stats()
        stats["recent_crawls"] = engine.get_recent_crawls(10)
    return JsonResponse(stats)
