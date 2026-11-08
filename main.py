"""Command-line interface for crawling and searching a small web corpus."""

import argparse
import sys

from crawler import Crawler
from search_engine import SearchEngine


def main():
    parser = argparse.ArgumentParser(description="Crawl websites and search their indexed pages.")
    parser.add_argument("--db", default="supernova.db", help="SQLite index path (default: supernova.db)")
    parser.add_argument("--semantic", action="store_true", help="Use the optional sentence-transformers vector model")
    parser.add_argument("--rerank", action="store_true", help="Use the optional cross-encoder reranker")
    commands = parser.add_subparsers(dest="command", required=True)

    crawl = commands.add_parser("crawl", help="Crawl and index one or more seed URLs")
    crawl.add_argument("urls", nargs="+", help="HTTP(S) URLs to start crawling from")
    crawl.add_argument("--max-pages", type=int, default=100, help="Maximum pages to index (default: 100)")
    crawl.add_argument("--max-depth", type=int, default=2, help="Maximum link depth from each seed (default: 2)")
    crawl.add_argument("--delay", type=float, default=1.0, help="Minimum delay between requests per host in seconds")

    search = commands.add_parser("search", help="Search indexed pages")
    search.add_argument("query", help="Search query")
    search.add_argument("--top-k", type=int, default=10, help="Maximum results to show")

    args = parser.parse_args()
    if args.command == "crawl" and (args.max_pages < 1 or args.max_depth < 0 or args.delay < 0):
        parser.error("--max-pages must be positive; --max-depth and --delay cannot be negative")
    if args.command == "search" and args.top_k < 1:
        parser.error("--top-k must be positive")

    try:
        with SearchEngine(args.db, semantic=args.semantic, rerank=args.rerank) as engine:
            if args.command == "crawl":
                crawler = Crawler(engine, max_pages=args.max_pages, max_depth=args.max_depth, delay=args.delay)
                count = crawler.crawl(args.urls)
                print(f"Indexed {count} page(s) into {args.db}")
            else:
                results = engine.search(args.query, top_k=args.top_k)
                if not results:
                    print("No matches found. Crawl some sites first, or try a different query.")
                    return
                for rank, result in enumerate(results, start=1):
                    print(f"{rank}. {result.title or result.url}\n   {result.url}\n   {result.snippet}\n   score: {result.score:.4f}\n")
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    main()
