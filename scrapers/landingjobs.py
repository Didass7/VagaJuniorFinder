from __future__ import annotations
import re
import datetime
import logging
from typing import List, Dict, Set, Optional
import requests
import feedparser
from .base import BaseScraper, Job, get_random_headers, clean_job_description, is_valid_job_offer

logger = logging.getLogger("Scraper")

class LandingJobsScraper(BaseScraper):
    """Scrapes Landing.jobs portal via official Atom feed (bypasses Cloudflare 403 on cloud runners) with API fallback."""
    def __init__(self, session: Optional[requests.Session] = None):
        super().__init__(session=session)

    def fetch(self) -> List[Job]:
        jobs = []
        seen_links = set()
        
        # Strategy 1: Official Atom Feeds (Unblockable on GitHub Actions / cloud IPs)
        atom_urls = [
            "https://landing.jobs/jobs.atom",
            "https://landing.jobs/feed"
        ]
        
        for atom_url in atom_urls:
            try:
                headers = get_random_headers()
                headers["Accept"] = "application/atom+xml,application/xml,text/xml;q=0.9,*/*;q=0.8"
                resp = self.session.get(atom_url, headers=headers, timeout=(4.0, 12.0))
                if resp.status_code == 200 and resp.content:
                    feed = feedparser.parse(resp.content) or feedparser.parse(resp.text)
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
                logger.debug(f"[LandingJobsScraper] Atom feed error for {atom_url}: {e}")

        # Strategy 2: Fallback to REST API if Atom feed was empty or failed
        if not jobs:
            for page in range(1, 4):
                url = f"https://landing.jobs/api/v1/jobs?page={page}"
                try:
                    headers = get_random_headers()
                    headers["Accept"] = "application/json, text/plain, */*"
                    resp = self.session.get(url, headers=headers, timeout=(3.5, 10.0))
                    if resp.status_code != 200:
                        break
                    items = resp.json()
                    if not items or not isinstance(items, list):
                        break
                    for item in items:
                        title = item.get("title", "")
                        link = item.get("url", "")
                        if "?" in link:
                            link = link.split("?")[0]
                        if not link or link in seen_links or not is_valid_job_offer(link, title):
                            continue
                        seen_links.add(link)

                        company = item.get("company_name", "Landing.jobs Company")
                        location = item.get("location", "Portugal / EU")
                        remote = item.get("remote", False)
                        work_mode = "Remoto" if remote else "Presencial / Híbrido"
                        desc = item.get("role_description", "") or item.get("summary", "")
                        pub_date = item.get("published_at", datetime.date.today().isoformat())

                        jobs.append(Job(
                            title=title, company=company, location=location,
                            work_mode=work_mode, link=link, description=desc,
                            source="Landing.jobs", pub_date=str(pub_date)[:10]
                        ))
                except Exception as e:
                    logger.debug(f"[Landing.jobs Portal] API error at page {page}: {e}")
                    break
                    
        logger.info(f"[Landing.jobs Portal] Fetched {len(jobs)} jobs successfully.")
        return jobs
