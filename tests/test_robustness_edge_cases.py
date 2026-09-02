import unittest
from unittest.mock import patch, MagicMock
from scrapers import Job, clean_job_description, ITJobsScraper
from core.ai_evaluator import AIEvaluator
from integrations.notion_store import NotionStore
from core.config import CandidateProfile
from core.matcher import ScoredJob

class TestRobustnessEdgeCases(unittest.TestCase):
    def setUp(self):
        self.profile = CandidateProfile(name="Test", degree="BSc", iefp_eligible=True, tech_stack=["Python"], languages=["English"])
        
    def test_scraper_network_failure(self):
        """Test how scraper handles network timeout/exceptions."""
        with patch('requests.Session.get') as mock_get:
            mock_get.side_effect = Exception("Connection Timeout")
            scraper = ITJobsScraper()
            jobs = scraper.fetch()
            self.assertEqual(jobs, [])

    def test_ai_evaluator_malformed_json(self):
        """Test AIEvaluator handles malformed JSON correctly."""
        evaluator = AIEvaluator(groq_api_key="mock", gemini_api_key="mock")
        bad_json = "This is just plain text, not JSON."
        batch = [Job("Title", "Company", "Location", "Remote", "http", "Desc", "Src", "Date")]
        results = evaluator._parse_batch_json_response(bad_json, batch)
        self.assertEqual(results, {})
        
    def test_notion_api_rate_limit(self):
        """Test NotionStore handles 429 Too Many Requests by retrying and eventually failing safely."""
        with patch('requests.post') as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 429
            mock_resp.text = "Rate Limited"
            mock_post.return_value = mock_resp
            
            store = NotionStore(token="mock", database_id="mock")
            with patch.object(store, 'get_database_schema', return_value={"Name": {"type": "title"}}):
                job = Job("Title", "Company", "Location", "Remoto", "http", "Desc", "Src", "Date")
                sj = ScoredJob(job=job, score=90, seniority_status="Júnior", matched_skills=["Python"], missing_skills=[])
                # Mock time.sleep to avoid actual waiting during tests
                with patch('time.sleep', return_value=None):
                    success = store._create_job_page(sj)
                    self.assertFalse(success)

    def test_clean_job_description_extreme(self):
        """Test clean_job_description with extremely large nested HTML input."""
        large_input = "<div>" * 500 + "Hello" + "</div>" * 500
        cleaned = clean_job_description(large_input)
        self.assertIn("Hello", cleaned)

if __name__ == '__main__':
    unittest.main()
