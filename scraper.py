import hashlib
import logging
import re
import datetime
import random
import time
import string
from dataclasses import dataclass
from typing import List, Dict, Set, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry
from bs4 import BeautifulSoup
import feedparser
from config import config

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("Scraper")

# Suppress noisy internal urllib3 retry warnings
logging.getLogger("urllib3.connectionpool").setLevel(logging.ERROR)
logging.getLogger("urllib3").setLevel(logging.ERROR)

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

def get_session(pool_size: int = 40) -> requests.Session:
    """Returns a requests.Session configured with automatic retries, exponential backoff, and HTTP connection pooling."""
    session = requests.Session()
    
    # Configure retry logic for HTTP 429 (Rate Limit) and server errors (500, 502, 503, 504)
    retries = Retry(
        total=3,
        connect=3,
        read=3,
        backoff_factor=0.8,  # Delays: 0.8s, 1.6s, 3.2s...
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
    "growth", "sales", "comercial", "branding", "copywriter", "videógrafo", "data annotator", "anotador de dados", "annotator",
    "administrativo", "administrativa", "contabilidade", "contabilista", "accounting", "accountant", "recursos humanos", "recruiter", "secretariado", "financeiro",
    "data entry", "introdução de dados", "introducao de dados", "entry assistant", "entry clerk"
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

def clean_job_description(html_or_text: str) -> str:
    """Strips HTML tags, script/style content, and collapses whitespace to reduce prompt token size."""
    if not html_or_text:
        return ""
    if "<" in html_or_text and ">" in html_or_text:
        try:
            soup = BeautifulSoup(html_or_text, "html.parser")
            for element in soup(["script", "style", "nav", "footer", "header"]):
                element.decompose()
            text = soup.get_text(separator=" ")
        except Exception:
            text = re.sub(r"<[^>]+>", " ", html_or_text)
    else:
        text = html_or_text

    # Collapse multiple whitespaces and line breaks
    text = re.sub(r"\s+", " ", text).strip()
    return text

NOISE_COMPANY_PATTERNS = [
    r"\bmodelo\s+híbrido\b.*$",
    r"\bmodelo\s+hibrido\b.*$",
    r"\bteletrabalho\b.*$",
    r"\bin\s+\d{4}\b.*$",
    r"\bin\s+lisboa\b.*$",
    r"\bin\s+lisbon\b.*$",
    r"\bin\s+porto\b.*$",
    r"\bin\s+portugal\b.*$",
    r"\blisboa\b.*$",
    r"\blisbon\b.*$",
    r"\bportugal\b.*$",
    r"\bpresencial\b.*$",
    r"\bremote\b.*$",
    r"\bremoto\b.*$",
    r"\bhybrid\b.*$",
]

def clean_company_name(company: str) -> str:
    if not company:
        return "Empresa Confidencial"
    c = company.strip()
    for pat in NOISE_COMPANY_PATTERNS:
        c = re.sub(pat, "", c, flags=re.IGNORECASE).strip()
    c = re.sub(r"[\s\-\|]+$", "", c).strip()
    return c if c else company.strip()

def normalize_title_company_for_hash(title: str, company: str) -> str:
    clean_c = clean_company_name(company)
    t_clean = re.sub(r"\b(remote|remoto|teletrabalho|híbrido|hibrido|hybrid|presencial|lisboa|lisbon|portugal)\b", "", title, flags=re.IGNORECASE)
    
    def _norm(s: str) -> str:
        return " ".join(s.lower().translate(str.maketrans('', '', string.punctuation)).split())
    
    return f"{_norm(t_clean)}_{_norm(clean_c)}"

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
    fetched_at: str = ""

    def __post_init__(self):
        self.company = clean_company_name(self.company)
        self.description = clean_job_description(self.description)

        if not self.fetched_at:
            self.fetched_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if not self.job_id:
            raw_str = normalize_title_company_for_hash(self.title, self.company)
            self.job_id = hashlib.sha256(raw_str.encode('utf-8')).hexdigest()[:16]
        
        text_content = f"{self.title} {self.description}".lower()
        if any(term in text_content for term in ["iefp", "ativar.pt", "ativar pt", "estágio profissional", "estagio profissional"]):
            self.iefp_mentioned = True
            
        # Strict Work Mode Inferencing Logic
        text_lower = f"{self.title} {self.description}".lower()
        has_hybrid = any(term in text_lower for term in ["híbrid", "hibrid", "hybrid", "modelo híbrido", "trabalho híbrido", "flexível", "dias presencial", "dias remoto"]) or ("presencial" in text_lower and ("remot" in text_lower or "teletrabalho" in text_lower))
        has_remote = any(term in text_lower for term in ["100% remoto", "100% remote", "totalmente remoto", "full remote", "teletrabalho", "remoto", "remote", "anywhere"])
        has_onsite = any(term in text_lower for term in ["presencial", "onsite", "on-site", "escritório", "no local"])

        if self.work_mode.lower() in ["unknown", "n/a", "não especificado", "", "presencial / híbrido"]:
            if has_hybrid:
                self.work_mode = "Híbrido"
            elif has_remote and not has_onsite:
                self.work_mode = "Remoto"
            elif has_onsite and not has_remote:
                self.work_mode = "Presencial"
            elif has_remote:
                self.work_mode = "Remoto"
            else:
                self.work_mode = "Presencial / Híbrido"

class LinkedInScraper:
    """Scrapes LinkedIn public search portal for Portugal AI & Data Science jobs with realistic browser headers."""
    def __init__(self, session: Optional[requests.Session] = None):
        self.session = session or get_session()

    def _fetch_query_cards(self, query: str, max_pages: int = 3) -> List[Dict]:
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
                time.sleep(random.uniform(0.8, 1.5))
                resp = self.session.get(url, headers=headers, timeout=12)

                if resp.status_code != 200:
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
        
        desc = f"{title} na empresa {company} em {location}."
        try:
            headers = get_random_headers()
            headers.update({
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate"
            })
            time.sleep(random.uniform(0.3, 0.6))
            detail_resp = self.session.get(clean_link, headers=headers, timeout=15)
            if detail_resp.status_code != 200:
                logger.warning(f"[{self.__class__.__name__}] Unexpected HTTP {detail_resp.status_code} for {detail_resp.url}")
            if detail_resp.status_code == 200:
                detail_soup = BeautifulSoup(detail_resp.text, "html.parser")
                markup = (
                    detail_soup.find("div", class_=lambda c: c and "show-more-less-html__markup" in str(c)) or
                    detail_soup.find("section", class_=lambda c: c and "description" in str(c)) or
                    detail_soup.find("div", class_=lambda c: c and "description__text" in str(c))
                )
                if markup:
                    text_content = markup.get_text(separator=" ", strip=True)
                else:
                    text_content = detail_soup.get_text(separator=" ", strip=True)
                
                if len(text_content) > 50:
                    desc = f"{title} - " + text_content
        except Exception as d_err:
            logger.debug(f"LinkedIn detail fetch failed for {clean_link}: {d_err}")

        return Job(
            title=title, company=company, location=location,
            work_mode="Presencial / Híbrido", link=clean_link, description=desc,
            source="LinkedIn", pub_date=pub_date
        )

    def fetch(self) -> List[Job]:
        queries = config.candidate.search_queries or ["Junior AI", "Junior Data Scientist", "Machine Learning Trainee", "Data Engineer Trainee", "Entry level AI", "Entry level Data"]
        all_cards: List[Dict] = []
        seen_links: Set[str] = set()
        
        for q in queries:
            res = self._fetch_query_cards(q)
            for card in res:
                if card["clean_link"] not in seen_links:
                    seen_links.add(card["clean_link"])
                    all_cards.append(card)

        jobs: List[Job] = []
        for card in all_cards:
            jobs.append(self._fetch_detail_job(card))

        logger.info(f"[LinkedIn Portal] Safely fetched {len(jobs)} fresh jobs with full detail body parsing.")
        return jobs


class ITJobsScraper:
    """Scrapes ITJobs.pt portal for Portugal IT, AI & Data Science jobs with full detail body parsing."""
    def __init__(self, session: Optional[requests.Session] = None):
        self.session = session or get_session()

    def _fetch_search_url_cards(self, url: str) -> List[Dict]:
        cards = []
        try:
            resp = self.session.get(url, headers=get_random_headers(), timeout=10)
            if resp.status_code != 200:
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
            detail_resp = self.session.get(full_link, headers=get_random_headers(), timeout=15)
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


    def fetch(self, api_key: str = "") -> List[Job]:
        jobs = []
        if api_key:
            try:
                for page in range(1, 4):
                    url = f"https://api.itjobs.pt/2/job/search.json?api_key={api_key}&limit=50&page={page}"
                    resp = self.session.get(url, headers=get_random_headers(), timeout=10)
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

class LandingJobsScraper:
    """Scrapes Landing.jobs portal via public API."""
    def __init__(self, session: Optional[requests.Session] = None):
        self.session = session or get_session()

    def fetch(self) -> List[Job]:
        jobs = []
        for page in range(1, 4):
            url = f"https://landing.jobs/api/v1/jobs?page={page}"
            try:
                h = get_random_headers()
                h["Accept"] = "application/json"
                resp = self.session.get(url, headers=h, timeout=10)
                if resp.status_code != 200:
                    logger.warning(f"[{self.__class__.__name__}] Unexpected HTTP {resp.status_code} for {resp.url}")
                    break
                if resp.status_code == 200:
                    items = resp.json()
                    if not items or not isinstance(items, list):
                        break
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
            except Exception as e:
                logger.error(f"[Landing.jobs Portal] Error at page {page}: {e}")
                break
        logger.info(f"[Landing.jobs Portal] Fetched {len(jobs)} jobs across pages 1-3.")
        return jobs

class RemotiveScraper:
    """Scrapes Remotive.com portal API for remote AI & Data Science jobs."""
    def __init__(self, session: Optional[requests.Session] = None):
        self.session = session or get_session()

    def fetch(self) -> List[Job]:
        jobs = []
        seen_links = set()
        categories = ["data", "software-dev"]
        for cat in categories:
            url = f"https://remotive.com/api/remote-jobs?category={cat}"
            try:
                h = get_random_headers()
                h["Accept"] = "application/json"
                resp = self.session.get(url, headers=h, timeout=10)
                if resp.status_code != 200:
                    logger.warning(f"[{self.__class__.__name__}] Unexpected HTTP {resp.status_code} for {resp.url}")
                if resp.status_code == 200:
                    data = resp.json()
                    for item in data.get("jobs", []):
                        title = item.get("title", "")
                        link = item.get("url", "")
                        
                        if not link or link in seen_links or not is_valid_job_offer(link, title):
                            continue
                        seen_links.add(link)

                        company = item.get("company_name", "Remotive Company")
                        location = item.get("candidate_required_location", "Worldwide Remote")
                        desc = BeautifulSoup(item.get("description", ""), "html.parser").get_text(separator=' ', strip=True)
                        pub_date = item.get("publication_date", datetime.date.today().isoformat())[:10]
                        
                        jobs.append(Job(
                            title=title, company=company, location=location,
                            work_mode="Remoto", link=link, description=desc,
                            source="Remotive", pub_date=pub_date
                        ))
            except Exception as e:
                logger.error(f"[Remotive Portal] Error for category {cat}: {e}")
        logger.info(f"[Remotive Portal] Fetched {len(jobs)} jobs across categories.")
        return jobs

class ArbeitnowScraper:
    """Scrapes Arbeitnow European job portal API."""
    def __init__(self, session: Optional[requests.Session] = None):
        self.session = session or get_session()

    def fetch(self) -> List[Job]:
        jobs = []
        for page in range(1, 4):
            url = f"https://www.arbeitnow.com/api/job-board-api?page={page}"
            try:
                h = get_random_headers()
                h["Accept"] = "application/json"
                resp = self.session.get(url, headers=h, timeout=10)
                if resp.status_code != 200:
                    logger.warning(f"[{self.__class__.__name__}] Unexpected HTTP {resp.status_code} for {resp.url}")
                    break
                if resp.status_code == 200:
                    data = resp.json()
                    items = data.get("data", [])
                    if not items:
                        break
                    for item in items:
                        title = item.get("title", "")
                        link = item.get("url", "")
                        
                        if not is_valid_job_offer(link, title):
                            continue

                        company = item.get("company_name", "Arbeitnow Company")
                        location = item.get("location", "Europe / Remote")
                        remote = item.get("remote", False)
                        work_mode = "Remoto" if remote else "Presencial / Híbrido"
                        desc = BeautifulSoup(item.get("description", ""), "html.parser").get_text(separator=' ', strip=True)
                        pub_date = datetime.date.fromtimestamp(item.get("created_at", int(datetime.datetime.now().timestamp()))).isoformat()
                        
                        jobs.append(Job(
                            title=title, company=company, location=location,
                            work_mode=work_mode, link=link, description=desc,
                            source="Arbeitnow", pub_date=pub_date
                        ))
            except Exception as e:
                logger.error(f"[Arbeitnow Portal] Error at page {page}: {e}")
                break
        logger.info(f"[Arbeitnow Portal] Fetched {len(jobs)} jobs across pages 1-3.")
        return jobs

class WeWorkRemotelyScraper:
    """Scrapes WeWorkRemotely job portal RSS feeds."""
    def __init__(self, session: Optional[requests.Session] = None):
        self.session = session or get_session()

    def fetch(self) -> List[Job]:
        jobs = []
        seen_links = set()
        rss_urls = [
            "https://weworkremotely.com/categories/remote-back-end-programming-jobs.rss",
            "https://weworkremotely.com/categories/remote-full-stack-programming-jobs.rss",
            "https://weworkremotely.com/categories/remote-devops-sysadmin-jobs.rss"
        ]
        for rss_url in rss_urls:
            try:
                feed = feedparser.parse(rss_url)
                for entry in feed.entries:
                    title = entry.get("title", "")
                    link = entry.get("link", "")
                    
                    if not link or link in seen_links or not is_valid_job_offer(link, title):
                        continue
                    seen_links.add(link)

                    desc = BeautifulSoup(entry.get("summary", ""), "html.parser").get_text(separator=' ', strip=True)
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
            except Exception as e:
                logger.error(f"[WeWorkRemotely Portal] Error for RSS {rss_url}: {e}")
        logger.info(f"[WeWorkRemotely Portal] Fetched {len(jobs)} jobs across RSS feeds.")
        return jobs

class RemoteOKScraper:
    """Scrapes RemoteOK portal API for remote data & AI roles."""
    def __init__(self, session: Optional[requests.Session] = None):
        self.session = session or get_session()

    def fetch(self) -> List[Job]:
        jobs = []
        seen_links = set()
        tags = ["data", "python", "ai", "dev"]
        for tag in tags:
            url = f"https://remoteok.com/api?tag={tag}"
            try:
                h = get_random_headers()
                h["Accept"] = "application/json"
                resp = self.session.get(url, headers=h, timeout=10)
                if resp.status_code != 200:
                    logger.warning(f"[{self.__class__.__name__}] Unexpected HTTP {resp.status_code} for {resp.url}")
                if resp.status_code == 200:
                    items = resp.json()
                    if isinstance(items, list) and len(items) > 1:
                        for item in items[1:]:
                            if isinstance(item, dict):
                                title = item.get("position", "")
                                link = item.get("url", "") or item.get("apply_url", "")
                                
                                if not link or link in seen_links or not is_valid_job_offer(link, title):
                                    continue
                                seen_links.add(link)

                                company = item.get("company", "RemoteOK Company")
                                location = item.get("location", "Worldwide Remote")
                                desc = BeautifulSoup(item.get("description", ""), "html.parser").get_text(separator=' ', strip=True)
                                pub_date = item.get("date", datetime.date.today().isoformat())[:10]
                                
                                jobs.append(Job(
                                    title=title, company=company, location=location,
                                    work_mode="Remoto", link=link, description=desc,
                                    source="RemoteOK", pub_date=pub_date
                                ))
            except Exception as e:
                logger.error(f"[RemoteOK Portal] Error for tag {tag}: {e}")
        logger.info(f"[RemoteOK Portal] Fetched {len(jobs)} jobs across tags.")
        return jobs

class CargaDeTrabalhosScraper:
    """Scrapes Carga de Trabalhos portal for Portuguese tech & AI jobs."""
    def __init__(self, session: Optional[requests.Session] = None):
        self.session = session or get_session()

    def _fetch_query_articles(self, q: str, max_pages: int = 3) -> List[Dict]:
        cards = []
        for page in range(1, max_pages + 1):
            try:
                url = f"https://cargadetrabalhos.pt/page/{page}/?s={q}" if page > 1 else f"https://cargadetrabalhos.pt/?s={q}"
                resp = self.session.get(url, headers=get_random_headers(), timeout=15)
                if resp.status_code != 200:
                    break
                soup = BeautifulSoup(resp.text, "html.parser")
                articles = soup.find_all("article")
                if not articles:
                    break
                page_added = 0
                for art in articles:
                    a_tag = art.find("a")
                    if not a_tag:
                        continue
                    link = a_tag.get("href", "").split("?")[0].rstrip("/")
                    if "/ofertas/" not in link:
                        continue
                    
                    title = a_tag.get_text(separator=' ', strip=True)
                    if not title or not is_valid_job_offer(link, title):
                        continue
                    
                    text = art.get_text(separator=" ", strip=True)
                    cards.append({"title": title, "link": link, "summary_text": text})
                    page_added += 1
                if page_added == 0:
                    break
            except Exception as e:
                logger.error(f"[Carga de Trabalhos Portal] Error querying '{q}' page {page}: {e}")
                break
        return cards

    def _fetch_detail_page(self, card_info: Dict) -> Job:
        title = card_info["title"]
        link = card_info["link"]
        text = card_info["summary_text"]

        try:
            det_resp = self.session.get(link, headers=get_random_headers(), timeout=15)
            if det_resp.status_code != 200:
                logger.warning(f"[{self.__class__.__name__}] Unexpected HTTP {det_resp.status_code} for {det_resp.url}")
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
        queries = config.candidate.search_queries or ["data", "python", "inteligencia", "machine learning", "ai"]
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

class JobicyScraper:
    """Scrapes Jobicy public API for remote tech, data & AI jobs."""
    def __init__(self, session: Optional[requests.Session] = None):
        self.session = session or get_session()

    def fetch(self) -> List[Job]:
        jobs = []
        seen_links = set()
        industries = ["data-science", "dev"]
        for ind in industries:
            for page in range(1, 4):
                url = f"https://jobicy.com/api/v2/remote-jobs?count=50&industry={ind}&page={page}"
                try:
                    resp = self.session.get(url, headers=get_random_headers(), timeout=10)
                    if resp.status_code == 200:
                        data = resp.json()
                        items = data.get("jobs", [])
                        if not items:
                            break
                        for item in items:
                            title = item.get("jobTitle", "")
                            link = item.get("url", "")
                            if not link or link in seen_links or not is_valid_job_offer(link, title):
                                continue
                            seen_links.add(link)
                            company = item.get("companyName", "Jobicy Company")
                            geo = item.get("jobGeo", "Worldwide Remote")
                            raw_desc = item.get("jobDescription", "") or item.get("jobExcerpt", "")
                            desc = BeautifulSoup(raw_desc, "html.parser").get_text(separator=" ", strip=True)
                            pub_date = item.get("pubDate", datetime.date.today().isoformat())[:10]
                            jobs.append(Job(
                                title=title, company=company, location=f"Remoto ({geo})",
                                work_mode="Remoto", link=link, description=desc,
                                source="Jobicy", pub_date=pub_date
                            ))
                except Exception as e:
                    logger.error(f"[Jobicy Portal] Error for industry {ind} page {page}: {e}")
                    break
        logger.info(f"[Jobicy Portal] Fetched {len(jobs)} jobs across pages.")
        return jobs

class HimalayasScraper:
    """Scrapes Himalayas public API for remote tech & data jobs."""
    def __init__(self, session: Optional[requests.Session] = None):
        self.session = session or get_session()

    def fetch(self) -> List[Job]:
        jobs = []
        seen_links = set()
        offsets = [0, 50, 100]
        for offset in offsets:
            url = f"https://himalayas.app/jobs/api?limit=50&offset={offset}"
            try:
                h = get_random_headers()
                h["Accept"] = "application/json"
                resp = self.session.get(url, headers=h, timeout=10)
                if resp.status_code != 200:
                    logger.warning(f"[{self.__class__.__name__}] Unexpected HTTP {resp.status_code} for {resp.url}")
                    break
                if resp.status_code == 200:
                    data = resp.json()
                    items = data.get("jobs", [])
                    if not items:
                        break
                    for item in items:
                        title = item.get("title", "")
                        link = item.get("applicationLink", "") or item.get("guid", "")
                        if not link or link in seen_links or not is_valid_job_offer(link, title):
                            continue
                        seen_links.add(link)
                        company = item.get("companyName", "Himalayas Company")
                        locs = item.get("locationRestrictions", [])
                        location_str = ", ".join(locs) if locs else "Worldwide Remote"
                        raw_desc = item.get("description", "") or item.get("excerpt", "")
                        desc = BeautifulSoup(raw_desc, "html.parser").get_text(separator=" ", strip=True)
                        pub_ts = item.get("pubDate")
                        pub_date = datetime.date.fromtimestamp(pub_ts).isoformat() if isinstance(pub_ts, (int, float)) else datetime.date.today().isoformat()
                        jobs.append(Job(
                            title=title, company=company, location=f"Remoto ({location_str})",
                            work_mode="Remoto", link=link, description=desc,
                            source="Himalayas", pub_date=pub_date
                        ))
            except Exception as e:
                logger.error(f"[Himalayas Portal] Error at offset {offset}: {e}")
                break
        logger.info(f"[Himalayas Portal] Fetched {len(jobs)} jobs across offsets.")
        return jobs

class NetEmpregosScraper:
    """Scrapes Net-Empregos portal (Portugal's largest job board) for tech, AI, Data & IEFP roles."""
    def __init__(self, session: Optional[requests.Session] = None):
        self.session = session or get_session()

    def _fetch_query_links(self, q: str, max_pages: int = 3) -> List[Dict]:
        cards = []
        for page in range(1, max_pages + 1):
            try:
                url = f"https://www.net-empregos.com/pesquisa-empregos.asp?chaves={q.replace(' ', '+')}&page={page}"
                resp = self.session.get(url, headers=get_random_headers(), timeout=10)
                if resp.status_code != 200:
                    break
                soup = BeautifulSoup(resp.text, "html.parser")
                links = soup.find_all("a", href=re.compile(r"/\d+/[^/]+/"))
                if not links:
                    break
                page_added = 0
                for a in links:
                    raw_href = a.get("href", "")
                    clean_link = f"https://www.net-empregos.com{raw_href}" if not raw_href.startswith("http") else raw_href
                    title = a.get_text(separator=' ', strip=True)
                    if title and len(title) >= 5 and is_valid_job_offer(clean_link, title):
                        cards.append({"title": title, "link": clean_link})
                        page_added += 1
                if page_added == 0:
                    break
            except Exception as e:
                logger.error(f"[Net-Empregos Portal] Error querying '{q}' page {page}: {e}")
                break
        return cards

    def _fetch_detail_page(self, card_info: Dict) -> Job:
        title = card_info["title"]
        link = card_info["link"]
        desc = title
        company = "Empresa via Net-Empregos"
        location = "Portugal"
        
        try:
            time.sleep(random.uniform(0.1, 0.3))
            det_resp = self.session.get(link, headers=get_random_headers(), timeout=15)
            if det_resp.status_code != 200:
                logger.warning(f"[{self.__class__.__name__}] Unexpected HTTP {det_resp.status_code} for {det_resp.url}")
            if det_resp.status_code == 200:
                det_soup = BeautifulSoup(det_resp.text, "html.parser")
                main_box = (
                    det_soup.find("div", class_="oferta-detalhe") or
                    det_soup.find("div", class_="content") or
                    det_soup.find("div", id="main")
                )
                if main_box:
                    desc = f"{title} - " + main_box.get_text(separator=" ", strip=True)
                else:
                    desc = f"{title} - " + det_soup.get_text(separator=" ", strip=True)
                
                # Parse company name securely from the page title
                # Format is usually: "Title - Company - Ref.ID"
                page_title = det_soup.title.text if det_soup.title else ""
                title_parts = page_title.split(" - ")
                if len(title_parts) >= 3 and not title_parts[1].strip().startswith("Ref."):
                    company = title_parts[1].strip()
                else:
                    # Fallback to the old method if title is weird
                    for a in det_soup.find_all("a", href=True):
                        if "/emprego-empresa-id/" in a["href"]:
                            txt = a.get_text(separator=' ', strip=True)
                            if len(txt) > 1:
                                company = txt
                                break

                if not company or "empresa via" in company.lower() or company.strip().lower() in ["detalhe da oferta:", "detalhe da oferta", "empresa"]:
                    company = "Empresa Confidencial"
        except Exception:
            pass

        if not company or "empresa via" in company.lower():
            company = "Empresa Confidencial"



        return Job(
            title=title, company=company, location=location,
            work_mode="Presencial / Híbrido", link=link, description=desc,
            source="Net-Empregos", pub_date=datetime.date.today().isoformat()
        )

    def fetch(self) -> List[Job]:
        queries = config.candidate.search_queries or ["python", "data", "inteligencia artificial", "machine learning", "estagio iefp"]
        cards_to_fetch = []
        seen_links = set()

        # 1. Fetch query cards concurrently
        with ThreadPoolExecutor(max_workers=min(len(queries), 5)) as executor:
            future_to_q = {executor.submit(self._fetch_query_links, q): q for q in queries}
            for future in as_completed(future_to_q):
                res = future.result()
                for c in res:
                    if c["link"] not in seen_links:
                        seen_links.add(c["link"])
                        cards_to_fetch.append(c)

        # 2. Fetch detail pages concurrently
        jobs = []
        if cards_to_fetch:
            with ThreadPoolExecutor(max_workers=10) as executor:
                future_to_detail = {executor.submit(self._fetch_detail_page, c): c for c in cards_to_fetch}
                for future in as_completed(future_to_detail):
                    try:
                        jobs.append(future.result())
                    except Exception as err:
                        logger.debug(f"[Net-Empregos Portal] Detail fetch error: {err}")

        logger.info(f"[Net-Empregos Portal] Fetched {len(jobs)} jobs with full detail body parsing concurrently.")
        return jobs

class TeamlyzerScraper:
    """Scrapes Teamlyzer jobs portal for tech & AI positions in Portugal."""
    def __init__(self, session: Optional[requests.Session] = None):
        self.session = session or get_session()

    def _fetch_detail_page(self, card_info: dict) -> Job:
        link = card_info["link"]
        title = card_info["title"]
        company = card_info["company"]
        desc = card_info["initial_desc"]

        try:
            r = self.session.get(link, headers=get_random_headers(), timeout=12, allow_redirects=True)
            if r.status_code != 200:
                logger.warning(f"[{self.__class__.__name__}] Unexpected HTTP {r.status_code} for {r.url}")
            if r.status_code == 200:
                soup = BeautifulSoup(r.text, "html.parser")
                h1_tag = soup.find("h1")
                if h1_tag:
                    full_h1 = h1_tag.get_text(separator=' ', strip=True)
                    if len(full_h1) > len(title):
                        title = full_h1

                fetched_text = clean_job_description(r.text)
                if len(fetched_text) >= 100:
                    desc = f"{title} - " + fetched_text
        except Exception as e:
            logger.debug(f"[Teamlyzer Portal] Error fetching detail page for {link}: {e}")

        work_mode = "Remoto" if "remote" in desc.lower() else "Presencial / Híbrido"
        return Job(
            title=title, company=company, location="Portugal",
            work_mode=work_mode, link=link, description=desc,
            source="Teamlyzer", pub_date=datetime.date.today().isoformat()
        )

    def fetch(self) -> List[Job]:
        cards_to_fetch = []
        seen_links = set()
        for page in range(1, 4):
            url = f"https://pt.teamlyzer.com/companies/jobs?page={page}"
            try:
                resp = self.session.get(url, headers=get_random_headers(), timeout=10)
                if resp.status_code != 200:
                    logger.warning(f"[{self.__class__.__name__}] Unexpected HTTP {resp.status_code} for {resp.url}")
                    break
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, "html.parser")
                    cards = soup.find_all("div", class_=lambda c: c and "jobcard" in str(c).lower())
                    if not cards:
                        break
                    for card in cards:
                        a_title = card.find("h4", class_="jobcard__title")
                        a_tag = a_title.find("a") if a_title else card.find("a", href=lambda h: h and "/get-job/" in h)
                        if not a_tag:
                            continue
                        
                        href = a_tag.get("href", "")
                        clean_href = href.split("?")[0]
                        if clean_href in seen_links:
                            continue
                        
                        link = f"https://pt.teamlyzer.com{href}" if href.startswith("/") else href
                        seen_links.add(clean_href)
                        
                        title = a_tag.get_text(separator=' ', strip=True)
                        if not title or not is_valid_job_offer(link, title):
                            continue
                        
                        logo_img = card.find("img", alt=True)
                        company = logo_img["alt"].strip() if logo_img and logo_img.get("alt") else ""
                        if not company:
                            comp_a = card.find("a", href=lambda h: h and "/companies/" in h and "/get-job/" not in h)
                            if comp_a:
                                company = comp_a.get_text(separator=' ', strip=True) or comp_a.get("href", "").split("/")[-1]
                        if not company:
                            company = "Empresa no Teamlyzer"
                            
                        initial_desc = card.get_text(separator=" ", strip=True)
                        cards_to_fetch.append({
                            "link": link,
                            "title": title,
                            "company": company,
                            "initial_desc": initial_desc
                        })

            except Exception as e:
                logger.error(f"[Teamlyzer Portal] Error at page {page}: {e}")
                break

        jobs = []
        if cards_to_fetch:
            with ThreadPoolExecutor(max_workers=8) as executor:
                future_to_detail = {executor.submit(self._fetch_detail_page, c): c for c in cards_to_fetch}
                for future in as_completed(future_to_detail):
                    try:
                        jobs.append(future.result())
                    except Exception as err:
                        logger.debug(f"[Teamlyzer Portal] Detail fetch error: {err}")

        logger.info(f"[Teamlyzer Portal] Fetched {len(jobs)} jobs across pages 1-3 concurrently.")
        return jobs

