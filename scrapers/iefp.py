from __future__ import annotations
import datetime
import random
import time
import logging
from typing import List, Optional, Any
import requests
from bs4 import BeautifulSoup
from .base import BaseScraper, Job, get_random_headers

logger = logging.getLogger("Scraper")

class IEFPScraper(BaseScraper):
    """Scrapes official IEFP Portugal portal (iefponline.iefp.pt) for job offers and internships via POST-based search."""
    BASE_URL = "https://iefponline.iefp.pt"
    SEARCH_URL = f"{BASE_URL}/IEFP/pesquisas/search.do"

    def __init__(self, session: Optional[requests.Session] = None, is_seen_func: Optional[Any] = None):
        super().__init__(session=session, is_seen_func=is_seen_func)

    def _search_offers(self, query: str, tipo: str, seen_links: set) -> List[Job]:
        """Performs a POST search on the IEFP portal and parses the results."""
        jobs = []
        try:
            # Step 1: GET to establish session cookies (JSESSIONID required)
            self.session.get(f"{self.SEARCH_URL}?cat=ofertaEmprego", headers=get_random_headers(), timeout=(4.0, 15.0))
            time.sleep(random.uniform(0.5, 1.5))

            # Step 2: POST search form
            data = {
                "text": query,
                "tipo": tipo,
                "origem": "Portugal",
                "origem_option": "Portugal",
                "currentPage": "1",
                "resultsPerPage": "25",
                "pos": "0",
                "len": "3",
            }
            resp = self.session.post(self.SEARCH_URL, headers=get_random_headers(), data=data, timeout=(4.0, 15.0))
            if resp.status_code != 200:
                return jobs

            soup = BeautifulSoup(resp.text, "html.parser")
            result_div = soup.find("div", class_="results-table")
            if not result_div:
                return jobs

            # Parse offer blocks by finding detail links
            detail_links = result_div.find_all("a", href=lambda h: h and "detalheOfertas" in h)
            for a_tag in detail_links:
                href = a_tag.get("href", "")
                link = f"{self.BASE_URL}/{href}" if not href.startswith("http") else href
                if link in seen_links:
                    continue

                # Walk up to find the parent card and extract title
                parent = a_tag.find_parent("div", class_=lambda c: c and "row" in str(c))
                if not parent:
                    parent = a_tag.parent
                
                # Title is in the first <h5> or <strong> before the detail link
                title_elem = parent.find("h5") if parent else None
                title = title_elem.get_text(strip=True) if title_elem else ""
                if not title:
                    # Fallback: extract from card text (pattern: "ID: XXXXX\nTITLE\n")
                    card_text = parent.get_text(separator="\n", strip=True) if parent else ""
                    lines = [l.strip() for l in card_text.split("\n") if l.strip() and not l.strip().startswith("ID:") and "Oferta" not in l]
                    title = lines[0] if lines else ""

                if not title or len(title) < 4:
                    continue

                if self.is_seen_func and self.is_seen_func(title, "Empresa via IEFP"):
                    continue

                seen_links.add(link)

                # Extract location from card
                location = "Portugal"
                loc_elem = parent.find("strong") if parent else None
                if loc_elem:
                    loc_candidates = parent.find_all("strong")
                    for lc in loc_candidates:
                        lc_text = lc.get_text(strip=True)
                        if lc_text != title and len(lc_text) > 2:
                            location = lc_text.split("|")[0].strip()
                            break

                card_text = parent.get_text(separator=" ", strip=True) if parent else title
                is_estagio = tipo == "OFERTA_ESTAGIO" or "estágio" in card_text.lower() or "estagio" in card_text.lower()
                source_label = "IEFP Portal (Estágio)" if is_estagio else "IEFP Portal (Emprego)"
                desc = f"{title} - Oferta IEFP. {card_text}"

                jobs.append(Job(
                    title=title, company="Empresa via IEFP", location=location,
                    work_mode="Presencial / Híbrido", link=link, description=desc,
                    source=source_label, pub_date=datetime.date.today().isoformat()
                ))
        except Exception as e:
            logger.debug(f"[IEFP Portal] Error searching '{query}' (tipo={tipo}): {e}")
        return jobs

    def fetch(self) -> List[Job]:
        jobs = []
        seen_links: set = set()
        queries = ["informatica", "data", "python", "inteligencia artificial", "estagio programador", "software"]

        for q in queries:
            for tipo in ["OFERTA_EMPREGO", "OFERTA_ESTAGIO"]:
                found = self._search_offers(q, tipo, seen_links)
                jobs.extend(found)
                time.sleep(random.uniform(1.0, 2.0))

        logger.info(f"[IEFP Portal] Fetched {len(jobs)} job/internship offers.")
        return jobs
