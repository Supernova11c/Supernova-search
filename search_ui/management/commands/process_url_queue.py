from django.core.management.base import BaseCommand
from django.db import close_old_connections
from django.utils import timezone

from crawler import Crawler
from search_engine import SearchEngine
from search_ui.models import URLSubmission


class Command(BaseCommand):
    help = "Process queued URL injections, respecting robots.txt and crawler bounds."

    def add_arguments(self, parser):
        parser.add_argument("--poll", type=float, default=0, help="Poll continuously at this many seconds; 0 processes once.")
        parser.add_argument("--max-pages", type=int, default=1, help="Pages per injected URL (default: 1).")

    def handle(self, *args, **options):
        poll = max(0, options["poll"])
        max_pages = max(1, min(25, options["max_pages"]))
        while True:
            close_old_connections()
            item = URLSubmission.objects.filter(status="pending").order_by("-priority", "created_at").first()
            if item is None:
                if not poll:
                    self.stdout.write("No pending URL injections.")
                    return
                time.sleep(poll)
                continue

            # Claim the item before doing network I/O; one queue worker is intended.
            URLSubmission.objects.filter(pk=item.pk, status="pending").update(status="running", last_error="")
            item.refresh_from_db()
            if item.status != "running":
                continue

            try:
                normalized = Crawler._normalize(item.url)
                host = __import__("urllib.parse", fromlist=["urlparse"]).urlparse(normalized or "").hostname
                if not normalized or not host or not Crawler._public_host(host):
                    raise ValueError("Only public HTTP(S) destinations can be crawled.")
                with SearchEngine() as engine:
                    crawler = Crawler(engine, max_pages=max_pages, max_depth=0, delay=1.0)
                    indexed = crawler.crawl([normalized])
                    if indexed:
                        engine.set_document_priority(normalized, item.priority)
                    status = "complete" if indexed else "no_pages"
                    engine.record_crawl(normalized, indexed, status)
                URLSubmission.objects.filter(pk=item.pk).update(status=status, indexed_pages=indexed,
                                                                updated_at=timezone.now(), last_error="")
                self.stdout.write(f"{status}: {normalized} ({indexed} page(s), priority {item.priority})")
            except Exception as exc:
                URLSubmission.objects.filter(pk=item.pk).update(status="failed", last_error=str(exc)[:500],
                                                                updated_at=timezone.now())
                self.stderr.write(f"failed: {item.url}: {exc}")
            close_old_connections()

            if not poll:
                return

import time
