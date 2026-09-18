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

    def test_pipeline_deadline_abandons_hung_scraper(self):
        """Test that a scraper still running at the deadline is abandoned and the other scrapers' jobs are returned."""
        import threading
        import time
        pipeline = JobIngestionPipeline()
        release = threading.Event()

        job_good = Job(
            title="Junior SOC Analyst", company="SecLab", location="Porto",
            work_mode="Híbrido", link="https://example.com/soc-job",
            description="SIEM and firewalls", source="SecPortal", pub_date=datetime.date.today().isoformat()
        )
        pipeline.teamlyzer_scraper.fetch = lambda: release.wait(10) and []
        pipeline.linkedin_scraper.fetch = MagicMock(return_value=[job_good])
        for attr in dir(pipeline):
            if attr.endswith("_scraper") and attr not in ["teamlyzer_scraper", "linkedin_scraper"]:
                getattr(pipeline, attr).fetch = MagicMock(return_value=[])

        try:
            with patch("scrapers.pipeline.SCRAPERS_DEADLINE_SECONDS", 0.5):
                start = time.time()
                jobs = pipeline.run()
                elapsed = time.time() - start
        finally:
            release.set()

        self.assertLess(elapsed, 5.0)
        self.assertEqual([j.title for j in jobs], ["Junior SOC Analyst"])

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

    def test_main_leaves_fetch_failed_and_ai_pending_jobs_unseen(self):
        """Jobs whose details failed to load or that got no AI verdict must stay unseen so the next run retries them."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
            temp_cache = tf.name

        try:
            def make_job(name, **kwargs):
                return Job(
                    title=f"Junior {name}", company=name, location="Lisboa", work_mode="Remoto",
                    link=f"https://example.com/{name}", description="Descrição " * 20,
                    source="Test", pub_date=datetime.date.today().isoformat(), **kwargs
                )

            job_synced = make_job("Synced")
            job_disqualified = make_job("Disqualified")
            job_fetch_failed = make_job("FetchFailed", fetch_failed=True)
            job_pending = make_job("Pending")

            scored_synced = ScoredJob(job=job_synced, score=85.0, matched_skills=[], missing_skills=[], seniority_status="Júnior")
            scored_pending = ScoredJob(job=job_pending, score=85.0, matched_skills=[], missing_skills=[], seniority_status="Avaliação IA Pendente", ai_pending=True)

            with patch("main.config") as mock_config, patch("sys.stdout"):
                mock_config.cache_file = temp_cache
                mock_config.enable_notion_sync = True
                mock_config.promising_match_threshold = 55.0

                pipeline = MagicMock()
                pipeline.run.return_value = [job_synced, job_disqualified, job_fetch_failed, job_pending]
                matcher = MagicMock()
                matcher.process_jobs.return_value = [scored_synced, scored_pending]
                notion = MagicMock()
                notion.sync_jobs.return_value = {job_synced.job_id}
                notion.last_synced_count = 1

                store = SeenStore(filepath=temp_cache)
                main.run_pipeline(pipeline=pipeline, seen_store=store, matcher=matcher, notion_store=notion)

            self.assertTrue(store.is_seen(job_synced.job_id))
            self.assertTrue(store.is_seen(job_disqualified.job_id))
            self.assertFalse(store.is_seen(job_fetch_failed.job_id))
            self.assertFalse(store.is_seen(job_pending.job_id))
            store.conn.close()
        finally:
            for path in (temp_cache, temp_cache[:-5] + ".db"):
                if os.path.exists(path):
                    os.remove(path)

    @staticmethod
    def _write_profiles(tmpdir, profiles):
        """Writes {name: top-level extra fields} as profile JSON files and returns their paths."""
        import json
        paths = []
        for name, extra in profiles.items():
            path = os.path.join(tmpdir, f"{name}.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump({**extra, "candidate": {"name": name}}, f)
            paths.append(path)
        return paths

    def test_run_all_skips_paused_profiles(self):
        """Profiles with "enabled": false are kept on disk but skipped by run_all.py."""
        with tempfile.TemporaryDirectory() as tmpdir:
            paths = self._write_profiles(tmpdir, {"active": {}, "paused": {"enabled": False}, "explicit": {"enabled": True}})
            with patch("glob.glob", return_value=paths), \
                 patch("sys.stdout"), \
                 patch("subprocess.run", return_value=MagicMock(returncode=0)) as mock_subproc:
                run_all.main()

        ran = [c.kwargs["env"]["ACTIVE_PROFILE"] for c in mock_subproc.call_args_list]
        self.assertEqual(ran, ["active", "explicit"])

    def test_default_profile_skips_paused_profiles(self):
        """Without ACTIVE_PROFILE, the default is the first enabled profile, not a paused one."""
        from core import config as config_module
        with tempfile.TemporaryDirectory() as tmpdir:
            paths = self._write_profiles(tmpdir, {"a_paused": {"enabled": False}, "b_active": {}})
            config_module._first_profile_on_disk.cache_clear()
            try:
                with patch.object(config_module.glob, "glob", return_value=paths), \
                     patch.dict(os.environ, {}, clear=False):
                    os.environ.pop("ACTIVE_PROFILE", None)
                    self.assertEqual(config_module.default_profile_name(), "b_active")
            finally:
                config_module._first_profile_on_disk.cache_clear()

    def test_cache_file_and_notion_sync_env_overrides(self):
        """CACHE_FILE sets the cache path and ENABLE_NOTION_SYNC toggles the Notion sync."""
        from core.config import load_config
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = os.path.join(tmpdir, "custom_cache.json")
            with patch.dict(os.environ, {"CACHE_FILE": cache, "ENABLE_NOTION_SYNC": "false"}):
                cfg = load_config("rafael")
            self.assertEqual(cfg.cache_file, cache)
            self.assertFalse(cfg.enable_notion_sync)

            with patch.dict(os.environ, {"ENABLE_NOTION_SYNC": "true"}):
                os.environ.pop("CACHE_FILE", None)
                cfg = load_config("rafael")
            self.assertEqual(cfg.cache_file, os.path.join("data", "jobs_cache_rafael.json"))
            self.assertTrue(cfg.enable_notion_sync)

    def test_main_logging_goes_to_stdout(self):
        """Importing scrapers must not configure logging, so main.py's stdout handler is the one in effect."""
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        code = (
            "import logging, sys\n"
            "import scrapers.base\n"
            "print(len(logging.getLogger().handlers))\n"
            "import main\n"
            "h = logging.getLogger().handlers\n"
            "print(len(h), h[0].stream is sys.stdout)\n"
        )
        out = subprocess.run([sys.executable, "-c", code], cwd=project_root, capture_output=True, text=True, timeout=120)
        self.assertEqual(out.stdout.split(), ["0", "1", "True"], out.stderr)

    def test_run_all_success_and_failure_exit_codes(self):
        """Test that run_all.py exits with 0 on all success, and sys.exit(1) on profile failure."""
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        paths = self._write_profiles(tmpdir.name, {"alice": {}, "bob": {}})
        with patch("glob.glob", return_value=paths), \
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

            # Case 3: One profile exceeds the per-profile timeout -> killed, next profile still runs, exit 1
            with patch("subprocess.run", side_effect=[
                subprocess.TimeoutExpired(["python", "main.py"], run_all.PROFILE_TIMEOUT_SECONDS),
                MagicMock(returncode=0)
            ]) as mock_subproc:
                with self.assertRaises(SystemExit) as cm:
                    run_all.main()
                self.assertEqual(cm.exception.code, 1)
                self.assertEqual(mock_subproc.call_count, 2)
                self.assertEqual(mock_subproc.call_args.kwargs["timeout"], run_all.PROFILE_TIMEOUT_SECONDS)


if __name__ == "__main__":
    unittest.main()

