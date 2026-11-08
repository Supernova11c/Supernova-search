import tempfile
import unittest
from pathlib import Path

from search_engine import SearchEngine


class SearchEngineTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db = Path(self.temp_dir.name) / "test.db"
        self.engine = SearchEngine(self.db)
        self.engine.add_document("https://example.test/python", "Python guide", "Python is a programming language for building applications.")
        self.engine.add_document("https://example.test/gardens", "Garden guide", "Gardens grow flowers and vegetables in healthy soil.")

    def tearDown(self):
        self.engine.close()
        self.temp_dir.cleanup()

    def test_keyword_search_ranks_matching_document(self):
        results = self.engine.search("python programming")
        self.assertTrue(results)
        self.assertEqual(results[0].url, "https://example.test/python")

    def test_no_match_returns_empty(self):
        self.assertEqual(self.engine.search("astronautical zebras"), [])

    def test_upsert_does_not_duplicate_document(self):
        self.engine.add_document("https://example.test/python", "Updated", "Python indexing and search.")
        self.assertEqual(self.engine.count(), 2)
        self.assertEqual(self.engine.search("indexing")[0].title, "Updated")


if __name__ == "__main__":
    unittest.main()
