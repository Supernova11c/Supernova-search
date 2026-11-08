import tempfile
import unittest
from pathlib import Path

from app import create_app
from search_engine import SearchEngine


class AdminFeatureTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db = str(Path(self.temp_dir.name) / "admin.db")
        self.app = create_app({"TESTING": True, "DATABASE": self.db,
                               "SECRET_KEY": "test-secret", "ADMIN_TOKEN": "secret-token"})
        self.client = self.app.test_client()

    def tearDown(self):
        self.temp_dir.cleanup()

    def login(self):
        page = self.client.get("/admin/login")
        with self.client.session_transaction() as state:
            csrf = state["csrf_token"]
        return self.client.post("/admin/login", data={"token": "secret-token", "csrf_token": csrf},
                                follow_redirects=True)

    def test_admin_requires_authentication(self):
        response = self.client.get("/admin")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login", response.location)

    def test_admin_login_and_panel(self):
        self.login()
        response = self.client.get("/admin")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"URL INJECTION", response.data)

    def test_priority_changes_search_order_for_matching_docs(self):
        with SearchEngine(self.db) as engine:
            engine.add_document("https://example.test/a", "Python notes", "Python search guide.")
            engine.add_document("https://example.test/b", "Python reference", "Python search reference.")
            engine.set_document_priority("https://example.test/b", 100)
            self.assertEqual(engine.search("python search")[0].url, "https://example.test/b")

    def test_dashboard_and_json_api(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["status"], "ok")
        self.assertEqual(self.client.get("/api/search?q=hello").status_code, 200)


if __name__ == "__main__":
    unittest.main()
