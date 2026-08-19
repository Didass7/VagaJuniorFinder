from __future__ import annotations
import logging
from typing import List, Dict, Optional, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from .base import Job, get_session
from .linkedin import LinkedInScraper
from .itjobs import ITJobsScraper
from .landingjobs import LandingJobsScraper
from .remotive import RemotiveScraper
from .arbeitnow import ArbeitnowScraper
from .remoteok import RemoteOKScraper
from .cargadetrabalhos import CargaDeTrabalhosScraper
from .jobicy import JobicyScraper
from .netempregos import NetEmpregosScraper
from .jobspresso import JobspressoScraper
from .euraxess import EuraxessScraper
from .iefp import IEFPScraper
from .indeed import IndeedScraper

logger = logging.getLogger("Scraper")

class JobIngestionPipeline:
    """Aggregates all structured job portal scrapers concurrently and deduplicates jobs."""
    def __init__(self, itjobs_api_key: str = "", seen_store: Optional[Any] = None, search_queries: Optional[List[str]] = None):
        self.session = get_session(pool_size=45)
        self.itjobs_api_key = itjobs_api_key
        self.seen_store = seen_store
        self.search_queries = search_queries

        is_seen_func = self.seen_store.is_seen_candidate if (self.seen_store and hasattr(self.seen_store, "is_seen_candidate")) else None

        self.linkedin_scraper = LinkedInScraper(session=self.session, is_seen_func=is_seen_func, queries=search_queries)
        self.itjobs_scraper = ITJobsScraper(session=self.session, is_seen_func=is_seen_func)
        self.landing_scraper = LandingJobsScraper(session=self.session)
        self.remotive_scraper = RemotiveScraper(session=self.session)
        self.arbeitnow_scraper = ArbeitnowScraper(session=self.session)
        self.remoteok_scraper = RemoteOKScraper(session=self.session)
        self.carga_scraper = CargaDeTrabalhosScraper(session=self.session, is_seen_func=is_seen_func, queries=search_queries)
        self.jobicy_scraper = JobicyScraper(session=self.session)
        self.netempregos_scraper = NetEmpregosScraper(session=self.session, is_seen_func=is_seen_func, queries=search_queries)
        self.jobspresso_scraper = JobspressoScraper(session=self.session)
        self.euraxess_scraper = EuraxessScraper(session=self.session, queries=search_queries)
        self.iefp_scraper = IEFPScraper(session=self.session, is_seen_func=is_seen_func)
        self.indeed_scraper = IndeedScraper(session=self.session, is_seen_func=is_seen_func, queries=search_queries)

    def run(self) -> List[Job]:
        logger.info("🚀 Starting resilient & concurrent job portal ingestion pipeline...")
        all_jobs: List[Job] = []

        scrapers = [
            ("LinkedIn", self.linkedin_scraper.fetch),
            ("ITJobs", lambda: self.itjobs_scraper.fetch(self.itjobs_api_key)),
            ("Indeed", self.indeed_scraper.fetch),
            ("Carga de Trabalhos", self.carga_scraper.fetch),
            ("Landing.jobs", self.landing_scraper.fetch),
            ("Remotive", self.remotive_scraper.fetch),
            ("Arbeitnow", self.arbeitnow_scraper.fetch),
            ("RemoteOK", self.remoteok_scraper.fetch),
            ("Jobicy", self.jobicy_scraper.fetch),
            ("Net-Empregos", self.netempregos_scraper.fetch),
            ("Jobspresso", self.jobspresso_scraper.fetch),
            ("Euraxess / Ergas", self.euraxess_scraper.fetch),
            ("IEFP Portal", self.iefp_scraper.fetch),
        ]

        # Execute all scrapers in parallel across worker threads
        scraper_results: Dict[str, int] = {}
        failed_scrapers: List[str] = []

        with ThreadPoolExecutor(max_workers=len(scrapers)) as executor:
            future_to_scraper = {executor.submit(func): name for name, func in scrapers}
            for future in as_completed(future_to_scraper):
                scraper_name = future_to_scraper[future]
                try:
                    res = future.result()
                    all_jobs.extend(res)
                    scraper_results[scraper_name] = len(res)
                except Exception as e:
                    logger.error(f"[{scraper_name}] Execution error during concurrent fetch: {e}")
                    scraper_results[scraper_name] = -1
                    failed_scrapers.append(scraper_name)

        # Report per-scraper health
        for name, count in scraper_results.items():
            if count == -1:
                logger.warning(f"⚠️ [{name}] FAILED — threw an exception during fetch.")
            elif count == 0:
                logger.info(f"ℹ️ [{name}] returned 0 jobs for current queries/filters.")

        if failed_scrapers:
            logger.warning(f"🔴 {len(failed_scrapers)}/{len(scrapers)} scrapers failed: {', '.join(failed_scrapers)}")

        # Deduplication using job_id hash
        unique_jobs: Dict[str, Job] = {}
        for j in all_jobs:
            if j.job_id not in unique_jobs:
                unique_jobs[j.job_id] = j

        final_jobs = list(unique_jobs.values())
        logger.info(f"✅ Ingestion complete. Total raw: {len(all_jobs)} | Unique portal job offers: {len(final_jobs)}")
        return final_jobs
