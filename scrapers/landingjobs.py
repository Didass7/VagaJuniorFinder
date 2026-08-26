from __future__ import annotations
import re
import datetime
import logging
from typing import List, Dict, Set, Optional
import requests
import feedparser
from .base import BaseScraper, Job, get_random_headers, clean_job_description, is_valid_job_offer, safe_fetch

logger = logging.getLogger("Scraper")

class LandingJobsScraper(BaseScraper):
    """Scrapes Landing.jobs portal via official Atom feed (bypasses Cloudflare 403 on cloud runners) with API fallback."""
    def __init__(self, session: Optional[requests.Session] = None):
        super().__init__(session=session)

    def fetch(self) -> List[Job]:
        jobs = []
        seen_links = set()

        # Strategy 1: Official Landing.jobs REST API (Direct Clean Requests + Cloud Edge Relay)
        import json
        for page in range(1, 6):
            url = f"https://landing.jobs/api/v1/jobs?page={page}"
            text = ""
            status_code = 0
            
            # Step 1: Direct requests with clean browser headers
            try:
                h = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                    "Accept": "application/json, text/plain, */*",
                    "Accept-Language": "pt-PT,pt;q=0.9,en-US;q=0.8,en;q=0.7"
                }
                r = requests.get(url, headers=h, timeout=8.0)
                if r.status_code == 200 and r.text and r.text.strip().startswith("["):
                    status_code = 200
                    text = r.text
            except Exception as direct_err:
                logger.debug(f"[Landing.jobs] Direct API error: {direct_err}")

            # Step 2: Cloud Runner Edge Relay fallback if direct request was blocked
            if status_code != 200 or not text:
                try:
                    relay_url = f"https://r.jina.ai/{url}"
                    resp = requests.get(relay_url, timeout=12.0)
                    if resp.status_code == 200 and resp.text:
                        raw_t = resp.text
                        if "Markdown Content:" in raw_t:
                            raw_t = raw_t.split("Markdown Content:", 1)[1].strip()
                        if raw_t.startswith("```json"):
                            raw_t = raw_t[7:]
                        if raw_t.startswith("```"):
                            raw_t = raw_t[3:]
                        if raw_t.endswith("```"):
                            raw_t = raw_t[:-3]
                        text = raw_t.strip()
                        status_code = 200
                except Exception as relay_err:
                    logger.debug(f"[Landing.jobs] Relay fetch error: {relay_err}")

            if status_code != 200 or not text:
                break

            try:
                items = json.loads(text)
                if not items or not isinstance(items, list):
                    break

                for item in items:
                    title = item.get("title", "").strip()
                    link = item.get("url", "").strip()
                    if "?" in link:
                        link = link.split("?")[0]
                    if not link or link in seen_links or not is_valid_job_offer(link, title):
                        continue
                    seen_links.add(link)

                    # Extract company from API or parse from URL slug /at/<company>/<job>
                    company = item.get("company_name")
                    if not company and "/at/" in link:
                        parts = link.split("/at/")[1].split("/")
                        if parts:
                            company = parts[0].replace("-", " ").title()
                    if not company:
                        company = "Landing.jobs Company"

                    location = item.get("city") or item.get("location") or "Portugal / EU"
                    remote = item.get("remote", False)
                    work_mode = "Remoto" if remote else "Presencial / Híbrido"
                    desc = item.get("role_description", "") or item.get("summary", "") or title
                    pub_date = item.get("published_at", datetime.date.today().isoformat())

                    jobs.append(Job(
                        title=title, company=company, location=location,
                        work_mode=work_mode, link=link, description=clean_job_description(desc),
                        source="Landing.jobs", pub_date=str(pub_date)[:10]
                    ))
            except Exception as e:
                logger.warning(f"[Landing.jobs Portal] JSON parse error at page {page}: {e}")
                break

        # Strategy 2: Official Atom/RSS Feeds
        if not jobs:
            atom_urls = [
                "https://landing.jobs/feed.atom",
                "https://landing.jobs/jobs.atom",
                "https://landing.jobs/feed",
            ]
            for atom_url in atom_urls:
                try:
                    status_code, text, content = safe_fetch(atom_url, session=self.session, timeout=10.0)
                    if status_code == 200 and (content or text):
                        payload = text if text else (content.decode("utf-8", errors="ignore") if content else "")
                        feed = feedparser.parse(payload)
                        if feed and feed.entries:
                            for entry in feed.entries:
                                title = entry.get("title", "").strip()
                                link = entry.get("link", "").strip()
                                if "?" in link:
                                    link = link.split("?")[0]
                                
                                if not link or link in seen_links or not is_valid_job_offer(link, title):
                                    continue
                                seen_links.add(link)

                                company = entry.get("author", "") or entry.get("author_detail", {}).get("name", "Landing.jobs Company")
                                pub_date = entry.get("published", "") or entry.get("updated", datetime.date.today().isoformat())
                                pub_date_str = str(pub_date)[:10]

                                raw_content = entry.get("summary", "") or (entry.get("content", [{}])[0].get("value", "") if entry.get("content") else "")
                                clean_desc = clean_job_description(raw_content)

                                work_mode = "Presencial / Híbrido"
                                desc_lower = clean_desc.lower()
                                if "remote policy: full remote" in desc_lower or "full remote" in desc_lower or "100% remote" in desc_lower:
                                    work_mode = "Remoto"
                                elif "partial remote" in desc_lower or "hybrid" in desc_lower or "híbrido" in desc_lower:
                                    work_mode = "Presencial / Híbrido"

                                location = "Lisboa / Porto, Portugal"
                                loc_match = re.search(r"in\s+([A-Za-z\s,]+),\s*Portugal", clean_desc, re.IGNORECASE)
                                if loc_match:
                                    location = f"{loc_match.group(1).strip()}, Portugal"
                                elif "in portugal" in desc_lower:
                                    location = "Portugal"

                                jobs.append(Job(
                                    title=title, company=company, location=location,
                                    work_mode=work_mode, link=link, description=clean_desc,
                                    source="Landing.jobs", pub_date=pub_date_str
                                ))
                            if jobs:
                                break
                except Exception as e:
                    logger.warning(f"[LandingJobsScraper] Atom feed error for {atom_url}: {e}")

        # Strategy 3: HTML Scrape fallback
        if not jobs:
            from bs4 import BeautifulSoup
            try:
                for page in range(1, 4):
                    url = f"https://landing.jobs/jobs?page={page}"
                    status_code, text, _ = safe_fetch(url, session=self.session, timeout=10.0)
                    if status_code != 200 or not text:
                        break
                    soup = BeautifulSoup(text, "html.parser")
                    cards = soup.find_all("a", href=re.compile(r"/at/[^/]+/[^/]+"))
                    for a in cards:
                        raw_href = a.get("href", "")
                        clean_link = f"https://landing.jobs{raw_href}" if not raw_href.startswith("http") else raw_href
                        title = a.get_text(separator=" ", strip=True)
                        if not title or len(title) < 5 or clean_link in seen_links or not is_valid_job_offer(clean_link, title):
                            continue
                        seen_links.add(clean_link)
                        
                        parts = raw_href.strip("/").split("/")
                        company = parts[1].replace("-", " ").title() if len(parts) >= 3 else "Landing.jobs Company"
                        
                        jobs.append(Job(
                            title=title,
                            company=company,
                            location="Portugal / EU",
                            work_mode="Presencial / Híbrido",
                            link=clean_link,
                            description=title,
                            source="Landing.jobs",
                            pub_date=datetime.date.today().isoformat()
                        ))
            except Exception as e:
                logger.warning(f"[Landing.jobs Portal] HTML scrape error: {e}")
                    
        logger.info(f"[Landing.jobs Portal] Fetched {len(jobs)} jobs successfully.")
        return jobs
