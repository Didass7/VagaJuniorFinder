from __future__ import annotations
import os
import re
import glob
import time
import json
import random
import logging
import datetime
from typing import List, Dict, Set, Optional, Any
from urllib.parse import quote_plus, urljoin
import requests
from bs4 import BeautifulSoup
from config import config
from .base import (
    BaseScraper,
    Job,
    get_random_headers,
    get_session,
    clean_job_description,
    is_valid_job_offer,
)

logger = logging.getLogger("Scraper")

def find_system_browser_binary() -> Optional[str]:
    """Finds a valid Google Chrome or Playwright Chromium binary on the system."""
    candidate_paths = [
        *glob.glob(os.path.expanduser(r"~\AppData\Local\ms-playwright\**\chrome.exe"), recursive=True),
        *glob.glob(os.path.expanduser(r"~\AppData\Local\Google\Chrome\Application\chrome.exe"), recursive=True),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ]
    for path in candidate_paths:
        if os.path.isfile(path):
            return path
    return None


class IndeedScraper(BaseScraper):
    """
    Resilient Indeed scraper for Portugal & Remote tech/AI jobs.
    Implements a multi-tier strategy:
      1. Undetected Browser Automation (SeleniumBase UC / Playwright)
      2. Direct HTTP requests with cookie/session emulation
      3. Jooble Portugal API fallback (if JOOBLE_API_KEY is configured)
      4. RapidAPI / JSearch fallback (if RAPIDAPI_KEY is configured)
    """
    def __init__(
        self,
        session: Optional[requests.Session] = None,
        is_seen_func: Optional[Any] = None,
        queries: Optional[List[str]] = None,
    ):
        super().__init__(session=session, is_seen_func=is_seen_func, queries=queries)

    def _parse_indeed_html(self, html: str, base_url: str = "https://pt.indeed.com") -> List[Job]:
        """Parses Indeed job search results HTML into Job objects."""
        jobs: List[Job] = []
        if not html or ("Security Check" in html and "job_seen_beacon" not in html):
            return jobs

        soup = BeautifulSoup(html, "html.parser")
        
        # Collect cards from all known Indeed card selectors
        card_selectors = [
            "div.job_seen_beacon",
            "div.cardOutline",
            "td.resultContent",
            "li.css-5lfssm",
            "[data-testid='slider_item']",
            "div[class*='job_seen_beacon']",
            "div[class*='cardOutline']"
        ]
        
        raw_cards = []
        for selector in card_selectors:
            raw_cards.extend(soup.select(selector))
            
        # Deduplicate card elements (avoid parent and child double match)
        seen_card_texts = set()
        cards = []
        for card in raw_cards:
            t = card.get_text(strip=True)
            if t and t not in seen_card_texts and len(t) > 10:
                seen_card_texts.add(t)
                cards.append(card)

        for card in cards:
            try:
                # 1. Title & Link
                title_elem = (
                    card.find("h2", class_=lambda c: c and "jobTitle" in str(c)) or
                    card.find("a", class_=lambda c: c and "jcs-JobTitle" in str(c)) or
                    card.find("a", href=re.compile(r"/rc/clk|/viewjob|/job/"))
                )
                if not title_elem:
                    continue

                link_elem = title_elem if title_elem.name == "a" else title_elem.find("a")
                title = title_elem.get_text(separator=" ", strip=True)
                raw_href = link_elem.get("href", "") if link_elem else ""

                if not title or len(title) < 4:
                    continue

                if raw_href.startswith("/"):
                    link = urljoin(base_url, raw_href)
                elif raw_href.startswith("http"):
                    link = raw_href
                else:
                    link = f"{base_url}/viewjob?jk={raw_href}"

                # Normalize link (strip tracking parameters)
                if "/viewjob" in link and "jk=" in link:
                    jk_match = re.search(r"jk=([a-zA-Z0-9]+)", link)
                    if jk_match:
                        link = f"{base_url}/viewjob?jk={jk_match.group(1)}"
                elif "?" in link:
                    link = link.split("?")[0]

                # 2. Company Name
                company_elem = (
                    card.find("span", attrs={"data-testid": "company-name"}) or
                    card.find("span", class_=lambda c: c and "companyName" in str(c)) or
                    card.find("span", class_=lambda c: c and "css-63koeb" in str(c)) or
                    card.find("div", class_=lambda c: c and "company_location" in str(c))
                )
                company = company_elem.get_text(separator=" ", strip=True) if company_elem else "Empresa no Indeed"

                # 3. Location
                loc_elem = (
                    card.find("div", attrs={"data-testid": "text-location"}) or
                    card.find("div", class_=lambda c: c and "companyLocation" in str(c)) or
                    card.find("div", class_=lambda c: c and "location" in str(c))
                )
                location = loc_elem.get_text(separator=" ", strip=True) if loc_elem else "Portugal"

                # 4. Job Snippet / Description
                snippet_elem = (
                    card.find("div", class_=lambda c: c and "job-snippet" in str(c)) or
                    card.find("ul", class_=lambda c: c and "job-snippet" in str(c)) or
                    card.find("div", class_=lambda c: c and "underSubtitle" in str(c))
                )
                snippet_text = snippet_elem.get_text(separator=" ", strip=True) if snippet_elem else title
                clean_desc = clean_job_description(f"{title} - {company} ({location}). {snippet_text}")

                # 5. Work Mode Inference
                text_lower = f"{title} {location} {clean_desc}".lower()
                work_mode = "Presencial / Híbrido"
                if any(t in text_lower for t in ["remoto", "remote", "100% remote", "teletrabalho"]):
                    work_mode = "Remoto"
                elif any(t in text_lower for t in ["híbrido", "hibrido", "hybrid"]):
                    work_mode = "Híbrido"
                elif any(t in text_lower for t in ["presencial", "onsite", "on-site"]):
                    work_mode = "Presencial"

                # Pre-filter check
                if not is_valid_job_offer(link, title):
                    continue

                if self.is_seen_func and self.is_seen_func(title, company):
                    continue

                jobs.append(Job(
                    title=title,
                    company=company,
                    location=location,
                    work_mode=work_mode,
                    link=link,
                    description=clean_desc,
                    source="Indeed",
                    pub_date=datetime.date.today().isoformat()
                ))
            except Exception as item_err:
                logger.debug(f"[Indeed Parser] Error parsing card: {item_err}")

        return jobs

    def _fetch_via_seleniumbase(self, queries: List[str]) -> List[Job]:
        """Scrapes Indeed using SeleniumBase in Undetected Chrome (UC) mode."""
        jobs: List[Job] = []
        try:
            from seleniumbase import Driver
        except ImportError:
            logger.debug("[Indeed Scraper] seleniumbase not installed, skipping UC mode.")
            return jobs

        binary_path = find_system_browser_binary()
        driver = None
        try:
            driver_kwargs: Dict[str, Any] = {"uc": True, "headless": False}
            if binary_path:
                driver_kwargs["binary_location"] = binary_path

            driver = Driver(**driver_kwargs)
            for q in queries:
                url = f"https://pt.indeed.com/jobs?q={quote_plus(q)}&l=Portugal&sort=date"
                try:
                    driver.uc_open_with_reconnect(url, reconnect_time=6)
                    time.sleep(random.uniform(3.0, 5.0))

                    if "Security Check" in driver.title or "Just a moment" in driver.title:
                        try:
                            driver.uc_gui_click_captcha()
                            time.sleep(random.uniform(4.0, 6.0))
                        except Exception:
                            pass

                    page_source = driver.page_source
                    parsed = self._parse_indeed_html(page_source)
                    jobs.extend(parsed)
                except Exception as q_err:
                    logger.debug(f"[Indeed UC] Error querying '{q}': {q_err}")

        except Exception as e:
            logger.debug(f"[Indeed UC Mode] Execution exception: {e}")
        finally:
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass

        return jobs

    def _fetch_via_http_session(self, queries: List[str]) -> List[Job]:
        """Attempts direct HTTP scraping with realistic rotated browser headers and cookies (from env or data/indeed_cookies.json)."""
        jobs: List[Job] = []
        headers = get_random_headers()
        
        # Check for persistent saved session from login_indeed.py
        cookies_file = os.path.join("data", "indeed_cookies.json")
        saved_cookies = ""
        if os.path.isfile(cookies_file):
            try:
                with open(cookies_file, "r", encoding="utf-8") as f:
                    saved_data = json.load(f)
                    saved_cookies = saved_data.get("cookies", "")
                    if saved_data.get("user_agent"):
                        headers["User-Agent"] = saved_data["user_agent"]
            except Exception as e:
                logger.debug(f"[Indeed HTTP] Error loading {cookies_file}: {e}")

        cookie_val = config.indeed_cookies or saved_cookies
        if cookie_val:
            headers["Cookie"] = cookie_val

        headers.update({
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "pt-PT,pt;q=0.9,en-US;q=0.8,en;q=0.7",
            "Referer": "https://pt.indeed.com/",
        })

        proxies = {"http": config.indeed_proxy, "https": config.indeed_proxy} if config.indeed_proxy else None

        for q in queries:
            url = f"https://pt.indeed.com/jobs?q={quote_plus(q)}&l=Portugal&sort=date"
            try:
                time.sleep(random.uniform(0.6, 1.2))
                resp = self.session.get(url, headers=headers, proxies=proxies, timeout=(4.0, 10.0))
                if resp.status_code == 200:
                    parsed = self._parse_indeed_html(resp.text)
                    jobs.extend(parsed)
                elif resp.status_code == 403:
                    logger.debug(f"[Indeed HTTP] Cloudflare protected (403) for query '{q}'.")
            except Exception as e:
                logger.debug(f"[Indeed HTTP] Request error for '{q}': {e}")

        return jobs

    def _fetch_via_jooble_api(self, queries: List[str]) -> List[Job]:
        """Fetches Portugal tech jobs from Jooble REST API (which aggregates Indeed & Portuguese portals)."""
        jobs: List[Job] = []
        api_key = getattr(config, "jooble_api_key", "") or os.getenv("JOOBLE_API_KEY", "")
        if not api_key:
            return jobs

        url = f"https://pt.jooble.org/api/{api_key}"
        for q in queries:
            try:
                payload = {
                    "keywords": q,
                    "location": "Portugal",
                }
                headers = {"Content-Type": "application/json"}
                resp = self.session.post(url, json=payload, headers=headers, timeout=(4.0, 12.0))
                if resp.status_code == 200:
                    data = resp.json()
                    for item in data.get("jobs", []):
                        title = item.get("title", "")
                        link = item.get("link", "")
                        company = item.get("company", "Empresa via Jooble/Indeed")
                        loc = item.get("location", "Portugal")
                        snippet = item.get("snippet", "")
                        pub_date = item.get("updated", datetime.date.today().isoformat())[:10]

                        clean_desc = clean_job_description(f"{title} - {company} ({loc}). {snippet}")
                        if not is_valid_job_offer(link, title):
                            continue
                        if self.is_seen_func and self.is_seen_func(title, company):
                            continue

                        work_mode = "Presencial / Híbrido"
                        text_l = f"{title} {loc} {clean_desc}".lower()
                        if "remoto" in text_l or "remote" in text_l:
                            work_mode = "Remoto"
                        elif "híbrido" in text_l or "hybrid" in text_l:
                            work_mode = "Híbrido"

                        jobs.append(Job(
                            title=title,
                            company=company,
                            location=loc,
                            work_mode=work_mode,
                            link=link,
                            description=clean_desc,
                            source="Indeed / Jooble",
                            pub_date=pub_date
                        ))
            except Exception as j_err:
                logger.debug(f"[Indeed/Jooble API] Error fetching '{q}': {j_err}")

        return jobs

    def _fetch_via_rapidapi(self, queries: List[str]) -> List[Job]:
        """Fetches Indeed jobs in Portugal via RapidAPI / JSearch if configured."""
        jobs: List[Job] = []
        api_key = getattr(config, "rapidapi_key", "") or os.getenv("RAPIDAPI_KEY", "")
        if not api_key:
            return jobs

        url = "https://jsearch.p.rapidapi.com/search"
        headers = {
            "X-RapidAPI-Key": api_key,
            "X-RapidAPI-Host": "jsearch.p.rapidapi.com"
        }

        for q in queries:
            try:
                params = {
                    "query": f"{q} in Portugal",
                    "page": "1",
                    "num_pages": "1"
                }
                resp = self.session.get(url, headers=headers, params=params, timeout=(4.0, 12.0))
                if resp.status_code == 200:
                    data = resp.json()
                    for item in data.get("data", []):
                        title = item.get("job_title", "")
                        link = item.get("job_apply_link", "") or item.get("job_google_link", "")
                        company = item.get("employer_name", "Empresa no Indeed")
                        city = item.get("job_city", "")
                        country = item.get("job_country", "Portugal")
                        loc = f"{city}, {country}" if city else country
                        desc = item.get("job_description", "")
                        is_remote = item.get("job_is_remote", False)

                        clean_desc = clean_job_description(desc) if desc else title
                        if not is_valid_job_offer(link, title):
                            continue
                        if self.is_seen_func and self.is_seen_func(title, company):
                            continue

                        work_mode = "Remoto" if is_remote else "Presencial / Híbrido"
                        jobs.append(Job(
                            title=title,
                            company=company,
                            location=loc,
                            work_mode=work_mode,
                            link=link,
                            description=clean_desc,
                            source="Indeed",
                            pub_date=datetime.date.today().isoformat()
                        ))
            except Exception as r_err:
                logger.debug(f"[Indeed RapidAPI] Error fetching '{q}': {r_err}")

    def _fetch_via_adzuna_api(self, queries: List[str]) -> List[Job]:
        """Fetches Portugal tech jobs from Adzuna API (aggregates Indeed and Portuguese sources)."""
        jobs: List[Job] = []
        app_id = getattr(config, "adzuna_app_id", "") or os.getenv("ADZUNA_APP_ID", "")
        app_key = getattr(config, "adzuna_app_key", "") or os.getenv("ADZUNA_APP_KEY", "")
        if not app_id or not app_key:
            return jobs

        for q in queries:
            try:
                url = f"https://api.adzuna.com/v1/api/jobs/pt/search/1"
                params = {
                    "app_id": app_id,
                    "app_key": app_key,
                    "what": q,
                    "where": "Portugal",
                    "content-type": "application/json"
                }
                resp = self.session.get(url, params=params, timeout=(4.0, 12.0))
                if resp.status_code == 200:
                    data = resp.json()
                    for item in data.get("results", []):
                        title = item.get("title", "")
                        link = item.get("redirect_url", "")
                        company_info = item.get("company", {})
                        company = company_info.get("display_name", "Empresa no Indeed / Adzuna")
                        loc_info = item.get("location", {})
                        loc = loc_info.get("display_name", "Portugal")
                        desc = item.get("description", "")
                        pub_date = item.get("created", datetime.date.today().isoformat())[:10]

                        clean_desc = clean_job_description(f"{title} - {company} ({loc}). {desc}")
                        if not is_valid_job_offer(link, title):
                            continue
                        if self.is_seen_func and self.is_seen_func(title, company):
                            continue

                        work_mode = "Presencial / Híbrido"
                        text_l = f"{title} {loc} {clean_desc}".lower()
                        if "remoto" in text_l or "remote" in text_l:
                            work_mode = "Remoto"
                        elif "híbrido" in text_l or "hybrid" in text_l:
                            work_mode = "Híbrido"

                        jobs.append(Job(
                            title=title,
                            company=company,
                            location=loc,
                            work_mode=work_mode,
                            link=link,
                            description=clean_desc,
                            source="Indeed / Adzuna",
                            pub_date=pub_date
                        ))
            except Exception as a_err:
                logger.debug(f"[Indeed/Adzuna API] Error fetching '{q}': {a_err}")

        return jobs

    def fetch(self) -> List[Job]:
        """Main fetch pipeline running multi-tier strategies and deduplicating jobs."""
        queries = (
            self.queries or
            config.candidate.search_queries or
            ["python", "data", "inteligencia artificial", "machine learning", "estagio iefp"]
        )
        all_jobs: List[Job] = []

        # Tier 1: Saved Cookie session / Direct HTTP (fastest if session is available)
        cookies_file = os.path.join("data", "indeed_cookies.json")
        if config.indeed_cookies or os.path.isfile(cookies_file):
            try:
                http_jobs = self._fetch_via_http_session(queries)
                if http_jobs:
                    all_jobs.extend(http_jobs)
            except Exception as e:
                logger.debug(f"[Indeed Portal] Saved HTTP session error: {e}")

        # Tier 2: Undetected Browser / SeleniumBase UC (if no saved cookies or yielded 0)
        if not all_jobs:
            try:
                uc_jobs = self._fetch_via_seleniumbase(queries[:4])
                if uc_jobs:
                    all_jobs.extend(uc_jobs)
            except Exception as e:
                logger.debug(f"[Indeed Portal] Browser strategy error: {e}")

        # Tier 3: Jooble API Fallback
        if not all_jobs and (getattr(config, "jooble_api_key", "") or os.getenv("JOOBLE_API_KEY")):
            try:
                jooble_jobs = self._fetch_via_jooble_api(queries)
                if jooble_jobs:
                    all_jobs.extend(jooble_jobs)
            except Exception as e:
                logger.debug(f"[Indeed Portal] Jooble API fallback error: {e}")

        # Tier 4: Adzuna API Fallback
        if not all_jobs and ((getattr(config, "adzuna_app_id", "") and getattr(config, "adzuna_app_key", "")) or (os.getenv("ADZUNA_APP_ID") and os.getenv("ADZUNA_APP_KEY"))):
            try:
                adzuna_jobs = self._fetch_via_adzuna_api(queries)
                if adzuna_jobs:
                    all_jobs.extend(adzuna_jobs)
            except Exception as e:
                logger.debug(f"[Indeed Portal] Adzuna API fallback error: {e}")

        # Tier 5: RapidAPI / JSearch Fallback
        if not all_jobs and (getattr(config, "rapidapi_key", "") or os.getenv("RAPIDAPI_KEY")):
            try:
                rapid_jobs = self._fetch_via_rapidapi(queries)
                if rapid_jobs:
                    all_jobs.extend(rapid_jobs)
            except Exception as e:
                logger.debug(f"[Indeed Portal] RapidAPI fallback error: {e}")

        # Deduplicate
        unique_jobs: Dict[str, Job] = {}
        for j in all_jobs:
            if j.job_id not in unique_jobs:
                unique_jobs[j.job_id] = j

        final_jobs = list(unique_jobs.values())
        logger.info(f"[Indeed Portal] Fetched {len(final_jobs)} jobs safely.")
        return final_jobs