class JobspressoScraper:
    """Scrapes Jobspresso HTML job listings for remote tech & data jobs."""
    def __init__(self, session: Optional[requests.Session] = None):
        self.session = session or get_session()

    def fetch(self) -> List[Job]:
        jobs = []
        seen_links = set()
        pages = ["https://jobspresso.co/", "https://jobspresso.co/page/2/", "https://jobspresso.co/page/3/"]
        
        for url in pages:
            try:
                resp = self.session.get(url, headers=get_random_headers(), timeout=10)
                if resp.status_code != 200:
                    logger.warning(f"[{self.__class__.__name__}] Unexpected HTTP {resp.status_code} for {resp.url}")
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
                        
                        desc = parent.get_text(separator=" ", strip=True)
                        
                        jobs.append(Job(
                            title=title, company=company, location=location,
                            work_mode="Remoto", link=href, description=desc,
                            source="Jobspresso", pub_date=datetime.date.today().isoformat()
                        ))
            except Exception as e:
                logger.error(f"[Jobspresso Portal] Error at {url}: {e}")
        logger.info(f"[Jobspresso Portal] Fetched {len(jobs)} jobs across pages 1-3.")
        return jobs

class EuraxessScraper:
    """Scrapes Euraxess Portugal portal for AI, ML & Data Science research fellowships & R&D grants."""
    def __init__(self, session: Optional[requests.Session] = None):
        self.session = session or get_session()

    def fetch(self) -> List[Job]:
        jobs = []
        queries = config.candidate.search_queries or ["Portugal", "AI", "Data"]
        seen_links = set()
        
        for q in queries:
            for page in range(0, 3):
                url = f"https://euraxess.ec.europa.eu/jobs/search?keywords={q}&page={page}"
                try:
                    resp = self.session.get(url, headers=get_random_headers(), timeout=10)
                    if resp.status_code != 200:
                        logger.warning(f"[{self.__class__.__name__}] Unexpected HTTP {resp.status_code} for {resp.url}")
                        break
                    if resp.status_code == 200:
                        soup = BeautifulSoup(resp.text, "html.parser")
                        job_links = soup.find_all("a", href=lambda h: h and re.search(r"/jobs/\d+", h))
                        if not job_links:
                            break
                        page_added = 0
                        for a in job_links:
                            href = a.get("href", "")
                            link = f"https://euraxess.ec.europa.eu{href}" if href.startswith("/") else href
                            if link in seen_links:
                                continue
                            seen_links.add(link)
                            
                            title = a.get_text(separator=' ', strip=True)
                            if not title or not is_valid_job_offer(link, title):
                                continue
                            
                            parent = a.find_parent("div", class_=lambda c: c and any(k in str(c).lower() for k in ["teaser", "card", "view", "item", "row", "result"]))
                            if not parent:
                                parent = a.parent.parent if a.parent else None
                                
                            desc = parent.get_text(separator=" ", strip=True) if parent else title
                            
                            company = "Universidade / Centro de I&D em Portugal"
                            if parent:
                                txt = parent.get_text(separator=" | ", strip=True)
                                parts = txt.split(" | ")
                                if parts:
                                    company = parts[0].strip()
                            
                            jobs.append(Job(
                                title=title, company=company, location="Portugal",
                                work_mode="Presencial / Híbrido", link=link, description=desc,
                                source="Euraxess / Ergas (Bolsas ID)", pub_date=datetime.date.today().isoformat()
                            ))
                            page_added += 1
                        if page_added == 0:
                            break
                except Exception as e:
                    logger.error(f"[Euraxess Portal] Error at {url}: {e}")
                    break
        logger.info(f"[Euraxess Portal] Fetched {len(jobs)} research fellowships across pages 1-3.")
        return jobs


