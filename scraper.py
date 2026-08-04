import hashlib
import logging
import re
import datetime
from dataclasses import dataclass, asdict
from typing import List, Dict, Set, Optional
import requests
from bs4 import BeautifulSoup
import feedparser

try:
    from duckduckgo_search import DDGS
    DDG_AVAILABLE = True
except ImportError:
    DDG_AVAILABLE = False

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
    work_mode: str  # Remote, Hybrid, On-site, Unknown
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
        
        # Check IEFP / ATIVAR.pt mention in title or description
        text_content = f"{self.title} {self.description}".lower()
        if any(term in text_content for term in ["iefp", "ativar.pt", "ativar pt", "estágio profissional", "estagio profissional"]):
            self.iefp_mentioned = True
            
        # Detect work mode if unknown
        if self.work_mode.lower() in ["unknown", "n/a", ""]:
            if "remot" in text_content or "teletrabalho" in text_content:
                self.work_mode = "Remoto"
            elif "híbrid" in text_content or "hybrid" in text_content:
                self.work_mode = "Híbrido"
            elif "presencial" in text_content or "on-site" in text_content or "onsite" in text_content:
                self.work_mode = "Presencial"
            else:
                self.work_mode = "Não especificado"

class ITJobsScraper:
    """Scrapes ITJobs.pt via API (if key provided) or direct web scraping of ITJobs.pt/emprego."""
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
                        company = item.get("company", {}).get("name", "N/A")
                        body = item.get("body", "")
                        link = f"https://www.itjobs.pt/oferta/{item.get('id')}"
                        locations = ", ".join([loc.get("name", "") for loc in item.get("locations", [])])
                        pub_date = item.get("created_at", datetime.date.today().isoformat())
                        jobs.append(Job(
                            title=title, company=company, location=locations or "Portugal",
                            work_mode="Unknown", link=link, description=body,
                            source="ITJobs.pt", pub_date=pub_date
                        ))
                    logger.info(f"[ITJobs.pt API] Fetched {len(jobs)} jobs.")
                    return jobs
            except Exception as e:
                logger.warning(f"[ITJobs.pt API] Error: {e}, falling back to Web Scraping.")

        # Direct Web Scraping Fallback for ITJobs.pt
        search_urls = [
            "https://www.itjobs.pt/emprego",
            "https://www.itjobs.pt/emprego?q=data",
            "https://www.itjobs.pt/emprego?q=python",
            "https://www.itjobs.pt/emprego?q=junior"
        ]
        
        seen_links = set()
        try:
            for url in search_urls:
                resp = requests.get(url, headers=HEADERS, timeout=10)
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, "html.parser")
                    job_elements = soup.find_all("div", class_=re.compile(r"list-item|job-item|offer-item|list-row"))
                    if not job_elements:
                        # Fallback to finding title links directly
                        title_anchors = soup.find_all("a", class_="title")
                        for a in title_anchors:
                            href = a.get("href", "")
                            if href and href not in seen_links:
                                seen_links.add(href)
                                full_link = f"https://www.itjobs.pt{href}" if href.startswith("/") else href
                                title = a.get_text(strip=True)
                                
                                # Find parent container for company & location info
                                parent = a.find_parent("div", class_="info") or a.find_parent("div")
                                company = "N/A"
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
                                    work_mode="Unknown", link=full_link, description=desc,
                                    source="ITJobs.pt Web", pub_date=datetime.date.today().isoformat()
                                ))

            logger.info(f"[ITJobs.pt Web] Fetched {len(jobs)} jobs.")
        except Exception as e:
            logger.error(f"[ITJobs.pt Web] Error: {e}")
        return jobs

class LandingJobsScraper:
    """Scrapes Landing.jobs via public API."""
    def fetch(self) -> List[Job]:
        jobs = []
        url = "https://landing.jobs/api/v1/jobs"
        try:
            resp = requests.get(url, headers=HEADERS, timeout=10)
            if resp.status_code == 200:
                items = resp.json()
                for item in items:
                    title = item.get("title", "")
                    company = item.get("company_name", "N/A")
                    link = item.get("url", "")
                    location = item.get("location", "Portugal / EU")
                    remote = item.get("remote", False)
                    work_mode = "Remoto" if remote else "Híbrido / Presencial"
                    desc = item.get("role_description", "") or item.get("summary", "")
                    pub_date = item.get("published_at", datetime.date.today().isoformat())
                    
                    jobs.append(Job(
                        title=title, company=company, location=location,
                        work_mode=work_mode, link=link, description=desc,
                        source="Landing.jobs", pub_date=str(pub_date)[:10]
                    ))
                logger.info(f"[Landing.jobs API] Fetched {len(jobs)} jobs.")
        except Exception as e:
            logger.error(f"[Landing.jobs API] Error: {e}")
        return jobs

