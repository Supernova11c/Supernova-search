import tempfile
import time
import unittest
from pathlib import Path

from app import create_app
from search_engine import SearchEngine


class WebAppTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = str(Path(self.temp_dir.name) / "web.db")
        with SearchEngine(self.database) as engine:
            engine.add_document("https://example.test/guide", "A Python guide", "Python search is useful for finding relevant documents.")
        self.app = create_app({"TESTING": True, "DATABASE": self.database})
        self.client = self.app.test_client()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_homepage_renders_brand_and_index_count(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"supernova", response.data)
        self.assertIn(b"1 pages indexed", response.data)

    def test_search_displays_result(self):
        response = self.client.get("/?q=python+search")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"A Python guide", response.data)
        self.assertIn(b"example.test/guide", response.data)

    def test_search_query_is_escaped(self):
        response = self.client.get("/?q=%3Cscript%3Ealert(1)%3C/script%3E")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(b"<script>alert(1)</script>", response.data)

    def test_invalid_crawl_url_is_rejected(self):
        response = self.client.post("/crawl", data={"url": "file:///etc/passwd"})
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"valid public HTTP or HTTPS", response.data)


if __name__ == "__main__":
    unittest.main()
