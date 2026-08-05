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

# Non-job documentation / blog / sponsored domains to exclude
NON_JOB_DOMAINS = [
    "aws.amazon.com", "amazon.com/what-is", "wikipedia.org", "medium.com",
    "github.com", "youtube.com", "google.com", "dev.to", "towardsdatascience.com"
]

# Non-AI/Data titles to filter out during ingestion
PRE_FILTER_DISQUALIFIERS = [
    "ui engineer", "ux engineer", "front-end", "frontend", "react", "vue", "angular",
    "electronics engineer", "rf engineer", "hardware", "embedded", "qa tester", "qa engineer",
    "sysadmin", "network engineer", "cybersecurity", "cibersegurança", "salesforce", "sap ",
    "scrum master", "helpdesk", "support technician", "webmaster", "marketing", "social media",
    "growth", "sales", "comercial", "branding", "copywriter", "videógrafo"
]

def is_valid_job_offer(link: str, title: str) -> bool:
    link_lower = link.lower()
    title_lower = title.lower()
    
    # Reject documentation/blog domains
    for domain in NON_JOB_DOMAINS:
        if domain in link_lower:
            return False
            
    # Reject titles that sound like articles or guides
    if any(title_lower.startswith(p) for p in ["what is", "how to", "introduction to", "guide to", "understanding"]):
        return False
        
    # Reject obvious non-AI / non-Data roles at ingestion time
    for disq in PRE_FILTER_DISQUALIFIERS:
        if disq in title_lower:
            return False

    return True

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
            if "remot" in text_content or "teletrabalho" in text_content or "anywhere" in text_content:
                self.work_mode = "Remoto"
            elif "híbrid" in text_content or "hybrid" in text_content:
                self.work_mode = "Híbrido"
            elif "presencial" in text_content or "on-site" in text_content or "onsite" in text_content:
                self.work_mode = "Presencial"
            else:
                self.work_mode = "Presencial / Híbrido"

class LinkedInScraper:
    """Scrapes LinkedIn public guest API for Portugal AI & Data Science jobs strictly posted in the last 24-48 hours."""
    def fetch(self) -> List[Job]:
        jobs = []
        queries = [
            "Junior AI Engineer",
            "Junior Data Scientist",
            "Junior Machine Learning Engineer",
            "Junior Data Engineer",
            "AI Developer",
            "Estágio Inteligência Artificial",
            "Data Science Trainee"
        ]
        seen_links: Set[str] = set()
        for q in queries:
            try:
                # f_TPR=r86400 restricts results to jobs posted in the last 24 hours (86400 seconds)
                url = f"https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords={q.replace(' ', '%20')}&location=Portugal&f_TPR=r86400&start=0"
                resp = requests.get(url, headers=HEADERS, timeout=10)
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, "html.parser")
                    cards = soup.find_all("div", class_="base-card")
                    for card in cards:
                        title_elem = card.find("h3", class_="base-search-card__title") or card.find("h3")
                        link_elem = card.find("a", class_="base-card__full-link") or card.find("a")
                        company_elem = card.find("h4", class_="base-search-card__subtitle") or card.find("h4")
                        loc_elem = card.find("span", class_="job-search-card__location") or card.find("span")
                        time_elem = card.find("time")
                        
                        if not title_elem or not link_elem:
                            continue
                            
                        title = title_elem.get_text(strip=True)
                        raw_link = link_elem.get("href", "")
                        clean_link = raw_link.split("?")[0].rstrip("/")
                        company = company_elem.get_text(strip=True) if company_elem else "Empresa no LinkedIn"
                        location = loc_elem.get_text(strip=True) if loc_elem else "Portugal"
                        
                        # Extract exact publication date from time tag (e.g., datetime="2026-08-04")
                        pub_date = datetime.date.today().isoformat()
                        if time_elem and time_elem.get("datetime"):
                            pub_date = time_elem.get("datetime")[:10]

                        if not is_valid_job_offer(clean_link, title) or clean_link in seen_links:
                            continue
                        seen_links.add(clean_link)
                        
                        # Detail page fetch via guest jobPosting API endpoint
                        desc = f"{title} na {company} em {location}"
                        try:
                            job_id_match = re.search(r"(\d+)$", clean_link)
                            if job_id_match:
                                job_id = job_id_match.group(1)
                                detail_url = f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"
                                detail_resp = requests.get(detail_url, headers=HEADERS, timeout=6)
                                if detail_resp.status_code == 200:
                                    detail_soup = BeautifulSoup(detail_resp.text, "html.parser")
                                    markup = detail_soup.find("div", class_="show-more-less-html__markup")
                                    if markup:
                                        desc = f"{title} - " + markup.get_text(separator=" ", strip=True)
                                    else:
                                        desc = f"{title} - " + detail_soup.get_text(separator=" ", strip=True)
                        except Exception as d_err:
                            logger.debug(f"LinkedIn detail fetch failed for {clean_link}: {d_err}")

                        jobs.append(Job(
                            title=title, company=company, location=location,
                            work_mode="Presencial / Híbrido", link=clean_link, description=desc,
                            source="LinkedIn", pub_date=pub_date
                        ))
            except Exception as e:
                logger.error(f"[LinkedIn Portal] Error fetching '{q}': {e}")

        logger.info(f"[LinkedIn Portal] Fetched {len(jobs)} fresh jobs (last 48h).")
        return jobs

