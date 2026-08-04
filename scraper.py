import hashlib
import logging
import re
import datetime
from dataclasses import dataclass
from typing import List, Dict, Set, Optional
import requests
from bs4 import BeautifulSoup
import feedparser

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("Scraper")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

@dataclass
class Job:
    title: str
    company: str
    location: str
    work_mode: str  # Remote, Hybrid, On-site, Presencial / Híbrido
    link: str
    description: str
    source: str
    pub_date: str
    iefp_mentioned: bool = False
    job_id: str = ""

    def __post_init__(self):
        if not self.job_id:
            raw_str = f"{self.title.lower().strip()}_{self.company.lower().strip()}_{self.link.strip()}"
            self.job_id = hashlib.sha256(raw_str.encode('utf-8')).hexdigest()[:16]
        
        text_content = f"{self.title} {self.description}".lower()
        if any(term in text_content for term in ["iefp", "ativar.pt", "ativar pt", "estágio profissional", "estagio profissional"]):
            self.iefp_mentioned = True
            
        if self.work_mode.lower() in ["unknown", "n/a", "não especificado", ""]:
            if "remot" in text_content or "teletrabalho" in text_content:
                self.work_mode = "Remoto"
            elif "híbrid" in text_content or "hybrid" in text_content:
                self.work_mode = "Híbrido"
            elif "presencial" in text_content or "on-site" in text_content or "onsite" in text_content:
                self.work_mode = "Presencial"
            else:
                self.work_mode = "Presencial / Híbrido"

class ITJobsScraper:
    """Scrapes ITJobs.pt portal for Portugal IT, AI & Data Science jobs."""
    def fetch(self, api_key: str = "") -> List[Job]:
        jobs = []
        if api_key:
            try:
                url = f"https://api.itjobs.pt/2/job/search.json?api_key={api_key}&limit=50"
                resp = requests.get(url, headers=HEADERS, timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    for item in data.get("results", []):
                        title = item.get("title", "")
                        company = item.get("company", {}).get("name", "Empresa ITJobs")
                        body = item.get("body", "")
                        link = f"https://www.itjobs.pt/oferta/{item.get('id')}"
                        locations = ", ".join([loc.get("name", "") for loc in item.get("locations", [])])
                        pub_date = item.get("created_at", datetime.date.today().isoformat())
                        jobs.append(Job(
                            title=title, company=company, location=locations or "Portugal",
                            work_mode="Presencial / Híbrido", link=link, description=body,
                            source="ITJobs.pt", pub_date=pub_date
                        ))
                    logger.info(f"[ITJobs.pt API] Fetched {len(jobs)} jobs.")
                    return jobs
            except Exception as e:
                logger.warning(f"[ITJobs.pt API] Error: {e}, falling back to Direct Portal Scraping.")

        # Direct Portal Scraping for ITJobs.pt (AI, Data Science, ML & Python focus)
        search_urls = [
            "https://www.itjobs.pt/emprego?q=data+scientist",
            "https://www.itjobs.pt/emprego?q=machine+learning",
            "https://www.itjobs.pt/emprego?q=inteligencia+artificial",
            "https://www.itjobs.pt/emprego?q=python",
            "https://www.itjobs.pt/emprego?q=data"
        ]
        
        seen_links = set()
        try:
            for url in search_urls:
                resp = requests.get(url, headers=HEADERS, timeout=10)
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, "html.parser")
                    title_anchors = soup.find_all("a", class_="title")
                    for a in title_anchors:
                        href = a.get("href", "")
                        if href and href not in seen_links and "/oferta/" in href:
                            seen_links.add(href)
                            full_link = f"https://www.itjobs.pt{href}" if href.startswith("/") else href
                            title = a.get_text(strip=True)
                            
                            parent = a.find_parent("div", class_="info") or a.find_parent("div")
                            company = "Empresa via ITJobs"
                            desc = title
                            location = "Portugal"
                            
                            if parent:
                                company_elem = parent.find("a", class_="company") or parent.find("span", class_="company")
                                if company_elem:
                                    company = company_elem.get_text(strip=True)
                                location_elem = parent.find("span", class_="location") or parent.find("div", class_="location")
                                if location_elem:
                                    location = location_elem.get_text(strip=True)
                                    
                            jobs.append(Job(
                                title=title, company=company, location=location,
                                work_mode="Presencial / Híbrido", link=full_link, description=desc,
                                source="ITJobs.pt", pub_date=datetime.date.today().isoformat()
                            ))

            logger.info(f"[ITJobs.pt Portal] Fetched {len(jobs)} jobs.")
        except Exception as e:
            logger.error(f"[ITJobs.pt Portal] Error: {e}")
        return jobs