class IndeedScraper:
    """Scrapes Indeed Portugal (pt.indeed.com) for tech, AI & Data Science jobs."""
    def __init__(self, session: Optional[requests.Session] = None):
        self.session = session or get_session()

    def fetch(self) -> List[Job]:
        jobs = []
        queries = config.candidate.search_queries or ["Junior AI", "Data Scientist", "Python", "Estagio Data"]
        seen_links = set()
        
        for q in queries:
            for page in range(0, 3):
                start = page * 10
                url = f"https://pt.indeed.com/jobs?q={q.replace(' ', '+')}&l=Portugal&start={start}"
                try:
                    headers = get_random_headers()
                    headers.update({
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                        "Accept-Language": "pt-PT,pt;q=0.9,en-US;q=0.8,en;q=0.7",
                    })
                    time.sleep(random.uniform(0.6, 1.5))
                    resp = self.session.get(url, headers=headers, timeout=12)
                    if resp.status_code != 200:
                        break
                    soup = BeautifulSoup(resp.text, "html.parser")
                    cards = soup.find_all("div", class_=lambda c: c and ("job_seen_beacon" in str(c) or "result" in str(c)))
                    if not cards:
                        cards = soup.find_all("td", class_="resultContent")
                    if not cards:
                        break
                    
                    page_added = 0
                    card_infos = []
                    for card in cards:
                        a_tag = card.find("a", href=True)
                        if not a_tag:
                            continue
                        href = a_tag["href"]
                        clean_link = f"https://pt.indeed.com{href}" if href.startswith("/") else href
                        clean_link = clean_link.split("&")[0]
                        if clean_link in seen_links:
                            continue
                        
                        title_elem = card.find("h2") or card.find("span", id=re.compile(r"^jobTitle")) or a_tag
                        title = title_elem.get_text(separator=" ", strip=True) if title_elem else ""
                        if not title or not is_valid_job_offer(clean_link, title):
                            continue
                        
                        seen_links.add(clean_link)
                        company_elem = card.find(class_=lambda c: c and "company" in str(c).lower())
                        company = company_elem.get_text(separator=" ", strip=True) if company_elem else "Empresa no Indeed"
                        
                        loc_elem = card.find(class_=lambda c: c and "location" in str(c).lower())
                        location = loc_elem.get_text(separator=" ", strip=True) if loc_elem else "Portugal"
                        
                        initial_desc = card.get_text(separator=" ", strip=True)
                        card_infos.append({
                            "title": title, "company": company, "location": location,
                            "link": clean_link, "initial_desc": initial_desc
                        })
                        page_added += 1

                    for c_info in card_infos:
                        desc = c_info["initial_desc"]
                        try:
                            time.sleep(random.uniform(0.3, 0.6))
                            det_resp = self.session.get(c_info["link"], headers=headers, timeout=10)
                            if det_resp.status_code == 200:
                                det_soup = BeautifulSoup(det_resp.text, "html.parser")
                                job_body = det_soup.find("div", id="jobDescriptionText") or det_soup.find("div", class_=lambda c: c and "jobsearch-jobdescriptiontext" in str(c).lower())
                                if job_body:
                                    desc = f"{c_info['title']} - " + job_body.get_text(separator=" ", strip=True)
                        except Exception:
                            pass

                        jobs.append(Job(
                            title=c_info["title"], company=c_info["company"], location=c_info["location"],
                            work_mode="Presencial / Híbrido", link=c_info["link"], description=desc,
                            source="Indeed Portugal", pub_date=datetime.date.today().isoformat()
                        ))
                    if page_added == 0:
                        break
                except Exception as e:
                    logger.debug(f"[Indeed Portugal] Error fetching '{q}' page {page+1}: {e}")
                    break
        logger.info(f"[Indeed Portugal] Fetched {len(jobs)} jobs.")
        return jobs


