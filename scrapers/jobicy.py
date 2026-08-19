from __future__ import annotations
import datetime
import logging
from typing import List, Optional
import requests
from bs4 import BeautifulSoup
from .base import BaseScraper, Job, get_random_headers, is_valid_job_offer

logger = logging.getLogger("Scraper")

class JobicyScraper(BaseScraper):
    """Scrapes Jobicy public API for remote tech, data & AI jobs."""
    def __init__(self, session: Optional[requests.Session] = None):
        super().__init__(session=session)

    def fetch(self) -> List[Job]:
        jobs = []
        seen_links = set()
        industries = ["data-science", "dev"]
        for ind in industries:
            url = f"https://jobicy.com/api/v2/remote-jobs?count=50&industry={ind}"
            try:
                resp = self.session.get(url, headers=get_random_headers(), timeout=(3.5, 12.0))
                if resp.status_code == 200:
                    data = resp.json()
                    items = data.get("jobs", [])
                    for item in items:
                        title = item.get("jobTitle", "")
                        link = item.get("url", "")
                        if not link or link in seen_links or not is_valid_job_offer(link, title):
                            continue
                        seen_links.add(link)
                        company = item.get("companyName", "Jobicy Company")
                        geo = item.get("jobGeo", "Worldwide Remote")
                        raw_desc = item.get("jobDescription", "") or item.get("jobExcerpt", "")
                        desc = BeautifulSoup(raw_desc, "html.parser").get_text(separator=" ", strip=True)
                        pub_date = item.get("pubDate", datetime.date.today().isoformat())[:10]
                        jobs.append(Job(
                            title=title, company=company, location=f"Remoto ({geo})",
                            work_mode="Remoto", link=link, description=desc,
                            source="Jobicy", pub_date=pub_date
                        ))
            except Exception as e:
                logger.error(f"[Jobicy Portal] Error for industry {ind}: {e}")
        logger.info(f"[Jobicy Portal] Fetched {len(jobs)} jobs.")
        return jobs
