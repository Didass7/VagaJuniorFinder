from __future__ import annotations
import re
import logging
import datetime
from typing import List, Optional, Any
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


class TeamlyzerScraper(BaseScraper):
    """
    Scraper for Teamlyzer Jobs (pt.teamlyzer.com/companies/jobs).
    Extracts tech, developer, AI, DevOps, data, and junior IT positions in Portugal
    along with salary indications, regime (Remote/Hybrid), and tech tags.
    """
    def __init__(
        self,
        session: Optional[requests.Session] = None,
        is_seen_func: Optional[Any] = None,
        queries: Optional[List[str]] = None,
    ):
        super().__init__(session=session, is_seen_func=is_seen_func, queries=queries)

    def _parse_page(self, html: str) -> List[Job]:
        jobs: List[Job] = []
        if not html:
            return jobs

        soup = BeautifulSoup(html, "html.parser")
        cards = soup.select(".jobcard, .jobboard-ad")
        
        for c in cards:
            try:
                # 1. Title & Link
                title_elem = c.select_one(".jobcard__title-row a") or c.select_one(".jobcard__title-row")
                if not title_elem:
                    continue

                raw_title = title_elem.get_text(separator=" ", strip=True)
                # Capitalize words nicely
                title = " ".join([word.capitalize() if not word.isupper() else word for word in raw_title.split()])

                link = ""
                if title_elem and title_elem.name == "a":
                    link = title_elem.get("href", "")
                if not link:
                    for a in c.find_all("a", href=True):
                        h = a.get("href", "")
                        if "/companies/get-job/" in h or "/jobs/" in h or "/companies/" in h:
                            link = h
                            break

                if link and link.startswith("/"):
                    link = f"https://pt.teamlyzer.com{link}"

                if not title or not link or not is_valid_job_offer(link, title):
                    continue

                # 2. Company Name
                metas = [m.get_text(separator=" ", strip=True) for m in c.select(".jobcard__meta")]
                company_raw = metas[0] if metas else "Empresa no Teamlyzer"
                # Strip review counts and ratings e.g. "Smart Consulting 3.1 210 Reviews" -> "Smart Consulting"
                company = re.sub(r"\d+(\.\d+)?\s*\d*\s*Reviews?.*$", "", company_raw, flags=re.IGNORECASE).strip()
                if not company:
                    company = company_raw

                if self.is_seen_func and self.is_seen_func(title, company, link=link):
                    continue

                # 3. Location, Regime & Salary metadata
                loc_meta = " ".join(metas[1:]) if len(metas) > 1 else "Portugal"
                location = "Portugal"
                if "Lisboa" in loc_meta:
                    location = "Lisboa, Portugal"
                elif "Porto" in loc_meta:
                    location = "Porto, Portugal"
                elif "Coimbra" in loc_meta:
                    location = "Coimbra, Portugal"
                elif "Braga" in loc_meta:
                    location = "Braga, Portugal"
                elif "Castelo Branco" in loc_meta:
                    location = "Castelo Branco, Portugal"
                elif "Leiria" in loc_meta:
                    location = "Leiria, Portugal"
                elif "Aveiro" in loc_meta:
                    location = "Aveiro, Portugal"

                # 4. Work Mode Inference
                text_l = f"{title} {loc_meta}".lower()
                work_mode = "Presencial / Híbrido"
                if any(w in text_l for w in ["full remote", "remoto", "remote"]):
                    work_mode = "Remoto"
                elif any(w in text_l for w in ["híbrido", "hibrido", "hybrid"]):
                    work_mode = "Híbrido"
                elif any(w in text_l for w in ["presencial", "onsite", "on-site"]):
                    work_mode = "Presencial"

                # 5. Tags & Rich Description
                tags = [t.get_text(strip=True) for t in c.select(".jobcard__tags span, .jobcard__tags a") if t.get_text(strip=True)]
                tags_str = ", ".join(tags) if tags else ""

                desc_parts = [f"{title} na {company}."]
                if loc_meta:
                    desc_parts.append(f"Detalhes: {loc_meta}.")
                if tags_str:
                    desc_parts.append(f"Tecnologias & Competências: {tags_str}.")
                clean_desc = clean_job_description(" ".join(desc_parts))

                jobs.append(Job(
                    title=title,
                    company=company,
                    location=location,
                    work_mode=work_mode,
                    link=link,
                    description=clean_desc,
                    source="Teamlyzer",
                    pub_date=datetime.date.today().isoformat()
                ))
            except Exception as item_err:
                logger.debug(f"[Teamlyzer Scraper] Error parsing card: {item_err}")

        return jobs

    def fetch(self) -> List[Job]:
        """Fetches jobs from Teamlyzer across initial listing pages."""
        all_jobs: List[Job] = []
        seen_links = set()

        headers = get_random_headers()
        headers.update({
            "Accept-Language": "pt-PT,pt;q=0.9,en-US;q=0.8,en;q=0.7",
            "Referer": "https://pt.teamlyzer.com/",
        })

        # Crawl first 2 pages of active jobs
        pages_to_crawl = [
            "https://pt.teamlyzer.com/companies/jobs",
            "https://pt.teamlyzer.com/companies/jobs?page=2",
        ]

        for url in pages_to_crawl:
            try:
                resp = self.session.get(url, headers=headers, timeout=(3.5, 10.0))
                if resp.status_code == 200:
                    parsed = self._parse_page(resp.text)
                    for j in parsed:
                        if j.link not in seen_links:
                            seen_links.add(j.link)
                            all_jobs.append(j)
                else:
                    logger.debug(f"[Teamlyzer Scraper] HTTP {resp.status_code} for {url}")
            except Exception as e:
                logger.debug(f"[Teamlyzer Scraper] Error crawling {url}: {e}")

        logger.info(f"[Teamlyzer] Fetched {len(all_jobs)} jobs.")
        return all_jobs
