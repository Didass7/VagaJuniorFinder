import hashlib
import logging
import re
import datetime
import random
import time
from dataclasses import dataclass
from typing import List, Dict, Set, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry
from bs4 import BeautifulSoup
import feedparser

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("Scraper")

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15"
]

def get_random_headers() -> Dict[str, str]:
    """Generates realistic HTTP headers with rotated User-Agent to prevent scraping blocks."""
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,pt-PT;q=0.8,pt;q=0.7",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }

def get_session(pool_size: int = 25) -> requests.Session:
    """Returns a requests.Session configured with automatic retries, exponential backoff, and HTTP connection pooling."""
    session = requests.Session()
    
    # Configure retry logic for HTTP 429 (Rate Limit) and server errors (500, 502, 503, 504)
    retries = Retry(
        total=3,
        backoff_factor=1.0,  # Delays: 1s, 2s, 4s...
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
        raise_on_status=False
    )
    
    adapter = HTTPAdapter(pool_connections=pool_size, pool_maxsize=pool_size, max_retries=retries)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.headers.update(get_random_headers())
    return session

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
    """Scrapes LinkedIn public guest API for Portugal AI & Data Science jobs strictly posted in the last 24-48 hours concurrently."""
    def __init__(self, session: Optional[requests.Session] = None):
        self.session = session or get_session()

    def _fetch_query_cards(self, query: str) -> List[Dict]:
        cards_data = []
        try:
            url = f"https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords={query.replace(' ', '%20')}&location=Portugal&f_TPR=r86400&start=0"
            resp = self.session.get(url, headers=get_random_headers(), timeout=10)
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
                    
                    pub_date = datetime.date.today().isoformat()
                    if time_elem and time_elem.get("datetime"):
                        pub_date = time_elem.get("datetime")[:10]

                    if is_valid_job_offer(clean_link, title):
                        cards_data.append({
                            "title": title, "clean_link": clean_link,
                            "company": company, "location": location,
                            "pub_date": pub_date
                        })
            elif resp.status_code == 429:
                logger.warning(f"[LinkedIn Portal] Rate limit (429) hit for search query: '{query}'")
        except Exception as e:
            logger.error(f"[LinkedIn Portal] Error fetching '{query}': {e}")
        return cards_data

    def _fetch_detail_job(self, card_info: Dict) -> Job:
        title = card_info["title"]
        clean_link = card_info["clean_link"]
        company = card_info["company"]
        location = card_info["location"]
        pub_date = card_info["pub_date"]
        
        desc = f"{title} na {company} em {location}"
        try:
            job_id_match = re.search(r"(\d+)$", clean_link)
            if job_id_match:
                job_id = job_id_match.group(1)
                detail_url = f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"
                
                # Polite jitter delay to prevent burst rate-limiting
                time.sleep(random.uniform(0.05, 0.2))
                
                detail_resp = self.session.get(detail_url, headers=get_random_headers(), timeout=6)
                if detail_resp.status_code == 200:
                    detail_soup = BeautifulSoup(detail_resp.text, "html.parser")
                    markup = detail_soup.find("div", class_="show-more-less-html__markup")
                    if markup:
                        desc = f"{title} - " + markup.get_text(separator=" ", strip=True)
                    else:
                        desc = f"{title} - " + detail_soup.get_text(separator=" ", strip=True)
                elif detail_resp.status_code == 429:
                    logger.warning(f"[LinkedIn Portal] Rate limit (429) for detail job ID: {job_id}")
        except Exception as d_err:
            logger.debug(f"LinkedIn detail fetch failed for {clean_link}: {d_err}")

        return Job(
            title=title, company=company, location=location,
            work_mode="Presencial / Híbrido", link=clean_link, description=desc,
            source="LinkedIn", pub_date=pub_date
        )

    def fetch(self) -> List[Job]:
        queries = [
            "Junior AI Engineer",
            "Junior Data Scientist",
            "Junior Machine Learning Engineer",
            "Junior Data Engineer",
            "AI Developer",
            "Estágio Inteligência Artificial",
            "Data Science Trainee"
        ]
        
        # 1. Fetch cards for all queries concurrently
        all_cards: List[Dict] = []
        seen_links: Set[str] = set()
        with ThreadPoolExecutor(max_workers=min(len(queries), 7)) as executor:
            future_to_query = {executor.submit(self._fetch_query_cards, q): q for q in queries}
            for future in as_completed(future_to_query):
                res = future.result()
                for card in res:
                    if card["clean_link"] not in seen_links:
                        seen_links.add(card["clean_link"])
                        all_cards.append(card)

        # 2. Fetch job details concurrently
        jobs: List[Job] = []
        if all_cards:
            with ThreadPoolExecutor(max_workers=10) as executor:
                future_to_card = {executor.submit(self._fetch_detail_job, c): c for c in all_cards}
                for future in as_completed(future_to_card):
                    try:
                        jobs.append(future.result())
                    except Exception as err:
                        logger.debug(f"[LinkedIn Portal] Error processing detail card: {err}")

        logger.info(f"[LinkedIn Portal] Fetched {len(jobs)} fresh jobs (last 48h) concurrently.")
        return jobs