class LandingJobsScraper:
    """Scrapes Landing.jobs portal via public API."""
    def fetch(self) -> List[Job]:
        jobs = []
        url = "https://landing.jobs/api/v1/jobs"
        try:
            resp = requests.get(url, headers=HEADERS, timeout=10)
            if resp.status_code == 200:
                items = resp.json()
                for item in items:
                    title = item.get("title", "")
                    company = item.get("company_name", "Landing.jobs Company")
                    link = item.get("url", "")
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
                logger.info(f"[Landing.jobs Portal] Fetched {len(jobs)} jobs.")
        except Exception as e:
            logger.error(f"[Landing.jobs Portal] Error: {e}")
        return jobs

class RemotiveScraper:
    """Scrapes Remotive.com portal API for remote AI & Data Science jobs."""
    def fetch(self) -> List[Job]:
        jobs = []
        url = "https://remotive.com/api/remote-jobs?category=data"
        try:
            resp = requests.get(url, headers=HEADERS, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                for item in data.get("jobs", []):
                    title = item.get("title", "")
                    company = item.get("company_name", "Remotive Company")
                    link = item.get("url", "")
                    location = item.get("candidate_required_location", "Worldwide Remote")
                    desc = BeautifulSoup(item.get("description", ""), "html.parser").get_text(strip=True)
                    pub_date = item.get("publication_date", datetime.date.today().isoformat())[:10]
                    
                    jobs.append(Job(
                        title=title, company=company, location=location,
                        work_mode="Remoto", link=link, description=desc,
                        source="Remotive", pub_date=pub_date
                    ))
                logger.info(f"[Remotive Portal] Fetched {len(jobs)} jobs.")
        except Exception as e:
            logger.error(f"[Remotive Portal] Error: {e}")
        return jobs

class ArbeitnowScraper:
    """Scrapes Arbeitnow European job portal API."""
    def fetch(self) -> List[Job]:
        jobs = []
        url = "https://www.arbeitnow.com/api/job-board-api"
        try:
            resp = requests.get(url, headers=HEADERS, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                for item in data.get("data", []):
                    title = item.get("title", "")
                    company = item.get("company_name", "Arbeitnow Company")
                    link = item.get("url", "")
                    location = item.get("location", "Europe / Remote")
                    remote = item.get("remote", False)
                    work_mode = "Remoto" if remote else "Presencial / Híbrido"
                    desc = BeautifulSoup(item.get("description", ""), "html.parser").get_text(strip=True)
                    pub_date = datetime.date.fromtimestamp(item.get("created_at", int(datetime.datetime.now().timestamp()))).isoformat()
                    
                    jobs.append(Job(
                        title=title, company=company, location=location,
                        work_mode=work_mode, link=link, description=desc,
                        source="Arbeitnow", pub_date=pub_date
                    ))
                logger.info(f"[Arbeitnow Portal] Fetched {len(jobs)} jobs.")
        except Exception as e:
            logger.error(f"[Arbeitnow Portal] Error: {e}")
        return jobs

class WeWorkRemotelyScraper:
    """Scrapes WeWorkRemotely job portal RSS feed."""
    def fetch(self) -> List[Job]:
        jobs = []
        rss_url = "https://weworkremotely.com/categories/remote-back-end-programming-jobs.rss"
        try:
            feed = feedparser.parse(rss_url)
            for entry in feed.entries:
                title = entry.get("title", "")
                link = entry.get("link", "")
                desc = BeautifulSoup(entry.get("summary", ""), "html.parser").get_text(strip=True)
                pub_date = entry.get("published", datetime.date.today().isoformat())
                
                company = "WeWorkRemotely Company"
                if ":" in title:
                    parts = title.split(":", 1)
                    company = parts[0].strip()
                    title = parts[1].strip()
                
                jobs.append(Job(
                    title=title, company=company, location="Remote International",
                    work_mode="Remoto", link=link, description=desc,
                    source="WeWorkRemotely", pub_date=pub_date
                ))
            logger.info(f"[WeWorkRemotely Portal] Fetched {len(jobs)} jobs.")
        except Exception as e:
            logger.error(f"[WeWorkRemotely Portal] Error: {e}")
        return jobs

class RemoteOKScraper:
    """Scrapes RemoteOK portal API for remote data & AI roles."""
    def fetch(self) -> List[Job]:
        jobs = []
        url = "https://remoteok.com/api?tag=data"
        try:
            resp = requests.get(url, headers=HEADERS, timeout=10)
            if resp.status_code == 200:
                items = resp.json()
                # First element in RemoteOK API response is legal metadata dict
                if isinstance(items, list) and len(items) > 1:
                    for item in items[1:]:
                        if isinstance(item, dict):
                            title = item.get("position", "")
                            company = item.get("company", "RemoteOK Company")
                            link = item.get("url", "") or item.get("apply_url", "")
                            location = item.get("location", "Worldwide Remote")
                            desc = BeautifulSoup(item.get("description", ""), "html.parser").get_text(strip=True)
                            pub_date = item.get("date", datetime.date.today().isoformat())[:10]
                            
                            jobs.append(Job(
                                title=title, company=company, location=location,
                                work_mode="Remoto", link=link, description=desc,
                                source="RemoteOK", pub_date=pub_date
                            ))
                logger.info(f"[RemoteOK Portal] Fetched {len(jobs)} jobs.")
        except Exception as e:
            logger.error(f"[RemoteOK Portal] Error: {e}")
        return jobs

class JobIngestionPipeline:
    """Aggregates all structured job portal scrapers and deduplicates jobs."""
    def __init__(self, itjobs_api_key: str = ""):
        self.itjobs_scraper = ITJobsScraper()
        self.landing_scraper = LandingJobsScraper()
        self.remotive_scraper = RemotiveScraper()
        self.arbeitnow_scraper = ArbeitnowScraper()
        self.wwr_scraper = WeWorkRemotelyScraper()
        self.remoteok_scraper = RemoteOKScraper()
        self.itjobs_api_key = itjobs_api_key

    def run(self) -> List[Job]:
        logger.info("🚀 Starting job portal ingestion pipeline (100% Direct Portals)...")
        all_jobs: List[Job] = []

        # 1. ITJobs.pt (Portugal IT & AI Portal)
        all_jobs.extend(self.itjobs_scraper.fetch(self.itjobs_api_key))
        
        # 2. Landing.jobs (Portugal & Europe Tech Portal)
        all_jobs.extend(self.landing_scraper.fetch())
        
        # 3. Remotive.com (Global Remote Tech & AI Portal)
        all_jobs.extend(self.remotive_scraper.fetch())
        
        # 4. Arbeitnow (Europe & Remote Tech Portal)
        all_jobs.extend(self.arbeitnow_scraper.fetch())
        
        # 5. WeWorkRemotely (Remote Tech Portal)
        all_jobs.extend(self.wwr_scraper.fetch())

        # 6. RemoteOK (Global Remote AI & Data Portal)
        all_jobs.extend(self.remoteok_scraper.fetch())

        # Deduplication using job_id hash
        unique_jobs: Dict[str, Job] = {}
        for j in all_jobs:
            if j.job_id not in unique_jobs:
                unique_jobs[j.job_id] = j

        final_jobs = list(unique_jobs.values())
        logger.info(f"✅ Ingestion complete. Total raw: {len(all_jobs)} | Unique portal job offers: {len(final_jobs)}")
        return final_jobs
