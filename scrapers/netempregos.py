from __future__ import annotations
import re
import datetime
import random
import time
import logging
from typing import List, Dict, Set, Optional, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
import warnings
import requests
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
from core.config import config
from .base import BaseScraper, Job, get_random_headers, is_valid_job_offer, safe_fetch

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

logger = logging.getLogger("Scraper")

def _parse_html(html_text: str) -> BeautifulSoup:
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
        return BeautifulSoup(html_text, "html.parser")

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
                soup = _parse_html(text)
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
                det_soup = _parse_html(text)
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
            import logging
            logging.warning('Exception swallowed')

        if not company or "empresa via" in company.lower():
            company = "Empresa Confidencial"

        return Job(
            title=title, company=company, location=location,
            work_mode="Presencial / Híbrido", link=link, description=desc,
            source="Net-Empregos", pub_date=datetime.date.today().isoformat()
        )

    def fetch(self) -> List[Job]:
        queries = self.queries or config.candidate.search_queries or ["python", "data", "inteligencia artificial", "machine learning", "estagio iefp"]
        jobs: List[Job] = []
        seen_links: Set[str] = set()

        # Strategy 1: Official Net-Empregos RSS Feed (1,000 live offers, unblockable on cloud IPs)
        import feedparser
        rss_urls = [
            "https://www.net-empregos.com/rss.asp",
            "https://www.net-empregos.com/feed.asp",
            "https://www.net-empregos.com/rss/"
        ]
        
        cards_to_fetch: List[Dict[str, str]] = []

        for r_url in rss_urls:
            try:
                status_code, text, content = safe_fetch(r_url, session=self.session, timeout=10.0)
                if status_code == 200 and (content or text):
                    fp = feedparser.parse(content or text)
                    if fp and fp.entries:
                        for entry in fp.entries:
                            title = entry.get("title", "").strip()
                            link = entry.get("link", "").strip()
                            if "?" in link:
                                link = link.split("?")[0]
                            if not link or link in seen_links or not is_valid_job_offer(link, title):
                                continue
                            seen_links.add(link)

                            raw_summary = entry.get("summary", "") or entry.get("description", "")
                            soup = _parse_html(raw_summary)
                            desc = soup.get_text(separator=" ", strip=True)

                            # Quick tech relevance check on title + RSS summary
                            text_lower = f"{title} {desc}".lower()
                            is_tech_candidate = any(k in text_lower for k in [
                                "python", "data", "informática", "informatica", "software", "programador",
                                "developer", "engenh", "redes", "cloud", "devops", "ciber", "segurança",
                                "seguranca", "iefp", "estágio", "estagio", "ai", "ia", "machine learning",
                                "web", "php", "laravel", "sql", "bi", "it ", "ti ", "sistemas", "analista"
                            ])
                            if not is_tech_candidate:
                                continue

                            cards_to_fetch.append({"title": title, "link": link})
                        if cards_to_fetch:
                            break
            except Exception as e:
                logger.debug(f"[Net-Empregos RSS] Error with {r_url}: {e}")

        # Strategy 2: Targeted Query search to enrich with candidate-specific queries
        with ThreadPoolExecutor(max_workers=min(len(queries), 5)) as executor:
            future_to_q = {executor.submit(self._fetch_query_links, q, 3): q for q in queries}
            for future in as_completed(future_to_q):
                res = future.result()
                for c in res:
                    if c["link"] not in seen_links:
                        seen_links.add(c["link"])
                        cards_to_fetch.append(c)

        # Step 3: Fetch full detail pages concurrently for all tech candidate offers (retrieves full requirements & real company)
        if cards_to_fetch:
            with ThreadPoolExecutor(max_workers=10) as executor:
                future_to_detail = {executor.submit(self._fetch_detail_page, c): c for c in cards_to_fetch}
                for future in as_completed(future_to_detail):
                    try:
                        job = future.result()
                        if job:
                            jobs.append(job)
                    except Exception as err:
                        logger.debug(f"[Net-Empregos Portal] Detail fetch error: {err}")

        logger.info(f"[Net-Empregos Portal] Fetched {len(jobs)} jobs with full detail body parsing concurrently.")
        return jobs
