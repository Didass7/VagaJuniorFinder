import unittest
from notion_store import NotionStore
from matcher import ScoredJob
from scraper import Job

class TestNotionStore(unittest.TestCase):
    def test_notion_store_unconfigured(self):
        store = NotionStore(token="", database_id="")
        self.assertFalse(store.is_configured)
        # sync_jobs should return 0 safely when not configured
        count = store.sync_jobs([])
        self.assertEqual(count, 0)

    def test_sanitize_select_name(self):
        store = NotionStore()
        clean = store._sanitize_select_name("Presencial, Lisboa")
        self.assertEqual(clean, "Presencial - Lisboa")

if __name__ == "__main__":
    unittest.main()
