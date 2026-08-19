from __future__ import annotations
import datetime
import logging
from typing import List, Optional
import requests
from bs4 import BeautifulSoup
from .base import BaseScraper, Job, get_random_headers, is_valid_job_offer

logger = logging.getLogger("Scraper")

class RemoteOKScraper(BaseScraper):
    """Scrapes RemoteOK portal API for remote data & AI roles."""
    def __init__(self, session: Optional[requests.Session] = None):
        super().__init__(session=session)

    def fetch(self) -> List[Job]:
        jobs = []
        seen_links = set()
        tags = ["data", "python", "ai", "dev"]
        for tag in tags:
            url = f"https://remoteok.com/api?tag={tag}"
            try:
                h = get_random_headers()
                h["Accept"] = "application/json"
                resp = self.session.get(url, headers=h, timeout=(3.5, 10.0))
                if resp.status_code != 200:
                    logger.warning(f"[{self.__class__.__name__}] Unexpected HTTP {resp.status_code} for {resp.url}")
                if resp.status_code == 200:
                    items = resp.json()
                    if isinstance(items, list) and len(items) > 1:
                        for item in items[1:]:
                            if isinstance(item, dict):
                                title = item.get("position", "")
                                link = item.get("url", "") or item.get("apply_url", "")
                                
                                if not link or link in seen_links or not is_valid_job_offer(link, title):
                                    continue
                                seen_links.add(link)

                                company = item.get("company", "RemoteOK Company")
                                location = item.get("location", "Worldwide Remote")
                                desc = BeautifulSoup(item.get("description", ""), "html.parser").get_text(separator=' ', strip=True)
                                pub_date = item.get("date", datetime.date.today().isoformat())[:10]
                                
                                jobs.append(Job(
                                    title=title, company=company, location=location,
                                    work_mode="Remoto", link=link, description=desc,
                                    source="RemoteOK", pub_date=pub_date
                                ))
            except Exception as e:
                logger.error(f"[RemoteOK Portal] Error for tag {tag}: {e}")
        logger.info(f"[RemoteOK Portal] Fetched {len(jobs)} jobs across tags.")
        return jobs