class ITJobsScraper:
    """Scrapes ITJobs.pt portal for Portugal IT, AI & Data Science jobs with full detail body parsing."""
    def __init__(self, session: Optional[requests.Session] = None):
        self.session = session or get_session()

    def _fetch_search_url_cards(self, url: str) -> List[Dict]:
        cards = []
        try:
            resp = self.session.get(url, headers=get_random_headers(), timeout=10)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                title_anchors = soup.find_all("a", class_="title")
                for a in title_anchors:
                    href = a.get("href", "")
                    if href and "/oferta/" in href:
                        full_link = f"https://www.itjobs.pt{href}" if href.startswith("/") else href
                        title = a.get_text(strip=True)
                        if is_valid_job_offer(full_link, title):
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
            detail_resp = self.session.get(full_link, headers=get_random_headers(), timeout=8)
            if detail_resp.status_code == 200:
                detail_soup = BeautifulSoup(detail_resp.text, "html.parser")
                text_blocks = [elem.get_text(strip=True) for elem in detail_soup.find_all(["p", "li"])]
                desc = f"{title} " + " ".join(text_blocks)
        except Exception as detail_err:
            logger.debug(f"Could not fetch offer detail page for {full_link}: {detail_err}")

        return Job(
            title=title, company=company, location=location,
            work_mode="Presencial / Híbrido", link=full_link, description=desc,
            source="ITJobs.pt", pub_date=datetime.date.today().isoformat()
        )

    def fetch(self, api_key: str = "") -> List[Job]:
        jobs = []
        if api_key:
            try:
                url = f"https://api.itjobs.pt/2/job/search.json?api_key={api_key}&limit=50"
                resp = self.session.get(url, headers=get_random_headers(), timeout=10)
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

        logger.info(f"[ITJobs.pt Portal] Fetched {len(jobs)} jobs with full detail body parsing concurrently.")
        return jobs

class LandingJobsScraper:
    """Scrapes Landing.jobs portal via public API."""
    def __init__(self, session: Optional[requests.Session] = None):
        self.session = session or get_session()

    def fetch(self) -> List[Job]:
        jobs = []
        url = "https://landing.jobs/api/v1/jobs"
        try:
            resp = self.session.get(url, headers=get_random_headers(), timeout=10)
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
    def __init__(self, session: Optional[requests.Session] = None):
        self.session = session or get_session()

    def fetch(self) -> List[Job]:
        jobs = []
        url = "https://remotive.com/api/remote-jobs?category=data"
        try:
            resp = self.session.get(url, headers=get_random_headers(), timeout=10)
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
    def __init__(self, session: Optional[requests.Session] = None):
        self.session = session or get_session()

    def fetch(self) -> List[Job]:
        jobs = []
        url = "https://www.arbeitnow.com/api/job-board-api"
        try:
            resp = self.session.get(url, headers=get_random_headers(), timeout=10)
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
    def __init__(self, session: Optional[requests.Session] = None):
        self.session = session or get_session()

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
    def __init__(self, session: Optional[requests.Session] = None):
        self.session = session or get_session()

    def fetch(self) -> List[Job]:
        jobs = []
        url = "https://remoteok.com/api?tag=data"
        try:
            resp = self.session.get(url, headers=get_random_headers(), timeout=10)
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
    def __init__(self, session: Optional[requests.Session] = None):
        self.session = session or get_session()

    def _fetch_query_articles(self, q: str) -> List[Dict]:
        cards = []
        try:
            url = f"https://cargadetrabalhos.pt/?s={q}"
            resp = self.session.get(url, headers=get_random_headers(), timeout=10)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                articles = soup.find_all("article")
                for art in articles:
                    a_tag = art.find("a")
                    if not a_tag:
                        continue
                    link = a_tag.get("href", "").split("?")[0].rstrip("/")
                    if "/ofertas/" not in link:
                        continue
                    
                    title = a_tag.get_text(strip=True)
                    if not title or not is_valid_job_offer(link, title):
                        continue
                    
                    text = art.get_text(separator=" ", strip=True)
                    cards.append({"title": title, "link": link, "summary_text": text})
        except Exception as e:
            logger.error(f"[Carga de Trabalhos Portal] Error querying '{q}': {e}")
        return cards

    def _fetch_detail_page(self, card_info: Dict) -> Job:
        title = card_info["title"]
        link = card_info["link"]
        text = card_info["summary_text"]

        try:
            det_resp = self.session.get(link, headers=get_random_headers(), timeout=5)
            if det_resp.status_code == 200:
                det_soup = BeautifulSoup(det_resp.text, "html.parser")
                is_closed = bool(det_soup.find(class_=lambda c: c and ("closed-job" in c or "job-closed" in c)))
                if is_closed:
                    text = f"{title} - Oferta Expirada"
                else:
                    main_div = det_soup.find("div", class_="noo-main") or det_soup.find("div", class_="entry-content")
                    if main_div:
                        text = f"{title} - " + main_div.get_text(separator=" ", strip=True)
        except Exception:
            pass

        return Job(
            title=title, company="Empresa via Carga de Trabalhos", location="Portugal",
            work_mode="Presencial / Híbrido", link=link, description=text,
            source="Carga de Trabalhos", pub_date=datetime.date.today().isoformat()
        )

    def fetch(self) -> List[Job]:
        queries = ["data", "python", "inteligencia", "machine learning", "ai"]
        cards_to_fetch = []
        seen_links = set()

        # 1. Query search pages concurrently
        with ThreadPoolExecutor(max_workers=min(len(queries), 5)) as executor:
            future_to_q = {executor.submit(self._fetch_query_articles, q): q for q in queries}
            for future in as_completed(future_to_q):
                res = future.result()
                for c in res:
                    if c["link"] not in seen_links:
                        seen_links.add(c["link"])
                        cards_to_fetch.append(c)

        # 2. Fetch detail pages concurrently
        jobs = []
        if cards_to_fetch:
            with ThreadPoolExecutor(max_workers=8) as executor:
                future_to_detail = {executor.submit(self._fetch_detail_page, c): c for c in cards_to_fetch}
                for future in as_completed(future_to_detail):
                    try:
                        jobs.append(future.result())
                    except Exception as err:
                        logger.debug(f"[Carga de Trabalhos Portal] Detail fetch error: {err}")

        logger.info(f"[Carga de Trabalhos Portal] Fetched {len(jobs)} jobs concurrently.")
        return jobs