class ITJobsScraper:
    """Scrapes ITJobs.pt portal for Portugal IT, AI & Data Science jobs with full detail body parsing."""
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
                    logger.info(f"[ITJobs.pt API] Fetched {len(jobs)} jobs.")
                    return jobs
            except Exception as e:
                logger.warning(f"[ITJobs.pt API] Error: {e}, falling back to Direct Portal Scraping.")

        search_urls = [
            "https://www.itjobs.pt/emprego?q=data+scientist",
            "https://www.itjobs.pt/emprego?q=machine+learning",
            "https://www.itjobs.pt/emprego?q=inteligencia+artificial",
            "https://www.itjobs.pt/emprego?q=data+engineer",
            "https://www.itjobs.pt/emprego?q=python"
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
                            
                            if not is_valid_job_offer(full_link, title):
                                continue
                                
                            parent = a.find_parent("div", class_="info") or a.find_parent("div")
                            company = "Empresa via ITJobs"
                            location = "Portugal"
                            
                            if parent:
                                company_elem = parent.find("a", class_="company") or parent.find("span", class_="company")
                                if company_elem:
                                    company = company_elem.get_text(strip=True)
                                location_elem = parent.find("span", class_="location") or parent.find("div", class_="location")
                                if location_elem:
                                    location = location_elem.get_text(strip=True)

                            # Fetch full offer detail page text to inspect requirements
                            desc = title
                            try:
                                detail_resp = requests.get(full_link, headers=HEADERS, timeout=8)
                                if detail_resp.status_code == 200:
                                    detail_soup = BeautifulSoup(detail_resp.text, "html.parser")
                                    text_blocks = [elem.get_text(strip=True) for elem in detail_soup.find_all(["p", "li"])]
                                    desc = f"{title} " + " ".join(text_blocks)
                            except Exception as detail_err:
                                logger.debug(f"Could not fetch offer detail page for {full_link}: {detail_err}")

                            jobs.append(Job(
                                title=title, company=company, location=location,
                                work_mode="Presencial / Híbrido", link=full_link, description=desc,
                                source="ITJobs.pt", pub_date=datetime.date.today().isoformat()
                            ))

            logger.info(f"[ITJobs.pt Portal] Fetched {len(jobs)} jobs with full detail body parsing.")
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
                    link = item.get("url", "")
                    
                    if not is_valid_job_offer(link, title):
                        continue

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
                    link = item.get("url", "")
                    
                    if not is_valid_job_offer(link, title):
                        continue

                    company = item.get("company_name", "Remotive Company")
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
                    link = item.get("url", "")
                    
                    if not is_valid_job_offer(link, title):
                        continue

                    company = item.get("company_name", "Arbeitnow Company")
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
                
                if not is_valid_job_offer(link, title):
                    continue

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
                if isinstance(items, list) and len(items) > 1:
                    for item in items[1:]:
                        if isinstance(item, dict):
                            title = item.get("position", "")
                            link = item.get("url", "") or item.get("apply_url", "")
                            
                            if not is_valid_job_offer(link, title):
                                continue

                            company = item.get("company", "RemoteOK Company")
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

class CargaDeTrabalhosScraper:
    """Scrapes Carga de Trabalhos portal for Portuguese tech & AI jobs."""
    def fetch(self) -> List[Job]:
        jobs = []
        queries = ["data", "python", "inteligencia", "machine learning", "ai"]
        seen_links: Set[str] = set()
        
        for q in queries:
            try:
                url = f"https://cargadetrabalhos.pt/?s={q}"
                resp = requests.get(url, headers=HEADERS, timeout=10)
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, "html.parser")
                    articles = soup.find_all("article")
                    for art in articles:
                        a_tag = art.find("a")
                        if not a_tag:
                            continue
                        link = a_tag.get("href", "").split("?")[0].rstrip("/")
                        if "/ofertas/" not in link or link in seen_links:
                            continue
                        
                        title = a_tag.get_text(strip=True)
                        if not title or not is_valid_job_offer(link, title):
                            continue
                        seen_links.add(link)
                        
                        text = art.get_text(separator=" ", strip=True)
                        
                        # Fetch detail page
                        try:
                            det_resp = requests.get(link, headers=HEADERS, timeout=5)
                            if det_resp.status_code == 200:
                                det_soup = BeautifulSoup(det_resp.text, "html.parser")
                                
                                # Check if job is closed/expired on Carga de Trabalhos
                                is_closed = bool(det_soup.find(class_=lambda c: c and ("closed-job" in c or "job-closed" in c)))
                                if is_closed:
                                    text = f"{title} - Oferta Expirada"
                                else:
                                    main_div = det_soup.find("div", class_="noo-main") or det_soup.find("div", class_="entry-content")
                                    if main_div:
                                        text = f"{title} - " + main_div.get_text(separator=" ", strip=True)
                        except Exception:
                            pass

                        jobs.append(Job(
                            title=title, company="Empresa via Carga de Trabalhos", location="Portugal",
                            work_mode="Presencial / Híbrido", link=link, description=text,
                            source="Carga de Trabalhos", pub_date=datetime.date.today().isoformat()
                        ))
            except Exception as e:
                logger.error(f"[Carga de Trabalhos Portal] Error querying '{q}': {e}")
                
        logger.info(f"[Carga de Trabalhos Portal] Fetched {len(jobs)} jobs.")
        return jobs