class RemotiveScraper:
    """Scrapes Remotive.com public API for remote AI & Data Science jobs."""
    def fetch(self) -> List[Job]:
        jobs = []
        url = "https://remotive.com/api/remote-jobs?category=data"
        try:
            resp = requests.get(url, headers=HEADERS, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                for item in data.get("jobs", []):
                    title = item.get("title", "")
                    company = item.get("company_name", "N/A")
                    link = item.get("url", "")
                    location = item.get("candidate_required_location", "Worldwide Remote")
                    desc = BeautifulSoup(item.get("description", ""), "html.parser").get_text(strip=True)
                    pub_date = item.get("publication_date", datetime.date.today().isoformat())[:10]
                    
                    jobs.append(Job(
                        title=title, company=company, location=location,
                        work_mode="Remoto", link=link, description=desc,
                        source="Remotive", pub_date=pub_date
                    ))
                logger.info(f"[Remotive API] Fetched {len(jobs)} jobs.")
        except Exception as e:
            logger.error(f"[Remotive API] Error: {e}")
        return jobs

class ArbeitnowScraper:
    """Scrapes Arbeitnow public API for European & Remote tech jobs."""
    def fetch(self) -> List[Job]:
        jobs = []
        url = "https://www.arbeitnow.com/api/job-board-api"
        try:
            resp = requests.get(url, headers=HEADERS, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                for item in data.get("data", []):
                    title = item.get("title", "")
                    company = item.get("company_name", "N/A")
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
                logger.info(f"[Arbeitnow API] Fetched {len(jobs)} jobs.")
        except Exception as e:
            logger.error(f"[Arbeitnow API] Error: {e}")
        return jobs

class WeWorkRemotelyScraper:
    """Scrapes WeWorkRemotely RSS feed for remote roles."""
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
                
                company = "N/A"
                if ":" in title:
                    parts = title.split(":", 1)
                    company = parts[0].strip()
                    title = parts[1].strip()
                
                jobs.append(Job(
                    title=title, company=company, location="Remote International",
                    work_mode="Remoto", link=link, description=desc,
                    source="WeWorkRemotely", pub_date=pub_date
                ))
            logger.info(f"[WeWorkRemotely RSS] Fetched {len(jobs)} jobs.")
        except Exception as e:
            logger.error(f"[WeWorkRemotely RSS] Error: {e}")
        return jobs

class DuckDuckGoJobScraper:
    """Targeted search queries via DuckDuckGo for LinkedIn, Indeed, Glassdoor & Tech Careers."""
    def fetch(self, target_queries: List[str]) -> List[Job]:
        jobs = []
        if not DDG_AVAILABLE:
            logger.warning("[DuckDuckGo] duckduckgo_search package not installed or available.")
            return jobs
            
        try:
            with DDGS() as ddgs:
                for query in target_queries:
                    try:
                        results = list(ddgs.text(query, max_results=10))
                        for r in results:
                            title = r.get("title", "")
                            link = r.get("href", "")
                            snippet = r.get("body", "")
                            
                            # Estimate company from snippet or title
                            company = "Empresa via Web Search"
                            if " | " in title:
                                parts = title.split(" | ")
                                title = parts[0]
                                company = parts[1]
                            elif " - " in title:
                                parts = title.split(" - ")
                                title = parts[0]
                                company = parts[1]

                            jobs.append(Job(
                                title=title, company=company, location="Portugal / Remoto",
                                work_mode="Unknown", link=link, description=snippet,
                                source="DuckDuckGo Search", pub_date=datetime.date.today().isoformat()
                            ))
                    except Exception as q_err:
                        logger.warning(f"[DuckDuckGo Query Error] {query}: {q_err}")
            logger.info(f"[DuckDuckGo Search] Fetched {len(jobs)} job search results.")
        except Exception as e:
            logger.error(f"[DuckDuckGo Search] Error: {e}")
        return jobs

class JobIngestionPipeline:
    """Aggregates all scrapers and deduplicates jobs."""
    def __init__(self, itjobs_api_key: str = ""):
        self.itjobs_scraper = ITJobsScraper()
        self.landing_scraper = LandingJobsScraper()
        self.remotive_scraper = RemotiveScraper()
        self.arbeitnow_scraper = ArbeitnowScraper()
        self.wwr_scraper = WeWorkRemotelyScraper()
        self.ddg_scraper = DuckDuckGoJobScraper()
        self.itjobs_api_key = itjobs_api_key

    def run(self) -> List[Job]:
        logger.info("🚀 Starting multi-source job ingestion pipeline...")
        all_jobs: List[Job] = []

        # 1. ITJobs.pt
        all_jobs.extend(self.itjobs_scraper.fetch(self.itjobs_api_key))
        
        # 2. Landing.jobs
        all_jobs.extend(self.landing_scraper.fetch())
        
        # 3. Remotive.com
        all_jobs.extend(self.remotive_scraper.fetch())
        
        # 4. Arbeitnow
        all_jobs.extend(self.arbeitnow_scraper.fetch())
        
        # 5. WeWorkRemotely
        all_jobs.extend(self.wwr_scraper.fetch())

        # 6. Targeted DuckDuckGo Web Searches (LinkedIn, Indeed, Glassdoor, IEFP)
        target_queries = [
            '"Junior AI Engineer" site:linkedin.com/jobs',
            '"Junior Data Scientist" site:linkedin.com/jobs',
            '"Junior Machine Learning Engineer" site:linkedin.com/jobs',
            '"AI Engineer" IEFP Portugal',
            '"Data Scientist" IEFP Portugal',
            '"Estágio" "AI Engineer" OR "Data Scientist" Portugal',
            '"RAG Developer" OR "NLP Engineer" Portugal OR Remote',
            '"Junior Data Scientist" remote Europe',
            '"Junior AI Engineer" remote Europe',
            '"Entry Level" "Data Scientist" remote',
        ]
        all_jobs.extend(self.ddg_scraper.fetch(target_queries))

        # Deduplication using job_id hash
        unique_jobs: Dict[str, Job] = {}
        for j in all_jobs:
            if j.job_id not in unique_jobs:
                unique_jobs[j.job_id] = j

        final_jobs = list(unique_jobs.values())
        logger.info(f"✅ Ingestion complete. Total raw: {len(all_jobs)} | Unique after deduplication: {len(final_jobs)}")
        return final_jobs
