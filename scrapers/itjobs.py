from __future__ import annotations
import re
import datetime
import logging
from typing import List, Dict, Set, Optional, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from bs4 import BeautifulSoup
from .base import BaseScraper, Job, get_random_headers, is_valid_job_offer

logger = logging.getLogger("Scraper")

class ITJobsScraper(BaseScraper):
    """Scrapes ITJobs.pt portal for Portugal IT, AI & Data Science jobs with full detail body parsing."""
    def __init__(self, session: Optional[requests.Session] = None, is_seen_func: Optional[Any] = None, api_key: str = ""):
        super().__init__(session=session, is_seen_func=is_seen_func)
        self.api_key = api_key

    def _fetch_search_url_cards(self, url: str) -> List[Dict]:
        cards = []
        try:
            resp = self.session.get(url, headers=get_random_headers(), timeout=(3.5, 10.0))
            if resp.status_code != 200 and resp.status_code != 404:
                logger.warning(f"[{self.__class__.__name__}] Unexpected HTTP {resp.status_code} for {resp.url}")
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                title_anchors = soup.find_all("a", class_="title")
                for a in title_anchors:
                    href = a.get("href", "")
                    if href and "/oferta/" in href:
                        full_link = f"https://www.itjobs.pt{href}" if href.startswith("/") else href
                        title = a.get_text(separator=' ', strip=True)
                        if is_valid_job_offer(full_link, title):
                            parent = a.find_parent("div", class_="info") or a.find_parent("div")
                            company = "Empresa via ITJobs"
                            location = "Portugal"
                            if parent:
                                company_elem = parent.find("a", class_="company") or parent.find("span", class_="company")
                                if company_elem:
                                    company = company_elem.get_text(separator=' ', strip=True)
                                location_elem = parent.find("span", class_="location") or parent.find("div", class_="location")
                                if location_elem:
                                    location = location_elem.get_text(separator=' ', strip=True)
                            if self.is_seen_func and self.is_seen_func(title, company):
                                continue
                            cards.append({
                                "title": title, "link": full_link,
                                "company": company, "location": location
                            })
        except Exception as e:
            logger.error(f"[ITJobs.pt Portal] Error querying '{url}': {e}")
        return cards

    def _fetch_detail_body(self, card_info: Dict) -> Job:
        full_link = card_info["link"]
        title = card_info["title"]
        company = card_info["company"]
        location = card_info["location"]
        
        desc = title
        try:
            detail_resp = self.session.get(full_link, headers=get_random_headers(), timeout=(3.5, 12.0))
            if detail_resp.status_code != 200:
                logger.warning(f"[{self.__class__.__name__}] Unexpected HTTP {detail_resp.status_code} for {detail_resp.url}")
            if detail_resp.status_code == 200:
                detail_soup = BeautifulSoup(detail_resp.text, "html.parser")
                text_blocks = [elem.get_text(separator=' ', strip=True) for elem in detail_soup.find_all(["p", "li"])]
                desc = f"{title} " + " ".join(text_blocks)

                # Extract real company name from ITJobs title or link
                if detail_soup.title:
                    parts = [p.strip() for p in detail_soup.title.text.split(' - ')]
                    if len(parts) >= 3 and parts[-1] == 'ITJobs':
                        c_val = parts[-2]
                        if len(c_val) > 1 and c_val.lower() not in ['itjobs', 'emprego']:
                            company = c_val

                if not company or "empresa via" in company.lower() or company == "Empresa Confidencial":
                    for a in detail_soup.find_all("a", href=True):
                        if "/empresa/" in a["href"] or "/company/" in a["href"]:
                            txt = a.get_text(separator=' ', strip=True)
                            if len(txt) > 2 and txt.lower() not in ["empresas", "empresa", "login"]:
                                company = txt
                                break

        except Exception as detail_err:
            logger.debug(f"Could not fetch offer detail page for {full_link}: {detail_err}")

        if not company or "empresa via" in company.lower():
            company = "Empresa Confidencial"

        return Job(
            title=title, company=company, location=location,
            work_mode="Presencial / Híbrido", link=full_link, description=desc,
            source="ITJobs.pt", pub_date=datetime.date.today().isoformat()
        )

    def fetch(self) -> List[Job]:
        jobs = []
        api_key = self.api_key
        if api_key:
            try:
                for page in range(1, 4):
                    url = f"https://api.itjobs.pt/2/job/search.json?api_key={api_key}&limit=50&page={page}"
                    resp = self.session.get(url, headers=get_random_headers(), timeout=(3.5, 10.0))
                    if resp.status_code != 200:
                        logger.warning(f"[{self.__class__.__name__}] Unexpected HTTP {resp.status_code} for {resp.url}")
                        break
                    if resp.status_code == 200:
                        data = resp.json()
                        results = data.get("results", [])
                        if not results:
                            break
                        for item in results:
                            title = item.get("title", "")
                            link = f"https://www.itjobs.pt/oferta/{item.get('id')}"
                            if not is_valid_job_offer(link, title):
                                continue
                            company = item.get("company", {}).get("name", "Empresa ITJobs")
                            body = item.get("body", "")
                            locations = ", ".join([loc.get("name", "") for loc in item.get("locations", [])])
                            pub_date = item.get("created_at", datetime.date.today().isoformat())
                            jobs.append(Job(
                                title=title, company=company, location=locations or "Portugal",
                                work_mode="Presencial / Híbrido", link=link, description=body,
                                source="ITJobs.pt", pub_date=pub_date
                            ))
                logger.info(f"[ITJobs.pt API] Fetched {len(jobs)} jobs across pages 1-3.")
                return jobs
            except Exception as e:
                logger.warning(f"[ITJobs.pt API] Error: {e}, falling back to Direct Portal Scraping.")

        base_search_urls = [
            "https://www.itjobs.pt/emprego?q=data+scientist",
            "https://www.itjobs.pt/emprego?q=machine+learning",
            "https://www.itjobs.pt/emprego?q=inteligencia+artificial",
            "https://www.itjobs.pt/emprego?q=data+engineer",
            "https://www.itjobs.pt/emprego?q=python"
        ]
        search_urls = []
        for u in base_search_urls:
            for page in range(1, 4):
                search_urls.append(f"{u}&page={page}")
        
        seen_links = set()
        cards_to_fetch = []
        
        # 1. Fetch search URLs concurrently
        with ThreadPoolExecutor(max_workers=min(len(search_urls), 5)) as executor:
            future_to_url = {executor.submit(self._fetch_search_url_cards, url): url for url in search_urls}
            for future in as_completed(future_to_url):
                res = future.result()
                for c in res:
                    if c["link"] not in seen_links:
                        seen_links.add(c["link"])
                        cards_to_fetch.append(c)

        # 2. Fetch offer detail pages concurrently
        if cards_to_fetch:
            with ThreadPoolExecutor(max_workers=10) as executor:
                future_to_detail = {executor.submit(self._fetch_detail_body, c): c for c in cards_to_fetch}
                for future in as_completed(future_to_detail):
                    try:
                        jobs.append(future.result())
                    except Exception as err:
                        logger.debug(f"[ITJobs.pt Portal] Error fetching detail: {err}")

        logger.info(f"[ITJobs.pt Portal] Fetched {len(jobs)} jobs with full detail body parsing concurrently across pages 1-3.")
        return jobs