class GlassdoorScraper:
    """Scrapes Glassdoor Portugal portal for AI, ML & Data Science jobs."""
    def __init__(self, session: Optional[requests.Session] = None):
        self.session = session or get_session()

    def fetch(self) -> List[Job]:
        jobs = []
        queries = config.candidate.search_queries or ["data science", "junior ai", "python", "machine learning"]
        seen_links = set()

        for q in queries:
            for page in range(1, 3):
                url = f"https://www.glassdoor.com/Job/jobs.htm?sc.keyword={q.replace(' ', '%20')}&locT=C&locId=195&p={page}"
                try:
                    headers = get_random_headers()
                    headers.update({
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                        "Accept-Language": "en-US,en;q=0.9,pt-PT;q=0.8",
                    })
                    time.sleep(random.uniform(0.7, 1.5))
                    resp = self.session.get(url, headers=headers, timeout=12)
                    if resp.status_code != 200:
                        break
                    soup = BeautifulSoup(resp.text, "html.parser")
                    items = soup.find_all("li", class_=lambda c: c and "job" in str(c).lower())
                    if not items:
                        items = soup.find_all("div", class_=lambda c: c and "jobListing" in str(c))
                    if not items:
                        break

                    page_added = 0
                    for item in items:
                        a_tag = item.find("a", href=True)
                        if not a_tag:
                            continue
                        href = a_tag["href"]
                        clean_link = f"https://www.glassdoor.com{href}" if href.startswith("/") else href
                        clean_link = clean_link.split("?")[0]
                        if clean_link in seen_links:
                            continue
                        
                        title = a_tag.get_text(separator=" ", strip=True)
                        if not title or not is_valid_job_offer(clean_link, title):
                            continue
                        
                        seen_links.add(clean_link)
                        comp_elem = item.find(class_=lambda c: c and "employer" in str(c).lower())
                        company = comp_elem.get_text(separator=" ", strip=True) if comp_elem else "Empresa no Glassdoor"
                        
                        desc = item.get_text(separator=" ", strip=True)
                        
                        jobs.append(Job(
                            title=title, company=company, location="Portugal",
                            work_mode="Presencial / Híbrido", link=clean_link, description=desc,
                            source="Glassdoor Portugal", pub_date=datetime.date.today().isoformat()
                        ))
                        page_added += 1
                    if page_added == 0:
                        break
                except Exception as e:
                    logger.debug(f"[Glassdoor Portugal] Error fetching '{q}' page {page}: {e}")
                    break
        logger.info(f"[Glassdoor Portugal] Fetched {len(jobs)} jobs.")
        return jobs


