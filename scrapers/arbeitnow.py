from __future__ import annotations
import datetime
import logging
from typing import List, Optional
import requests
from bs4 import BeautifulSoup
from .base import BaseScraper, Job, get_random_headers, is_valid_job_offer

logger = logging.getLogger("Scraper")

class ArbeitnowScraper(BaseScraper):
    """Scrapes Arbeitnow European job portal API."""
    def __init__(self, session: Optional[requests.Session] = None):
        super().__init__(session=session)

    def fetch(self) -> List[Job]:
        jobs = []
        for page in range(1, 4):
            url = f"https://www.arbeitnow.com/api/job-board-api?page={page}"
            try:
                h = get_random_headers()
                h["Accept"] = "application/json"
                resp = self.session.get(url, headers=h, timeout=(3.5, 10.0))
                if resp.status_code != 200:
                    logger.warning(f"[{self.__class__.__name__}] Unexpected HTTP {resp.status_code} for {resp.url}")
                    break
                if resp.status_code == 200:
                    data = resp.json()
                    items = data.get("data", [])
                    if not items:
                        break
                    for item in items:
                        title = item.get("title", "")
                        link = item.get("url", "")
                        
                        if not is_valid_job_offer(link, title):
                            continue

                        company = item.get("company_name", "Arbeitnow Company")
                        location = item.get("location", "Europe / Remote")
                        remote = item.get("remote", False)
                        work_mode = "Remoto" if remote else "Presencial / Híbrido"
                        desc = BeautifulSoup(item.get("description", ""), "html.parser").get_text(separator=' ', strip=True)
                        pub_date = datetime.date.fromtimestamp(item.get("created_at", int(datetime.datetime.now().timestamp()))).isoformat()
                        
                        jobs.append(Job(
                            title=title, company=company, location=location,
                            work_mode=work_mode, link=link, description=desc,
                            source="Arbeitnow", pub_date=pub_date
                        ))
            except Exception as e:
                logger.error(f"[Arbeitnow Portal] Error at page {page}: {e}")
                break
        logger.info(f"[Arbeitnow Portal] Fetched {len(jobs)} jobs across pages 1-3.")
        return jobs
