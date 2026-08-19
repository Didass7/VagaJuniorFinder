from __future__ import annotations
import datetime
import logging
from typing import List, Optional
import requests
from bs4 import BeautifulSoup
from .base import BaseScraper, Job, get_random_headers, is_valid_job_offer

logger = logging.getLogger("Scraper")

class JobspressoScraper(BaseScraper):
    """Scrapes Jobspresso HTML job listings for remote tech & data jobs."""
    def __init__(self, session: Optional[requests.Session] = None):
        super().__init__(session=session)

    def fetch(self) -> List[Job]:
        jobs = []
        seen_links = set()
        pages = ["https://jobspresso.co/", "https://jobspresso.co/page/2/", "https://jobspresso.co/page/3/"]
        
        for url in pages:
            try:
                resp = self.session.get(url, headers=get_random_headers(), timeout=(3.5, 10.0))
                if resp.status_code != 200:
                    logger.warning(f"[{self.__class__.__name__}] Unexpected HTTP {resp.status_code} for {resp.url}")
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, "html.parser")
                    job_a_tags = soup.find_all("a", href=lambda h: h and "/job/" in h)
                    for a in job_a_tags:
                        href = a.get("href", "")
                        if not href or href in seen_links or href.endswith("/job/") or href == "https://jobspresso.co/job/":
                            continue
                        
                        parent = a.find_parent("li") or a.find_parent("div", class_=lambda c: c and "job" in str(c).lower())
                        if not parent:
                            continue
                        
                        seen_links.add(href)
                        title_elem = parent.find(class_=lambda c: c and "title" in str(c).lower()) or a
                        title = title_elem.get_text(separator=' ', strip=True) if title_elem else a.get_text(separator=' ', strip=True)
                        if not title:
                            continue
                        
                        if not is_valid_job_offer(href, title):
                            continue
                        
                        comp_elem = parent.find(class_=lambda c: c and "company" in str(c).lower())
                        company = comp_elem.get_text(separator=' ', strip=True) if comp_elem else "Jobspresso Company"
                        
                        loc_elem = parent.find(class_=lambda c: c and "location" in str(c).lower())
                        location = loc_elem.get_text(separator=' ', strip=True) if loc_elem else "Worldwide Remote"
                        
                        desc = parent.get_text(separator=" ", strip=True)
                        
                        jobs.append(Job(
                            title=title, company=company, location=location,
                            work_mode="Remoto", link=href, description=desc,
                            source="Jobspresso", pub_date=datetime.date.today().isoformat()
                        ))
            except Exception as e:
                logger.error(f"[Jobspresso Portal] Error at {url}: {e}")
        logger.info(f"[Jobspresso Portal] Fetched {len(jobs)} jobs across pages 1-3.")
        return jobs
