from __future__ import annotations
import datetime
import logging
from typing import List, Dict, Set, Optional, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from bs4 import BeautifulSoup
from config import config
from .base import BaseScraper, Job, get_random_headers, is_valid_job_offer

logger = logging.getLogger("Scraper")

class CargaDeTrabalhosScraper(BaseScraper):
    """Scrapes Carga de Trabalhos portal for Portuguese tech & AI jobs."""
    def __init__(self, session: Optional[requests.Session] = None, is_seen_func: Optional[Any] = None, queries: Optional[List[str]] = None):
        super().__init__(session=session, is_seen_func=is_seen_func, queries=queries)

    def _fetch_query_articles(self, q: str, max_pages: int = 3) -> List[Dict]:
        cards = []
        for page in range(1, max_pages + 1):
            try:
                url = f"https://cargadetrabalhos.pt/page/{page}/?s={q}" if page > 1 else f"https://cargadetrabalhos.pt/?s={q}"
                resp = self.session.get(url, headers=get_random_headers(), timeout=(3.5, 12.0))
                if resp.status_code != 200:
                    break
                soup = BeautifulSoup(resp.text, "html.parser")
                articles = soup.find_all("article")
                if not articles:
                    break
                page_added = 0
                for art in articles:
                    a_tag = art.find("a")
                    if not a_tag:
                        continue
                    link = a_tag.get("href", "").split("?")[0].rstrip("/")
                    if "/ofertas/" not in link:
                        continue
                    
                    title = a_tag.get_text(separator=' ', strip=True)
                    if not title or not is_valid_job_offer(link, title):
                        continue
                    
                    if self.is_seen_func and self.is_seen_func(title, "Empresa via Carga de Trabalhos"):
                        continue

                    text = art.get_text(separator=" ", strip=True)
                    cards.append({"title": title, "link": link, "summary_text": text})
                    page_added += 1
                if page_added == 0:
                    break
            except Exception as e:
                logger.error(f"[Carga de Trabalhos Portal] Error querying '{q}' page {page}: {e}")
                break
        return cards

    def _fetch_detail_page(self, card_info: Dict) -> Job:
        title = card_info["title"]
        link = card_info["link"]
        text = card_info["summary_text"]

        try:
            det_resp = self.session.get(link, headers=get_random_headers(), timeout=(3.5, 12.0))
            if det_resp.status_code != 200:
                logger.warning(f"[{self.__class__.__name__}] Unexpected HTTP {det_resp.status_code} for {det_resp.url}")
            if det_resp.status_code == 200:
                det_soup = BeautifulSoup(det_resp.text, "html.parser")
                is_closed = bool(det_soup.find(class_=lambda c: c and ("closed-job" in c or "job-closed" in c)))
                if is_closed:
                    text = f"{title} - Oferta Expirada"
                else:
                    main_div = det_soup.find("div", class_="noo-main") or det_soup.find("div", class_="entry-content")
                    if main_div:
                        text = f"{title} - " + main_div.get_text(separator=" ", strip=True)
        except Exception:
            pass

        return Job(
            title=title, company="Empresa via Carga de Trabalhos", location="Portugal",
            work_mode="Presencial / Híbrido", link=link, description=text,
            source="Carga de Trabalhos", pub_date=datetime.date.today().isoformat()
        )

    def fetch(self) -> List[Job]:
        queries = self.queries or config.candidate.search_queries or ["data", "python", "inteligencia", "machine learning", "ai"]
        cards_to_fetch = []
        seen_links = set()

        # 1. Query search pages concurrently
        with ThreadPoolExecutor(max_workers=min(len(queries), 5)) as executor:
            future_to_q = {executor.submit(self._fetch_query_articles, q): q for q in queries}
            for future in as_completed(future_to_q):
                res = future.result()
                for c in res:
                    if c["link"] not in seen_links:
                        seen_links.add(c["link"])
                        cards_to_fetch.append(c)

        # 2. Fetch detail pages concurrently
        jobs = []
        if cards_to_fetch:
            with ThreadPoolExecutor(max_workers=8) as executor:
                future_to_detail = {executor.submit(self._fetch_detail_page, c): c for c in cards_to_fetch}
                for future in as_completed(future_to_detail):
                    try:
                        jobs.append(future.result())
                    except Exception as err:
                        logger.debug(f"[Carga de Trabalhos Portal] Detail fetch error: {err}")

        logger.info(f"[Carga de Trabalhos Portal] Fetched {len(jobs)} jobs concurrently.")
        return jobs
