import unittest
from integrations.notion_store import NotionStore
from core.matcher import ScoredJob
from scrapers import Job

class TestNotionStore(unittest.TestCase):
    def test_notion_store_unconfigured(self):
        store = NotionStore(token="", database_id="")
        self.assertFalse(store.is_configured)
        # sync_jobs should return an empty set safely when not configured
        synced_ids = store.sync_jobs([])
        self.assertEqual(synced_ids, set())

    def test_sync_skips_jobs_pending_ai_verdict(self):
        """Jobs without an AI verdict are neither created in Notion nor reported as handled."""
        from unittest.mock import patch
        import datetime
        def make(i, pending):
            job = Job(title=f"Junior SOC Analyst {i}", company=f"C{i}", location="Lisboa", work_mode="Híbrido",
                      link=f"https://example.com/soc{i}", description="SIEM e firewalls " * 10,
                      source="Test", pub_date=datetime.date.today().isoformat())
            return ScoredJob(job=job, score=90.0, matched_skills=[], missing_skills=[],
                             seniority_status="Júnior", ai_pending=pending)
        ok, pending = make(1, False), make(2, True)

        store = NotionStore(token="t", database_id="d")
        with patch.object(store, "get_existing_records", return_value=(set(), set())), \
             patch.object(store, "_create_job_page", return_value=True) as create, \
             patch("time.sleep"):
            synced_ids = store.sync_jobs([ok, pending], threshold=55.0)

        self.assertEqual(synced_ids, {ok.job.job_id})
        create.assert_called_once_with(ok)

    def test_sanitize_select_name(self):
        store = NotionStore()
        clean = store._sanitize_select_name("Presencial, Lisboa")
        self.assertEqual(clean, "Presencial - Lisboa")

if __name__ == "__main__":
    unittest.main()
