from __future__ import annotations
import re
import datetime
import logging
from typing import List, Optional
import requests
from bs4 import BeautifulSoup
from config import config
from .base import BaseScraper, Job, get_random_headers, is_valid_job_offer

logger = logging.getLogger("Scraper")

class EuraxessScraper(BaseScraper):
    """Scrapes Euraxess Portugal portal for AI, ML & Data Science research fellowships & R&D grants."""
    def __init__(self, session: Optional[requests.Session] = None, queries: Optional[List[str]] = None):
        super().__init__(session=session, queries=queries)

    def fetch(self) -> List[Job]:
        jobs = []
        queries = self.queries or config.candidate.search_queries or ["Portugal", "AI", "Data"]
        seen_links = set()
        
        for q in queries:
            for page in range(0, 3):
                url = f"https://euraxess.ec.europa.eu/jobs/search?keywords={q}&page={page}"
                try:
                    resp = self.session.get(url, headers=get_random_headers(), timeout=(3.5, 10.0))
                    if resp.status_code != 200:
                        logger.warning(f"[{self.__class__.__name__}] Unexpected HTTP {resp.status_code} for {resp.url}")
                        break
                    if resp.status_code == 200:
                        soup = BeautifulSoup(resp.text, "html.parser")
                        job_links = soup.find_all("a", href=lambda h: h and re.search(r"/jobs/\d+", h))
                        if not job_links:
                            break
                        page_added = 0
                        for a in job_links:
                            href = a.get("href", "")
                            link = f"https://euraxess.ec.europa.eu{href}" if href.startswith("/") else href
                            if link in seen_links:
                                continue
                            seen_links.add(link)
                            
                            title = a.get_text(separator=' ', strip=True)
                            if not title or not is_valid_job_offer(link, title):
                                continue
                            
                            parent = a.find_parent("div", class_=lambda c: c and any(k in str(c).lower() for k in ["teaser", "card", "view", "item", "row", "result"]))
                            if not parent:
                                parent = a.parent.parent if a.parent else None
                                
                            desc = parent.get_text(separator=" ", strip=True) if parent else title
                            
                            company = "Universidade / Centro de I&D em Portugal"
                            if parent:
                                txt = parent.get_text(separator=" | ", strip=True)
                                parts = txt.split(" | ")
                                if parts:
                                    company = parts[0].strip()
                            
                            jobs.append(Job(
                                title=title, company=company, location="Portugal",
                                work_mode="Presencial / Híbrido", link=link, description=desc,
                                source="Euraxess / Ergas (Bolsas ID)", pub_date=datetime.date.today().isoformat()
                            ))
                            page_added += 1
                        if page_added == 0:
                            break
                except Exception as e:
                    logger.debug(f"[Euraxess Portal] Request note at {url}: {e}")
                    break
        logger.info(f"[Euraxess Portal] Fetched {len(jobs)} research fellowships across pages 1-3.")
        return jobs
