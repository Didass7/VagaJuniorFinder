import unittest
import tempfile
import os
import sys
import datetime
import subprocess
from unittest.mock import patch, MagicMock

from scrapers.base import Job
from scrapers.pipeline import JobIngestionPipeline
from core.seen_store import SeenStore
from core.matcher import ScoredJob
import main
import run_all


class TestPipelineAndCLI(unittest.TestCase):
    """Unit tests validating JobIngestionPipeline error isolation/timeouts and CLI entry points."""

    def test_pipeline_error_isolation(self):
        """Test that an unhandled exception in one scraper does not abort other scrapers in the pipeline."""
        pipeline = JobIngestionPipeline()
        
        # Scraper 1 returns 1 valid job
        job_good = Job(
            title="Junior Data Scientist", company="GoodTech", location="Lisboa",
            work_mode="Remoto", link="https://example.com/good1",
            description="Python and SQL", source="GoodPortal", pub_date=datetime.date.today().isoformat()
        )
        pipeline.linkedin_scraper.fetch = MagicMock(return_value=[job_good])

        # Scraper 2 throws an exception
        pipeline.indeed_scraper.fetch = MagicMock(side_effect=ConnectionResetError("Simulated Network Drop"))

        # Scraper 3 throws another error
        pipeline.landing_scraper.fetch = MagicMock(side_effect=ValueError("Simulated Malformed Response"))

        # Mock remaining scrapers to return empty lists
        for attr in dir(pipeline):
            if attr.endswith("_scraper") and attr not in ["linkedin_scraper", "indeed_scraper", "landing_scraper"]:
                getattr(pipeline, attr).fetch = MagicMock(return_value=[])

        jobs = pipeline.run()
        
        # Pipeline must succeed, isolate errors, and return jobs from healthy scraper
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].title, "Junior Data Scientist")
        self.assertEqual(jobs[0].company, "GoodTech")

    def test_pipeline_timeout_handling(self):
        """Test that a hung scraper timing out is caught by the 90s timeout handler and does not crash the pipeline."""
        pipeline = JobIngestionPipeline()
        
        job_good = Job(
            title="Junior AI Engineer", company="AILab", location="Porto",
            work_mode="Híbrido", link="https://example.com/ai-job",
            description="PyTorch and LLMs", source="AIPortal", pub_date=datetime.date.today().isoformat()
        )
        
        # Scraper 1 times out
        def mock_hung_fetch():
            raise TimeoutError("Simulated 90s Scraper Hang")
        
        pipeline.teamlyzer_scraper.fetch = mock_hung_fetch
        pipeline.linkedin_scraper.fetch = MagicMock(return_value=[job_good])

        # Mock remaining scrapers to return empty lists
        for attr in dir(pipeline):
            if attr.endswith("_scraper") and attr not in ["teamlyzer_scraper", "linkedin_scraper"]:
                getattr(pipeline, attr).fetch = MagicMock(return_value=[])

        jobs = pipeline.run()
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].title, "Junior AI Engineer")

    def test_pipeline_internal_deduplication(self):
        """Test that multiple scrapers returning identical jobs are deduplicated down to 1 unique offer."""
        pipeline = JobIngestionPipeline()
        job_duplicate_1 = Job(
            title="Junior Python Dev", company="NovaTech", location="Lisboa",
            work_mode="Remoto", link="https://example.com/dup",
            description="Python development", source="PortalA", pub_date=datetime.date.today().isoformat()
        )
        job_duplicate_2 = Job(
            title="Junior Python Dev", company="NovaTech", location="Lisboa",
            work_mode="Remoto", link="https://example.com/dup",
            description="Python development", source="PortalB", pub_date=datetime.date.today().isoformat()
        )

        pipeline.linkedin_scraper.fetch = MagicMock(return_value=[job_duplicate_1])
        pipeline.itjobs_scraper.fetch = MagicMock(return_value=[job_duplicate_2])

        for attr in dir(pipeline):
            if attr.endswith("_scraper") and attr not in ["linkedin_scraper", "itjobs_scraper"]:
                getattr(pipeline, attr).fetch = MagicMock(return_value=[])

        jobs = pipeline.run()
        self.assertEqual(len(jobs), 1)

    def test_main_dry_run_skips_notion_and_seen_save(self):
        """Test that main.py --dry-run scores jobs but skips Notion sync and does not mark jobs in SeenStore."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
            temp_cache = tf.name

        try:
            test_job = Job(
                title="Junior Machine Learning Specialist", company="TestAI",
                location="Lisboa", work_mode="Remoto", link="https://example.com/test-ml",
                description="Python, PyTorch, Scikit-learn with over 100 characters of description for testing.",
                source="Test", pub_date=datetime.date.today().isoformat()
            )

            scored = ScoredJob(
                job=test_job, score=85.0,
                matched_skills=["python", "pytorch"],
                missing_skills=[],
                seniority_status="Júnior",
                match_reason="Great match",
                ai_reasoning="Qualified junior"
            )

            with patch("main.config") as mock_config, \
                 patch("main.JobIngestionPipeline") as mock_pipeline_cls, \
                 patch("main.JobMatcher") as mock_matcher_cls, \
                 patch("main.NotionStore") as mock_notion_cls:

                mock_config.cache_file = temp_cache
                mock_config.candidate.name = "Test Candidate"
                mock_config.candidate.email = "test@example.com"
                mock_config.candidate.search_queries = ["AI"]
                mock_config.itjobs_api_key = ""
                mock_config.enable_notion_sync = True

                mock_pipeline = MagicMock()
                mock_pipeline.run.return_value = [test_job]
                mock_pipeline_cls.return_value = mock_pipeline

                mock_matcher = MagicMock()
                mock_matcher.process_jobs.return_value = [scored]
                mock_matcher_cls.return_value = mock_matcher

                # Execute dry-run with silenced stdout
                with patch("sys.stdout"):
                    main.run_pipeline(dry_run=True)

                # Notion sync must NOT be instantiated or called
                mock_notion_cls.assert_not_called()

                # SeenStore must NOT have recorded the job
                store = SeenStore(filepath=temp_cache)
                self.assertFalse(store.is_seen(test_job.job_id))
                self.assertEqual(store.count, 0)
        finally:
            if os.path.exists(temp_cache):
                os.remove(temp_cache)

    def test_run_all_success_and_failure_exit_codes(self):
        """Test that run_all.py exits with 0 on all success, and sys.exit(1) on profile failure."""
        with patch("glob.glob", return_value=["profiles/diogo.json", "profiles/rafael.json"]), \
             patch("os.path.exists", return_value=True), \
             patch("sys.stdout"):

            # Case 1: All profiles succeed
            with patch("subprocess.run") as mock_subproc:
                mock_subproc.return_value = MagicMock(returncode=0)
                # Should finish without calling sys.exit(1)
                run_all.main()
                self.assertEqual(mock_subproc.call_count, 2)

            # Case 2: One profile fails -> must call sys.exit(1)
            with patch("subprocess.run", side_effect=[
                MagicMock(returncode=0),
                subprocess.CalledProcessError(1, ["python", "main.py"])
            ]):
                with self.assertRaises(SystemExit) as cm:
                    run_all.main()
                self.assertEqual(cm.exception.code, 1)


if __name__ == "__main__":
    unittest.main()

