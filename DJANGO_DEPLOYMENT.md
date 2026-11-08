# Django deployment (alternative to the existing Flask UI)
# Copy .env.example to .env and set strong secrets before starting.

```bash
docker compose -f docker-compose.django.yml up --build
```

Open <http://127.0.0.1:8000/> for search and <http://127.0.0.1:8000/admin/> for the Django admin. Create a staff superuser after startup:

```bash
docker compose -f docker-compose.django.yml exec django python manage.py createsuperuser
```

In Django Admin, add a **URL injection** with a public HTTP(S) URL and priority 1–100. The durable worker processes pending submissions, obeys robots.txt, stays on the submitted host, and applies the priority as an editorial ranking boost. Change priority later from the admin list. Ranking still requires documents to match the query; editorial boosts never make unrelated pages appear.

The queue runs as a separate worker so web requests do not block on network crawling. Search API: `GET /api/search/?q=python&top_k=10`; health API: `GET /api/health/`. Set `DJANGO_ALLOWED_HOSTS` for the deployment hostname, use a unique strong `SUPERNOVA_SECRET_KEY`, configure HTTPS behind a reverse proxy, and change `SESSION_COOKIE_SECURE`/`CSRF_COOKIE_SECURE` in settings before exposing the admin publicly.

Django and the existing search index share the configured SQLite file. This is a practical single-machine deployment, not a distributed queue or multi-node search architecture.