class JobIngestionPipeline:
    """Aggregates all structured job portal scrapers including LinkedIn and deduplicates jobs."""
    def __init__(self, itjobs_api_key: str = ""):
        self.linkedin_scraper = LinkedInScraper()
        self.itjobs_scraper = ITJobsScraper()
        self.landing_scraper = LandingJobsScraper()
        self.remotive_scraper = RemotiveScraper()
        self.arbeitnow_scraper = ArbeitnowScraper()
        self.wwr_scraper = WeWorkRemotelyScraper()
        self.remoteok_scraper = RemoteOKScraper()
        self.carga_scraper = CargaDeTrabalhosScraper()
        self.itjobs_api_key = itjobs_api_key

    def run(self) -> List[Job]:
        logger.info("🚀 Starting job portal ingestion pipeline (LinkedIn + ITJobs + Carga de Trabalhos + Global Portals)...")
        all_jobs: List[Job] = []

        all_jobs.extend(self.linkedin_scraper.fetch())
        all_jobs.extend(self.itjobs_scraper.fetch(self.itjobs_api_key))
        all_jobs.extend(self.carga_scraper.fetch())
        all_jobs.extend(self.landing_scraper.fetch())
        all_jobs.extend(self.remotive_scraper.fetch())
        all_jobs.extend(self.arbeitnow_scraper.fetch())
        all_jobs.extend(self.wwr_scraper.fetch())
        all_jobs.extend(self.remoteok_scraper.fetch())

        # Deduplication using job_id hash
        unique_jobs: Dict[str, Job] = {}
        for j in all_jobs:
            if j.job_id not in unique_jobs:
                unique_jobs[j.job_id] = j

        final_jobs = list(unique_jobs.values())
        logger.info(f"✅ Ingestion complete. Total raw: {len(all_jobs)} | Unique portal job offers: {len(final_jobs)}")
        return final_jobs