class JobIngestionPipeline:
    """Aggregates all structured job portal scrapers concurrently and deduplicates jobs."""
    def __init__(self, itjobs_api_key: str = ""):
        self.session = get_session(pool_size=30)
        self.linkedin_scraper = LinkedInScraper(session=self.session)
        self.itjobs_scraper = ITJobsScraper(session=self.session)
        self.landing_scraper = LandingJobsScraper(session=self.session)
        self.remotive_scraper = RemotiveScraper(session=self.session)
        self.arbeitnow_scraper = ArbeitnowScraper(session=self.session)
        self.wwr_scraper = WeWorkRemotelyScraper(session=self.session)
        self.remoteok_scraper = RemoteOKScraper(session=self.session)
        self.carga_scraper = CargaDeTrabalhosScraper(session=self.session)
        self.itjobs_api_key = itjobs_api_key

    def run(self) -> List[Job]:
        logger.info("🚀 Starting resilient & concurrent job portal ingestion pipeline...")
        all_jobs: List[Job] = []

        scrapers = [
            ("LinkedIn", self.linkedin_scraper.fetch),
            ("ITJobs", lambda: self.itjobs_scraper.fetch(self.itjobs_api_key)),
            ("Carga de Trabalhos", self.carga_scraper.fetch),
            ("Landing.jobs", self.landing_scraper.fetch),
            ("Remotive", self.remotive_scraper.fetch),
            ("Arbeitnow", self.arbeitnow_scraper.fetch),
            ("WeWorkRemotely", self.wwr_scraper.fetch),
            ("RemoteOK", self.remoteok_scraper.fetch),
        ]

        # Execute all scrapers in parallel across worker threads
        with ThreadPoolExecutor(max_workers=len(scrapers)) as executor:
            future_to_scraper = {executor.submit(func): name for name, func in scrapers}
            for future in as_completed(future_to_scraper):
                scraper_name = future_to_scraper[future]
                try:
                    res = future.result()
                    all_jobs.extend(res)
                except Exception as e:
                    logger.error(f"[{scraper_name}] Execution error during concurrent fetch: {e}")

        # Deduplication using job_id hash
        unique_jobs: Dict[str, Job] = {}
        for j in all_jobs:
            if j.job_id not in unique_jobs:
                unique_jobs[j.job_id] = j

        final_jobs = list(unique_jobs.values())
        logger.info(f"✅ Ingestion complete. Total raw: {len(all_jobs)} | Unique portal job offers: {len(final_jobs)}")
        return final_jobs