class SapoEmpregosScraper:
    """Scrapes SAPO Emprego portal (emprego.sapo.pt) for Portuguese tech, AI & Data Science jobs."""
    def __init__(self, session: Optional[requests.Session] = None):
        self.session = session or get_session()

    def fetch(self) -> List[Job]:
        jobs = []
        queries = config.candidate.search_queries or ["python", "data", "inteligencia artificial", "estagio"]
        seen_links = set()

        for q in queries:
            for page in range(1, 4):
                url = f"https://emprego.sapo.pt/pesquisa/ofertas?q={q.replace(' ', '+')}&pagina={page}"
                try:
                    resp = self.session.get(url, headers=get_random_headers(), timeout=10)
                    if resp.status_code != 200:
                        break
                    soup = BeautifulSoup(resp.text, "html.parser")
                    cards = soup.find_all("article") or soup.find_all("div", class_=lambda c: c and "oferta" in str(c).lower())
                    if not cards:
                        break
                    page_added = 0
                    for card in cards:
                        a_tag = card.find("a", href=True)
                        if not a_tag:
                            continue
                        href = a_tag["href"]
                        link = f"https://emprego.sapo.pt{href}" if href.startswith("/") else href
                        if link in seen_links:
                            continue
                        
                        title = a_tag.get_text(separator=" ", strip=True)
                        if not title or not is_valid_job_offer(link, title):
                            continue
                        
                        seen_links.add(link)
                        comp_elem = card.find(class_=lambda c: c and "empresa" in str(c).lower())
                        company = comp_elem.get_text(separator=" ", strip=True) if comp_elem else "Empresa no SAPO Emprego"
                        
                        loc_elem = card.find(class_=lambda c: c and "local" in str(c).lower())
                        location = loc_elem.get_text(separator=" ", strip=True) if loc_elem else "Portugal"
                        
                        desc = card.get_text(separator=" ", strip=True)
                        
                        jobs.append(Job(
                            title=title, company=company, location=location,
                            work_mode="Presencial / Híbrido", link=link, description=desc,
                            source="SAPO Emprego", pub_date=datetime.date.today().isoformat()
                        ))
                        page_added += 1
                    if page_added == 0:
                        break
                except Exception as e:
                    logger.debug(f"[SAPO Emprego] Error fetching '{q}' page {page}: {e}")
                    break
        logger.info(f"[SAPO Emprego] Fetched {len(jobs)} jobs.")
        return jobs


