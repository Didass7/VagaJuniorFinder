from __future__ import annotations
import datetime
import logging
from typing import List, Dict, Optional, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from bs4 import BeautifulSoup
from .base import BaseScraper, Job, get_random_headers, clean_job_description, is_valid_job_offer

logger = logging.getLogger("Scraper")

class JobspressoScraper(BaseScraper):
    """Scrapes Jobspresso HTML job listings for remote tech & data jobs with full detail body parsing."""
    def __init__(self, session: Optional[requests.Session] = None):
        super().__init__(session=session)

    def _fetch_detail_page(self, card: Dict[str, Any]) -> Job:
        title = card["title"]
        href = card["link"]
        company = card["company"]
        location = card["location"]
        desc = card["summary"]

        try:
            resp = self.session.get(href, headers=get_random_headers(), timeout=(3.5, 10.0))
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                desc_elem = (
                    soup.find("div", class_="job_listing-description")
                    or soup.find("div", class_="job-overview")
                    or soup.find("div", class_="entry-content")
                )
                if desc_elem:
                    full_txt = desc_elem.get_text(separator=" ", strip=True)
                    if len(full_txt) > 100:
                        desc = f"{title} - " + clean_job_description(full_txt)

                # Real company name from detail page if available
                comp_tag = soup.find("h2", class_="company_name") or soup.find("span", class_="company_name") or soup.find("a", class_="company-name")
                if comp_tag:
                    c_txt = comp_tag.get_text(strip=True)
                    if c_txt and len(c_txt) > 1:
                        company = c_txt
        except Exception as e:
            logger.debug(f"[Jobspresso Portal] Detail fetch failed for {href}: {e}")

        return Job(
            title=title, company=company, location=location,
            work_mode="Remoto", link=href, description=desc,
            source="Jobspresso", pub_date=datetime.date.today().isoformat()
        )

    def fetch(self) -> List[Job]:
        cards: List[Dict[str, Any]] = []
        seen_links = set()
        pages = ["https://jobspresso.co/", "https://jobspresso.co/page/2/", "https://jobspresso.co/page/3/"]
        
        for url in pages:
            try:
                resp = self.session.get(url, headers=get_random_headers(), timeout=(3.5, 10.0))
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, "html.parser")
                    job_a_tags = soup.find_all("a", href=lambda h: h and "/job/" in h)
                    for a in job_a_tags:
                        href = a.get("href", "")
                        if not href or href in seen_links or href.endswith("/job/") or href == "https://jobspresso.co/job/":
                            continue
                        
                        parent = a.find_parent("li") or a.find_parent("div", class_=lambda c: c and "job" in str(c).lower())
                        if not parent:
                            continue
                        
                        seen_links.add(href)
                        title_elem = parent.find(class_=lambda c: c and "title" in str(c).lower()) or a
                        title = title_elem.get_text(separator=' ', strip=True) if title_elem else a.get_text(separator=' ', strip=True)
                        if not title:
                            continue
                        
                        if not is_valid_job_offer(href, title):
                            continue
                        
                        comp_elem = parent.find(class_=lambda c: c and "company" in str(c).lower())
                        company = comp_elem.get_text(separator=' ', strip=True) if comp_elem else "Jobspresso Company"
                        
                        loc_elem = parent.find(class_=lambda c: c and "location" in str(c).lower())
                        location = loc_elem.get_text(separator=' ', strip=True) if loc_elem else "Worldwide Remote"
                        
                        summary = parent.get_text(separator=" ", strip=True)
                        cards.append({"title": title, "company": company, "location": location, "link": href, "summary": summary})
            except Exception as e:
                logger.error(f"[Jobspresso Portal] Error at {url}: {e}")

        # Fetch detail pages concurrently
        jobs: List[Job] = []
        if cards:
            with ThreadPoolExecutor(max_workers=6) as executor:
                futs = {executor.submit(self._fetch_detail_page, c): c for c in cards}
                for f in as_completed(futs):
                    try:
                        jobs.append(f.result())
                    except Exception as e:
                        logger.debug(f"[Jobspresso Portal] Error processing job: {e}")

        logger.info(f"[Jobspresso Portal] Fetched {len(jobs)} jobs with full detail parsing.")
        return jobs

