from __future__ import annotations
import datetime
import logging
from typing import List, Optional
import requests
from bs4 import BeautifulSoup
from .base import BaseScraper, Job, get_random_headers, is_valid_job_offer

logger = logging.getLogger("Scraper")

class RemotiveScraper(BaseScraper):
    """Scrapes Remotive.com portal API for remote AI & Data Science jobs."""
    def __init__(self, session: Optional[requests.Session] = None):
        super().__init__(session=session)

    def fetch(self) -> List[Job]:
        jobs = []
        seen_links = set()
        categories = ["data", "software-dev"]
        for cat in categories:
            url = f"https://remotive.com/api/remote-jobs?category={cat}"
            try:
                h = get_random_headers()
                h["Accept"] = "application/json"
                resp = self.session.get(url, headers=h, timeout=(3.5, 10.0))
                if resp.status_code != 200:
                    logger.warning(f"[{self.__class__.__name__}] Unexpected HTTP {resp.status_code} for {resp.url}")
                if resp.status_code == 200:
                    data = resp.json()
                    for item in data.get("jobs", []):
                        title = item.get("title", "")
                        link = item.get("url", "")
                        
                        if not link or link in seen_links or not is_valid_job_offer(link, title):
                            continue
                        seen_links.add(link)

                        company = item.get("company_name", "Remotive Company")
                        location = item.get("candidate_required_location", "Worldwide Remote")
                        desc = BeautifulSoup(item.get("description", ""), "html.parser").get_text(separator=' ', strip=True)
                        pub_date = item.get("publication_date", datetime.date.today().isoformat())[:10]
                        
                        jobs.append(Job(
                            title=title, company=company, location=location,
                            work_mode="Remoto", link=link, description=desc,
                            source="Remotive", pub_date=pub_date
                        ))
            except Exception as e:
                logger.error(f"[Remotive Portal] Error for category {cat}: {e}")
        logger.info(f"[Remotive Portal] Fetched {len(jobs)} jobs across categories.")
        return jobs