class TuringScraper:
    """Scrapes Turing.com jobs portal for remote engineering, AI & Data Science positions."""
    def __init__(self, session: Optional[requests.Session] = None):
        self.session = session or get_session()

    def fetch(self) -> List[Job]:
        jobs = []
        url = "https://www.turing.com/api/v1/jobs"
        try:
            h = get_random_headers()
            h["Accept"] = "application/json"
            resp = self.session.get(url, headers=h, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                items = data.get("jobs", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
                for item in items:
                    title = item.get("title", "") or item.get("role", "")
                    link = item.get("url", "") or "https://www.turing.com/jobs"
                    if not title or not is_valid_job_offer(link, title):
                        continue
                    company = "Turing Client Company"
                    desc = item.get("description", "") or f"Remote {title} position via Turing"
                    jobs.append(Job(
                        title=title, company=company, location="Remote International",
                        work_mode="Remoto", link=link, description=desc,
                        source="Turing", pub_date=datetime.date.today().isoformat()
                    ))
            logger.info(f"[Turing Portal] Fetched {len(jobs)} jobs.")
        except Exception as e:
            logger.error(f"[Turing Portal] Error: {e}")
        return jobs


class WellfoundScraper:
    """Scrapes Wellfound (formerly AngelList) for startup AI & Data Science jobs in Portugal / Remote."""
    def __init__(self, session: Optional[requests.Session] = None):
        self.session = session or get_session()

    def fetch(self) -> List[Job]:
        jobs = []
        url = "https://wellfound.com/location/portugal"
        try:
            h = get_random_headers()
            resp = self.session.get(url, headers=h, timeout=10)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                job_cards = soup.find_all("div", class_=lambda c: c and any(k in str(c).lower() for k in ["job", "startup", "card", "component"]))
                seen_links = set()
                for card in job_cards:
                    a_tag = card.find("a", href=lambda h: h and ("/jobs/" in h or "/company/" in h))
                    if not a_tag:
                        continue
                    href = a_tag["href"]
                    link = f"https://wellfound.com{href}" if href.startswith("/") else href
                    if link in seen_links:
                        continue
                    
                    title = a_tag.get_text(separator=" ", strip=True)
                    if not title or not is_valid_job_offer(link, title):
                        continue
                    
                    seen_links.add(link)
                    comp_elem = card.find(class_=lambda c: c and "name" in str(c).lower())
                    company = comp_elem.get_text(separator=" ", strip=True) if comp_elem else "Startup via Wellfound"
                    desc = card.get_text(separator=" ", strip=True)
                    
                    jobs.append(Job(
                        title=title, company=company, location="Portugal / Remoto",
                        work_mode="Remoto", link=link, description=desc,
                        source="Wellfound (AngelList)", pub_date=datetime.date.today().isoformat()
                    ))
            logger.info(f"[Wellfound Portal] Fetched {len(jobs)} startup jobs.")
        except Exception as e:
            logger.error(f"[Wellfound Portal] Error: {e}")
        return jobs


class HackerNewsScraper:
    """Scrapes Hacker News monthly 'Who is Hiring?' threads via Algolia REST API for high-quality remote/AI roles."""
    def __init__(self, session: Optional[requests.Session] = None):
        self.session = session or get_session()

    def fetch(self) -> List[Job]:
        jobs = []
        try:
            search_url = "https://hn.algolia.com/api/v1/search?tags=story,author_whoishiring&query=Who%20is%20hiring"
            resp = self.session.get(search_url, headers=get_random_headers(), timeout=10)
            if resp.status_code == 200:
                hits = resp.json().get("hits", [])
                if hits:
                    latest_story_id = hits[0].get("objectID")
                    comments_url = f"https://hn.algolia.com/api/v1/search?tags=comment,story_{latest_story_id}&hitsPerPage=50"
                    c_resp = self.session.get(comments_url, headers=get_random_headers(), timeout=10)
                    if c_resp.status_code == 200:
                        comments = c_resp.json().get("hits", [])
                        keywords = ["ai", "data", "python", "machine learning", "remote", "portugal", "europe"]
                        for c in comments:
                            text = c.get("comment_text", "")
                            if not text:
                                continue
                            soup = BeautifulSoup(text, "html.parser")
                            clean_text = soup.get_text(separator=" ", strip=True)
                            text_lower = clean_text.lower()
                            
                            if any(kw in text_lower for kw in keywords) and ("hiring" in text_lower or "|" in clean_text[:80]):
                                first_line = clean_text.split("\n")[0][:100]
                                parts = first_line.split("|")
                                company = parts[0].strip() if len(parts) > 1 else "Hacker News Startup"
                                title = parts[1].strip() if len(parts) > 1 else first_line
                                link = f"https://news.ycombinator.com/item?id={c.get('objectID')}"
                                
                                if is_valid_job_offer(link, title):
                                    jobs.append(Job(
                                        title=title[:80], company=company[:60], location="Remote / Europe",
                                        work_mode="Remoto", link=link, description=clean_text,
                                        source="Hacker News (Who is Hiring?)", pub_date=datetime.date.today().isoformat()
                                    ))
            logger.info(f"[Hacker News] Fetched {len(jobs)} high-quality Tech/AI jobs.")
        except Exception as e:
            logger.error(f"[Hacker News] Error: {e}")
        return jobs


class IEFPScraper:
    """Scrapes official IEFP Portugal portal (iefponline.iefp.pt) for ATIVAR.PT professional internships."""
    def __init__(self, session: Optional[requests.Session] = None):
        self.session = session or get_session()

    def fetch(self) -> List[Job]:
        jobs = []
        queries = ["estagio", "data", "informatica", "inteligencia artificial", "python"]
        seen_links = set()

        for q in queries:
            url = f"https://iefponline.iefp.pt/IEFP/pesquisaofertas/pesquisarOfertasPortal.do?tipoOferta=ESTAGIO&query={q}"
            try:
                resp = self.session.get(url, headers=get_random_headers(), timeout=12)
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, "html.parser")
                    offers = soup.find_all("tr", class_=lambda c: c and "linha" in str(c).lower()) or soup.find_all("div", class_=lambda c: c and "oferta" in str(c).lower())
                    for off in offers:
                        a_tag = off.find("a", href=True)
                        if not a_tag:
                            continue
                        href = a_tag["href"]
                        link = f"https://iefponline.iefp.pt{href}" if href.startswith("/") else href
                        if link in seen_links:
                            continue
                        
                        title = a_tag.get_text(separator=" ", strip=True)
                        if not title or len(title) < 4:
                            continue
                        
                        seen_links.add(link)
                        desc = f"{title} - Estágio Profissional IEFP ATIVAR.PT. " + off.get_text(separator=" ", strip=True)
                        
                        jobs.append(Job(
                            title=title, company="Empresa via IEFP Portal", location="Portugal",
                            work_mode="Presencial / Híbrido", link=link, description=desc,
                            source="IEFP Portal (ATIVAR.pt)", pub_date=datetime.date.today().isoformat()
                        ))
            except Exception as e:
                logger.debug(f"[IEFP Portal] Error querying '{q}': {e}")
        logger.info(f"[IEFP Portal] Fetched {len(jobs)} ATIVAR.PT internship offers.")
        return jobs


class JobIngestionPipeline:
    """Aggregates all structured job portal scrapers concurrently and deduplicates jobs."""
    def __init__(self, itjobs_api_key: str = ""):
        self.session = get_session(pool_size=45)
        self.linkedin_scraper = LinkedInScraper(session=self.session)
        self.itjobs_scraper = ITJobsScraper(session=self.session)
        self.landing_scraper = LandingJobsScraper(session=self.session)
        self.remotive_scraper = RemotiveScraper(session=self.session)
        self.arbeitnow_scraper = ArbeitnowScraper(session=self.session)
        self.wwr_scraper = WeWorkRemotelyScraper(session=self.session)
        self.remoteok_scraper = RemoteOKScraper(session=self.session)
        self.carga_scraper = CargaDeTrabalhosScraper(session=self.session)
        self.jobicy_scraper = JobicyScraper(session=self.session)
        self.himalayas_scraper = HimalayasScraper(session=self.session)
        self.netempregos_scraper = NetEmpregosScraper(session=self.session)
        self.teamlyzer_scraper = TeamlyzerScraper(session=self.session)
        self.jobspresso_scraper = JobspressoScraper(session=self.session)
        self.euraxess_scraper = EuraxessScraper(session=self.session)
        self.indeed_scraper = IndeedScraper(session=self.session)
        self.glassdoor_scraper = GlassdoorScraper(session=self.session)
        self.sapo_scraper = SapoEmpregosScraper(session=self.session)
        self.turing_scraper = TuringScraper(session=self.session)
        self.wellfound_scraper = WellfoundScraper(session=self.session)
        self.hn_scraper = HackerNewsScraper(session=self.session)
        self.iefp_scraper = IEFPScraper(session=self.session)
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
            ("Jobicy", self.jobicy_scraper.fetch),
            ("Himalayas", self.himalayas_scraper.fetch),
            ("Net-Empregos", self.netempregos_scraper.fetch),
            ("Teamlyzer", self.teamlyzer_scraper.fetch),
            ("Jobspresso", self.jobspresso_scraper.fetch),
            ("Euraxess / Ergas", self.euraxess_scraper.fetch),
            ("Indeed Portugal", self.indeed_scraper.fetch),
            ("Glassdoor Portugal", self.glassdoor_scraper.fetch),
            ("SAPO Emprego", self.sapo_scraper.fetch),
            ("Turing", self.turing_scraper.fetch),
            ("Wellfound", self.wellfound_scraper.fetch),
            ("Hacker News", self.hn_scraper.fetch),
            ("IEFP Portal", self.iefp_scraper.fetch),
        ]

        # Execute all scrapers in parallel across worker threads
        scraper_results: Dict[str, int] = {}
        failed_scrapers: List[str] = []

        with ThreadPoolExecutor(max_workers=len(scrapers)) as executor:
            future_to_scraper = {executor.submit(func): name for name, func in scrapers}
            for future in as_completed(future_to_scraper):
                scraper_name = future_to_scraper[future]
                try:
                    res = future.result()
                    all_jobs.extend(res)
                    scraper_results[scraper_name] = len(res)
                except Exception as e:
                    logger.error(f"[{scraper_name}] Execution error during concurrent fetch: {e}")
                    scraper_results[scraper_name] = -1
                    failed_scrapers.append(scraper_name)

        # Report per-scraper health
        for name, count in scraper_results.items():
            if count == -1:
                logger.warning(f"⚠️ [{name}] FAILED — threw an exception during fetch.")
            elif count == 0:
                logger.warning(f"⚠️ [{name}] returned 0 jobs — source may be broken or blocking requests.")

        if failed_scrapers:
            logger.warning(f"🔴 {len(failed_scrapers)}/{len(scrapers)} scrapers failed: {', '.join(failed_scrapers)}")

        # Deduplication using job_id hash
        unique_jobs: Dict[str, Job] = {}
        for j in all_jobs:
            if j.job_id not in unique_jobs:
                unique_jobs[j.job_id] = j

        final_jobs = list(unique_jobs.values())
        logger.info(f"✅ Ingestion complete. Total raw: {len(all_jobs)} | Unique portal job offers: {len(final_jobs)}")
        return final_jobs

