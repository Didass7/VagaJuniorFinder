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
from .base import BaseScraper, Job, get_random_headers, clean_job_description, is_valid_job_offer

logger = logging.getLogger("Scraper")

class LinkedInScraper(BaseScraper):
    """Scrapes LinkedIn public search portal for Portugal AI & Data Science jobs with realistic browser headers."""
    def __init__(self, session: Optional[requests.Session] = None, is_seen_func: Optional[Any] = None, queries: Optional[List[str]] = None):
        super().__init__(session=session, is_seen_func=is_seen_func, queries=queries)

    def _fetch_query_cards(self, query: str, max_pages: int = 10) -> List[Dict]:
        cards_data = []
        for page in range(max_pages):
            start = page * 25
            try:
                url = f"https://www.linkedin.com/jobs/search?keywords={query.replace(' ', '%20')}&location=Portugal&f_TPR=r2592000&start={start}"
                headers = get_random_headers()
                headers.update({
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.9,pt-PT;q=0.8,pt;q=0.7",
                    "Sec-Fetch-Dest": "document",
                    "Sec-Fetch-Mode": "navigate",
                    "Sec-Fetch-Site": "none",
                    "Sec-Fetch-User": "?1",
                    "Upgrade-Insecure-Requests": "1"
                })
                time.sleep(random.uniform(0.2, 0.4))
                resp = self.session.get(url, headers=headers, timeout=(3.5, 10.0))

                if resp.status_code != 200:
                    if resp.status_code == 429:
                        time.sleep(random.uniform(1.5, 3.0))
                        headers = get_random_headers()
                        resp = self.session.get(url, headers=headers, timeout=(3.5, 10.0))

                    if resp.status_code != 200:
                        if resp.status_code == 429:
                            logger.debug(f"[{self.__class__.__name__}] HTTP 429 rate limit for query '{query}' (start={start})")
                        else:
                            logger.warning(f"[{self.__class__.__name__}] HTTP {resp.status_code} for query '{query}' (start={start})")
                        break

                soup = BeautifulSoup(resp.text, "html.parser")
                cards = soup.find_all("li") or soup.find_all("div", class_=lambda c: c and "base-card" in str(c))
                if not cards:
                    break
                new_count = 0
                for card in cards:
                    title_elem = card.find("h3", class_=lambda c: c and "title" in str(c)) or card.find("h3") or card.find("h4")
                    link_elem = card.find("a", class_=lambda c: c and "link" in str(c)) or card.find("a")
                    company_elem = card.find("h4", class_=lambda c: c and "subtitle" in str(c)) or card.find("h4") or card.find("h3")
                    loc_elem = card.find("span", class_=lambda c: c and "location" in str(c)) or card.find("span")
                    time_elem = card.find("time")
                    
                    if not title_elem or not link_elem or not link_elem.get("href"):
                        continue
                    
                    title = title_elem.get_text(separator=' ', strip=True)
                    raw_link = link_elem.get("href", "")
                    clean_link = raw_link.split("?")[0].rstrip("/")
                    company = company_elem.get_text(separator=' ', strip=True) if company_elem else "Empresa no LinkedIn"
                    location = loc_elem.get_text(separator=' ', strip=True) if loc_elem else "Portugal"
                    
                    pub_date = datetime.date.today().isoformat()
                    if time_elem and time_elem.get("datetime"):
                        pub_date = time_elem.get("datetime")[:10]

                    if is_valid_job_offer(clean_link, title):
                        if self.is_seen_func and self.is_seen_func(title, company):
                            continue
                        cards_data.append({
                            "title": title, "clean_link": clean_link,
                            "company": company, "location": location,
                            "pub_date": pub_date
                        })
                        new_count += 1
                if new_count == 0:
                    break
            except Exception as e:
                logger.debug(f"[LinkedIn Portal] Error fetching '{query}' (page {page+1}): {e}")
                break
        return cards_data

    def _fetch_detail_job(self, card_info: Dict) -> Job:
        title = card_info["title"]
        clean_link = card_info["clean_link"]
        company = card_info["company"]
        location = card_info["location"]
        pub_date = card_info["pub_date"]
        
        desc = ""
        try:
            # Extract numeric job ID from LinkedIn URL
            id_match = re.search(r"(\d{8,12})", clean_link)
            if id_match:
                time.sleep(random.uniform(0.15, 0.35))
                job_posting_id = id_match.group(1)
                guest_api_url = f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_posting_id}"
                headers = get_random_headers()
                headers.update({
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                    "Accept-Language": "pt-PT,pt;q=0.9,en-US;q=0.8,en;q=0.7",
                })
                resp = self.session.get(guest_api_url, headers=headers, timeout=(3.5, 8.0))
                if resp.status_code == 200:
                    detail_soup = BeautifulSoup(resp.text, "html.parser")
                    markup = (
                        detail_soup.find("div", class_=lambda c: c and "show-more-less-html__markup" in str(c)) or
                        detail_soup.find("section", class_=lambda c: c and "description" in str(c)) or
                        detail_soup.find("div", class_=lambda c: c and "description__text" in str(c))
                    )
                    text_content = markup.get_text(separator=" ", strip=True) if markup else ""

                    criteria_list = []
                    criteria_elem = detail_soup.find("ul", class_=lambda c: c and "job-criteria" in str(c))
                    if criteria_elem:
                        for li in criteria_elem.find_all("li"):
                            criteria_list.append(li.get_text(separator=": ", strip=True))

                    extra_texts = []
                    for p in detail_soup.find_all(["p", "span", "div"]):
                        p_txt = p.get_text(strip=True)
                        if any(k in p_txt.lower() for k in ["level of experience", "anos de experi", "years of experi"]):
                            extra_texts.append(p.get_text(separator=" ", strip=True))

                    full_parts = [title]
                    if criteria_list:
                        full_parts.append(" | ".join(criteria_list))
                    if extra_texts:
                        full_parts.append(" | ".join(extra_texts))
                    if text_content:
                        full_parts.append(clean_job_description(text_content))

                    combined = " - ".join(full_parts)
                    if len(combined) > 100:
                        desc = combined
        except Exception as d_err:
            logger.debug(f"LinkedIn detail fetch via guest API failed for {clean_link}: {d_err}")

        # Secondary fallback: Fetch direct job page URL (bypasses guest API blocking, parses JSON-LD or full markup)
        if not desc or len(desc) < 100:
            try:
                time.sleep(random.uniform(0.15, 0.35))
                headers = get_random_headers()
                headers.update({
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "pt-PT,pt;q=0.9,en-US;q=0.8,en;q=0.7",
                })
                resp = self.session.get(clean_link, headers=headers, timeout=(3.5, 8.0))
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, "html.parser")
                    import html as html_lib
                    import json as json_lib
                    for script in soup.find_all("script", type="application/ld+json"):
                        try:
                            ld_data = json_lib.loads(script.string)
                            if isinstance(ld_data, dict) and "description" in ld_data:
                                raw_desc = html_lib.unescape(ld_data["description"])
                                clean_text = BeautifulSoup(raw_desc, "html.parser").get_text(separator=" ", strip=True)
                                if len(clean_text) > 100:
                                    desc = f"{title} - {clean_job_description(clean_text)}"
                                    break
                        except Exception:
                            pass

                    if not desc or len(desc) < 100:
                        markup = (
                            soup.find("div", class_=lambda c: c and "show-more-less-html__markup" in str(c)) or
                            soup.find("section", class_=lambda c: c and "description" in str(c))
                        )
                        if markup:
                            text = markup.get_text(separator=" ", strip=True)
                            if len(text) > 100:
                                desc = f"{title} - {clean_job_description(text)}"
            except Exception as page_err:
                logger.debug(f"LinkedIn direct page fetch failed for {clean_link}: {page_err}")

        # Fallback description if all endpoints were blocked
        if not desc or len(desc) < 100:
            desc = f"{title} na empresa {company} ({location}). Oportunidade de emprego publicada no LinkedIn Jobs Portugal com foco em tecnologia e engenharia informática."

        return Job(
            title=title, company=company, location=location,
            work_mode="Presencial / Híbrido", link=clean_link, description=desc,
            source="LinkedIn", pub_date=pub_date
        )

    def fetch(self) -> List[Job]:
        queries = self.queries or config.candidate.search_queries or ["Junior AI", "Junior Data Scientist", "Machine Learning Trainee", "Data Engineer Trainee", "Entry level AI", "Entry level Data"]
        target_queries = list(queries)
        all_cards: List[Dict] = []
        seen_links: Set[str] = set()
        
        # 1. Fetch query cards concurrently across all pages
        with ThreadPoolExecutor(max_workers=min(len(target_queries), 6)) as executor:
            future_to_q = {executor.submit(self._fetch_query_cards, q): q for q in target_queries}
            for future in as_completed(future_to_q):
                try:
                    res = future.result()
                    for card in res:
                        if card["clean_link"] not in seen_links:
                            seen_links.add(card["clean_link"])
                            all_cards.append(card)
                except Exception as e:
                    logger.debug(f"[LinkedIn Portal] Error fetching query cards: {e}")

        # 2. Fetch full detail bodies concurrently for all discovered jobs
        jobs: List[Job] = []
        cards_to_fetch = all_cards
        if cards_to_fetch:
            with ThreadPoolExecutor(max_workers=6) as executor:
                future_to_detail = {executor.submit(self._fetch_detail_job, card): card for card in cards_to_fetch}

                for future in as_completed(future_to_detail):
                    try:
                        job = future.result()
                        if job.description and len(job.description) >= 50:
                            jobs.append(job)
                    except Exception as e:
                        logger.debug(f"[LinkedIn Portal] Error fetching job detail: {e}")

        logger.info(f"[LinkedIn Portal] Safely fetched {len(jobs)} fresh jobs with full detail body parsing across all available pages.")
        return jobs


