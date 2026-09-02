from __future__ import annotations
import re
import json
import logging
import datetime
from typing import List, Optional, Any
from urllib.parse import quote_plus
import requests
from bs4 import BeautifulSoup
from core.config import config
from .base import (
    BaseScraper,
    Job,
    get_random_headers,
    clean_job_description,
    is_valid_job_offer,
)

logger = logging.getLogger("Scraper")


class SapoScraper(BaseScraper):
    """
    Scraper for Sapo Emprego (emprego.sapo.pt) in Portugal.
    Extracts IT and tech jobs from the structured JSON embedded in the Vue search results component.
    """
    def __init__(
        self,
        session: Optional[requests.Session] = None,
        is_seen_func: Optional[Any] = None,
        queries: Optional[List[str]] = None,
    ):
        super().__init__(session=session, is_seen_func=is_seen_func, queries=queries)

    def _parse_sapo_page(self, html: str) -> List[Job]:
        jobs: List[Job] = []
        if not html:
            return jobs

        soup = BeautifulSoup(html, "html.parser")
        
        # 1. Primary Strategy: Vue component with native JSON offers
        comp = soup.find("search-results-component")
        raw_offers = None
        if comp:
            raw_offers = comp.get(":offers") or comp.get("offers")

        if raw_offers:
            try:
                offers_data = json.loads(raw_offers)
                if isinstance(offers_data, list):
                    for item in offers_data:
                        offer_id = item.get("id", "")
                        title = item.get("offer_name", "")
                        if not offer_id or not title:
                            continue

                        link = f"https://emprego.sapo.pt/offer/{offer_id}"
                        if not is_valid_job_offer(link, title):
                            continue

                        company = (
                            item.get("company_name")
                            or item.get("company_slug", "").replace("-", " ").title()
                            or (item.get("company") if isinstance(item.get("company"), str) else "")
                            or "Empresa no Sapo Emprego"
                        )

                        if self.is_seen_func and self.is_seen_func(title, company, link=link):
                            continue

                        district = item.get("job_district") or item.get("location") or "Portugal"
                        country = item.get("job_country") or "Portugal"
                        location = f"{district}, {country}" if district and district != country else (district or "Portugal")

                        pitch = item.get("offer_pitch", "")
                        raw_desc = item.get("job_description", "")
                        full_desc = f"{pitch}\n{raw_desc}" if pitch else raw_desc
                        clean_desc = clean_job_description(full_desc or title)

                        # Work mode inference
                        text_l = f"{title} {location} {pitch} {raw_desc}".lower()
                        work_mode = "Presencial / Híbrido"
                        if any(w in text_l for w in ["remoto", "remote", "teletrabalho", "100% remote"]):
                            work_mode = "Remoto"
                        elif any(w in text_l for w in ["híbrido", "hibrido", "hybrid"]):
                            work_mode = "Híbrido"
                        elif any(w in text_l for w in ["presencial", "on-site", "onsite"]):
                            work_mode = "Presencial"

                        pub_date = item.get("publication_date", datetime.date.today().isoformat())[:10]

                        jobs.append(Job(
                            title=title,
                            company=company,
                            location=location,
                            work_mode=work_mode,
                            link=link,
                            description=clean_desc,
                            source="Sapo Emprego",
                            pub_date=pub_date
                        ))
                    return jobs
            except Exception as e:
                logger.debug(f"[Sapo Scraper] JSON parse error: {e}")

        # 2. Fallback Strategy: HTML scraping
        for a_elem in soup.find_all("a", href=re.compile(r"/offer/[a-zA-Z0-9\-]+")):
            try:
                href = a_elem.get("href", "")
                link = f"https://emprego.sapo.pt{href}" if href.startswith("/") else href
                title = a_elem.get_text(separator=" ", strip=True)
                if not title or len(title) < 5 or not is_valid_job_offer(link, title):
                    continue

                jobs.append(Job(
                    title=title,
                    company="Empresa no Sapo Emprego",
                    location="Portugal",
                    work_mode="Presencial / Híbrido",
                    link=link,
                    description=title,
                    source="Sapo Emprego",
                    pub_date=datetime.date.today().isoformat()
                ))
            except Exception:
                import logging
                logging.warning('Exception swallowed')

        return jobs

    def fetch(self) -> List[Job]:
        """Fetches jobs from Sapo Emprego across general IT category and candidate queries."""
        all_jobs: List[Job] = []
        seen_links = set()

        headers = get_random_headers()
        headers.update({
            "Accept-Language": "pt-PT,pt;q=0.9,en-US;q=0.8,en;q=0.7",
            "Referer": "https://emprego.sapo.pt/",
        })

        # Base IT search url
        urls_to_crawl = [
            "https://emprego.sapo.pt/offers?categoria=informatica-ti",
        ]

        queries = (
            self.queries
            or config.candidate.search_queries
            or ["python", "data", "inteligencia artificial", "machine learning", "estagio iefp"]
        )

        for q in queries[:6]:
            urls_to_crawl.append(f"https://emprego.sapo.pt/offers?q={quote_plus(q)}")

        for url in urls_to_crawl:
            try:
                resp = self.session.get(url, headers=headers, timeout=(3.5, 10.0))
                if resp.status_code == 200:
                    parsed = self._parse_sapo_page(resp.text)
                    for j in parsed:
                        if j.link not in seen_links:
                            seen_links.add(j.link)
                            all_jobs.append(j)
                else:
                    logger.debug(f"[Sapo Scraper] HTTP {resp.status_code} for {url}")
            except Exception as e:
                logger.debug(f"[Sapo Scraper] Error crawling {url}: {e}")

        logger.info(f"[Sapo Emprego] Fetched {len(all_jobs)} jobs.")
        return all_jobs
