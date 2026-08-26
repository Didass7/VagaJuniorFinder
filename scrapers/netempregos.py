from __future__ import annotations
import re
import datetime
import random
import time
import logging
from typing import List, Dict, Set, Optional, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from bs4 import BeautifulSoup
from config import config
from .base import BaseScraper, Job, get_random_headers, is_valid_job_offer, safe_fetch

logger = logging.getLogger("Scraper")

class NetEmpregosScraper(BaseScraper):
    """Scrapes Net-Empregos portal (Portugal's largest job board) for tech, AI, Data & IEFP roles."""
    def __init__(self, session: Optional[requests.Session] = None, is_seen_func: Optional[Any] = None, queries: Optional[List[str]] = None):
        super().__init__(session=session, is_seen_func=is_seen_func, queries=queries)

    def _fetch_query_links(self, q: str, max_pages: int = 5) -> List[Dict]:
        import unicodedata
        from urllib.parse import quote_plus
        
        # Normalize accents for Net-Empregos search engine compatibility (e.g. cibersegurança -> ciberseguranca)
        clean_q = ''.join(c for c in unicodedata.normalize('NFD', q) if unicodedata.category(c) != 'Mn').strip()
        encoded_q = quote_plus(clean_q)
        
        cards = []
        for page in range(1, max_pages + 1):
            try:
                url = f"https://www.net-empregos.com/pesquisa-empregos.asp?chaves={encoded_q}&page={page}"
                status_code, text, content = safe_fetch(url, session=self.session, timeout=12.0)
                if status_code != 200 or not text:
                    break
                soup = BeautifulSoup(text, "html.parser")
                links = soup.find_all("a", href=re.compile(r"/\d+/[^/]+/"))
                if not links:
                    break
                for a in links:
                    raw_href = a.get("href", "")
                    clean_link = f"https://www.net-empregos.com{raw_href}" if not raw_href.startswith("http") else raw_href
                    title = a.get_text(separator=' ', strip=True)
                    if title and len(title) >= 5 and is_valid_job_offer(clean_link, title):
                        cards.append({"title": title, "link": clean_link})
            except Exception as e:
                logger.debug(f"[Net-Empregos Portal] Error querying '{q}' page {page}: {e}")
                break
        return cards

    def _fetch_detail_page(self, card_info: Dict) -> Job:
        title = card_info["title"]
        link = card_info["link"]
        desc = title
        company = "Empresa via Net-Empregos"
        location = "Portugal"
        
        try:
            time.sleep(random.uniform(0.05, 0.15))
            status_code, text, content = safe_fetch(link, session=self.session, timeout=10.0)
            if status_code == 200 and text:
                det_soup = BeautifulSoup(text, "html.parser")
                main_box = (
                    det_soup.find("div", class_="oferta-detalhe") or
                    det_soup.find("div", class_="content") or
                    det_soup.find("div", id="main")
                )
                if main_box:
                    desc = f"{title} - " + main_box.get_text(separator=" ", strip=True)
                else:
                    desc = f"{title} - " + det_soup.get_text(separator=" ", strip=True)
                
                # Parse company name securely from the page title
                # Format is usually: "Title - Company - Ref.ID"
                page_title = det_soup.title.text if det_soup.title else ""
                title_parts = page_title.split(" - ")
                if len(title_parts) >= 3 and not title_parts[1].strip().startswith("Ref."):
                    company = title_parts[1].strip()
                else:
                    for a in det_soup.find_all("a", href=True):
                        if "/emprego-empresa-id/" in a["href"]:
                            txt = a.get_text(separator=' ', strip=True)
                            if len(txt) > 1:
                                company = txt
                                break

                if not company or "empresa via" in company.lower() or company.strip().lower() in ["detalhe da oferta:", "detalhe da oferta", "empresa"]:
                    company = "Empresa Confidencial"
        except Exception:
            pass

        if not company or "empresa via" in company.lower():
            company = "Empresa Confidencial"

        return Job(
            title=title, company=company, location=location,
            work_mode="Presencial / Híbrido", link=link, description=desc,
            source="Net-Empregos", pub_date=datetime.date.today().isoformat()
        )

    def fetch(self) -> List[Job]:
        queries = self.queries or config.candidate.search_queries or ["python", "data", "inteligencia artificial", "machine learning", "estagio iefp"]
        cards_to_fetch = []
        seen_links = set()

        # 1. Fetch query cards concurrently
        with ThreadPoolExecutor(max_workers=min(len(queries), 5)) as executor:
            future_to_q = {executor.submit(self._fetch_query_links, q): q for q in queries}
            for future in as_completed(future_to_q):
                res = future.result()
                for c in res:
                    if c["link"] not in seen_links:
                        seen_links.add(c["link"])
                        cards_to_fetch.append(c)

        # 2. Fetch detail pages concurrently
        jobs = []
        if cards_to_fetch:
            with ThreadPoolExecutor(max_workers=10) as executor:
                future_to_detail = {executor.submit(self._fetch_detail_page, c): c for c in cards_to_fetch}
                for future in as_completed(future_to_detail):
                    try:
                        jobs.append(future.result())
                    except Exception as err:
                        logger.debug(f"[Net-Empregos Portal] Detail fetch error: {err}")

        logger.info(f"[Net-Empregos Portal] Fetched {len(jobs)} jobs with full detail body parsing concurrently.")
        return jobs
