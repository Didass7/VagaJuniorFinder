from __future__ import annotations
import hashlib
import logging
import re
import datetime
import random
import time
import string
from dataclasses import dataclass
from typing import List, Dict, Set, Optional, Any, Callable, Tuple
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
    "salesforce", "sap ",
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
    def __init__(self, session: Optional[requests.Session] = None, is_seen_func: Optional[Any] = None, queries: Optional[List[str]] = None):
        self.session = session or get_session()
        self.is_seen_func = is_seen_func
        self.queries = queries

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
                job_posting_id = id_match.group(1)
                guest_api_url = f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_posting_id}"
                headers = get_random_headers()
                headers.update({
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                    "Accept-Language": "pt-PT,pt;q=0.9,en-US;q=0.8,en;q=0.7",
                })
                time.sleep(random.uniform(0.3, 0.7))
                resp = self.session.get(guest_api_url, headers=headers, timeout=10)
                if resp.status_code == 200:
                    detail_soup = BeautifulSoup(resp.text, "html.parser")
                    markup = (
                        detail_soup.find("div", class_=lambda c: c and "show-more-less-html__markup" in str(c)) or
                        detail_soup.find("section", class_=lambda c: c and "description" in str(c)) or
                        detail_soup.find("div", class_=lambda c: c and "description__text" in str(c))
                    )
                    if markup:
                        text_content = markup.get_text(separator=" ", strip=True)
                    else:
                        text_content = detail_soup.get_text(separator=" ", strip=True)
                    
                    if len(text_content) > 100:
                        desc = f"{title} - " + clean_job_description(text_content)
        except Exception as d_err:
            logger.debug(f"LinkedIn detail fetch failed for {clean_link}: {d_err}")

        return Job(
            title=title, company=company, location=location,
            work_mode="Presencial / Híbrido", link=clean_link, description=desc,
            source="LinkedIn", pub_date=pub_date
        )

    def fetch(self) -> List[Job]:
        queries = self.queries or config.candidate.search_queries or ["Junior AI", "Junior Data Scientist", "Machine Learning Trainee", "Data Engineer Trainee", "Entry level AI", "Entry level Data"]
        all_cards: List[Dict] = []
        seen_links: Set[str] = set()
        
        # 1. Fetch query cards with polite sequential spacing
        for q in queries:
            res = self._fetch_query_cards(q)
            for card in res:
                if card["clean_link"] not in seen_links:
                    seen_links.add(card["clean_link"])
                    all_cards.append(card)
            time.sleep(random.uniform(0.4, 0.8))

        # 2. Fetch full detail bodies concurrently
        jobs: List[Job] = []
        if all_cards:
            with ThreadPoolExecutor(max_workers=6) as executor:
                future_to_detail = {executor.submit(self._fetch_detail_job, card): card for card in all_cards}
                for future in as_completed(future_to_detail):
                    try:
                        job = future.result()
                        if job.description and len(job.description) >= 100:
                            jobs.append(job)
                    except Exception as e:
                        logger.debug(f"[LinkedIn Portal] Error fetching job detail: {e}")

        logger.info(f"[LinkedIn Portal] Safely fetched {len(jobs)} fresh jobs with full detail body parsing.")
        return jobs


class ITJobsScraper:
    """Scrapes ITJobs.pt portal for Portugal IT, AI & Data Science jobs with full detail body parsing."""
    def __init__(self, session: Optional[requests.Session] = None, is_seen_func: Optional[Any] = None):
        self.session = session or get_session()
        self.is_seen_func = is_seen_func

    def _fetch_search_url_cards(self, url: str) -> List[Dict]:
        cards = []
        try:
            resp = self.session.get(url, headers=get_random_headers(), timeout=10)
            if resp.status_code != 200 and resp.status_code != 404:
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
                            if self.is_seen_func and self.is_seen_func(title, company):
                                continue
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
    """Scrapes Landing.jobs portal via official Atom feed (bypasses Cloudflare 403 on cloud runners) with API fallback."""
    def __init__(self, session: Optional[requests.Session] = None):
        self.session = session or get_session()

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
                resp = self.session.get(atom_url, headers=headers, timeout=15)
                if resp.status_code == 200 and resp.content:
                    feed = feedparser.parse(resp.content)
                    if feed.entries:
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
                    resp = self.session.get(url, headers=headers, timeout=12)
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
    def __init__(self, session: Optional[requests.Session] = None, is_seen_func: Optional[Any] = None, queries: Optional[List[str]] = None):
        self.session = session or get_session()
        self.is_seen_func = is_seen_func
        self.queries = queries

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
                    
                    if self.is_seen_func and self.is_seen_func(title, "Empresa via Carga de Trabalhos"):
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
        queries = self.queries or config.candidate.search_queries or ["data", "python", "inteligencia", "machine learning", "ai"]
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
            url = f"https://jobicy.com/api/v2/remote-jobs?count=50&industry={ind}"
            try:
                resp = self.session.get(url, headers=get_random_headers(), timeout=15)
                if resp.status_code == 200:
                    data = resp.json()
                    items = data.get("jobs", [])
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
                logger.error(f"[Jobicy Portal] Error for industry {ind}: {e}")
        logger.info(f"[Jobicy Portal] Fetched {len(jobs)} jobs.")
        return jobs

class NetEmpregosScraper:
    """Scrapes Net-Empregos portal (Portugal's largest job board) for tech, AI, Data & IEFP roles."""
    def __init__(self, session: Optional[requests.Session] = None, is_seen_func: Optional[Any] = None, queries: Optional[List[str]] = None):
        self.session = session or get_session()
        self.is_seen_func = is_seen_func
        self.queries = queries

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
                        if self.is_seen_func and self.is_seen_func(title, "Empresa via Net-Empregos"):
                            continue
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
        queries = self.queries or config.candidate.search_queries or ["python", "data", "inteligencia artificial", "machine learning", "estagio iefp"]
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
    def __init__(self, session: Optional[requests.Session] = None, queries: Optional[List[str]] = None):
        self.session = session or get_session()
        self.queries = queries

    def fetch(self) -> List[Job]:
        jobs = []
        queries = self.queries or config.candidate.search_queries or ["Portugal", "AI", "Data"]
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


        logger.info(f"[Euraxess Portal] Fetched {len(jobs)} research fellowships across pages 1-3.")
        return jobs


class IEFPScraper:
    """Scrapes official IEFP Portugal portal (iefponline.iefp.pt) for job offers and internships via POST-based search."""
    BASE_URL = "https://iefponline.iefp.pt"
    SEARCH_URL = f"{BASE_URL}/IEFP/pesquisas/search.do"

    def __init__(self, session: Optional[requests.Session] = None, is_seen_func: Optional[Any] = None):
        self.session = session or get_session()
        self.is_seen_func = is_seen_func

    def _search_offers(self, query: str, tipo: str, seen_links: set) -> List[Job]:
        """Performs a POST search on the IEFP portal and parses the results."""
        jobs = []
        try:
            # Step 1: GET to establish session cookies (JSESSIONID required)
            self.session.get(f"{self.SEARCH_URL}?cat=ofertaEmprego", headers=get_random_headers(), timeout=20)
            time.sleep(random.uniform(0.5, 1.5))

            # Step 2: POST search form
            data = {
                "text": query,
                "tipo": tipo,
                "origem": "Portugal",
                "origem_option": "Portugal",
                "currentPage": "1",
                "resultsPerPage": "25",
                "pos": "0",
                "len": "3",
            }
            resp = self.session.post(self.SEARCH_URL, headers=get_random_headers(), data=data, timeout=20)
            if resp.status_code != 200:
                return jobs

            soup = BeautifulSoup(resp.text, "html.parser")
            result_div = soup.find("div", class_="results-table")
            if not result_div:
                return jobs

            # Parse offer blocks by finding detail links
            detail_links = result_div.find_all("a", href=lambda h: h and "detalheOfertas" in h)
            for a_tag in detail_links:
                href = a_tag.get("href", "")
                link = f"{self.BASE_URL}/{href}" if not href.startswith("http") else href
                if link in seen_links:
                    continue

                # Walk up to find the parent card and extract title
                parent = a_tag.find_parent("div", class_=lambda c: c and "row" in str(c))
                if not parent:
                    parent = a_tag.parent
                
                # Title is in the first <h5> or <strong> before the detail link
                title_elem = parent.find("h5") if parent else None
                title = title_elem.get_text(strip=True) if title_elem else ""
                if not title:
                    # Fallback: extract from card text (pattern: "ID: XXXXX\nTITLE\n")
                    card_text = parent.get_text(separator="\n", strip=True) if parent else ""
                    lines = [l.strip() for l in card_text.split("\n") if l.strip() and not l.strip().startswith("ID:") and "Oferta" not in l]
                    title = lines[0] if lines else ""

                if not title or len(title) < 4:
                    continue

                if self.is_seen_func and self.is_seen_func(title, "Empresa via IEFP"):
                    continue

                seen_links.add(link)

                # Extract location from card
                location = "Portugal"
                loc_elem = parent.find("strong") if parent else None
                if loc_elem:
                    loc_candidates = parent.find_all("strong")
                    for lc in loc_candidates:
                        lc_text = lc.get_text(strip=True)
                        if lc_text != title and len(lc_text) > 2:
                            location = lc_text.split("|")[0].strip()
                            break

                card_text = parent.get_text(separator=" ", strip=True) if parent else title
                is_estagio = tipo == "OFERTA_ESTAGIO" or "estágio" in card_text.lower() or "estagio" in card_text.lower()
                source_label = "IEFP Portal (Estágio)" if is_estagio else "IEFP Portal (Emprego)"
                desc = f"{title} - Oferta IEFP. {card_text}"

                jobs.append(Job(
                    title=title, company="Empresa via IEFP", location=location,
                    work_mode="Presencial / Híbrido", link=link, description=desc,
                    source=source_label, pub_date=datetime.date.today().isoformat()
                ))
        except Exception as e:
            logger.debug(f"[IEFP Portal] Error searching '{query}' (tipo={tipo}): {e}")
        return jobs

    def fetch(self) -> List[Job]:
        jobs = []
        seen_links: set = set()
        queries = ["informatica", "data", "python", "inteligencia artificial", "estagio programador", "software"]

        for q in queries:
            for tipo in ["OFERTA_EMPREGO", "OFERTA_ESTAGIO"]:
                found = self._search_offers(q, tipo, seen_links)
                jobs.extend(found)
                time.sleep(random.uniform(1.0, 2.0))

        logger.info(f"[IEFP Portal] Fetched {len(jobs)} job/internship offers.")
        return jobs


class JobIngestionPipeline:
    """Aggregates all structured job portal scrapers concurrently and deduplicates jobs."""
    def __init__(self, itjobs_api_key: str = "", seen_store: Optional[Any] = None, search_queries: Optional[List[str]] = None):
        self.session = get_session(pool_size=45)
        self.itjobs_api_key = itjobs_api_key
        self.seen_store = seen_store
        self.search_queries = search_queries

        is_seen_func = self.seen_store.is_seen_candidate if (self.seen_store and hasattr(self.seen_store, "is_seen_candidate")) else None

        self.linkedin_scraper = LinkedInScraper(session=self.session, is_seen_func=is_seen_func, queries=search_queries)
        self.itjobs_scraper = ITJobsScraper(session=self.session, is_seen_func=is_seen_func)
        self.landing_scraper = LandingJobsScraper(session=self.session)
        self.remotive_scraper = RemotiveScraper(session=self.session)
        self.arbeitnow_scraper = ArbeitnowScraper(session=self.session)
        self.wwr_scraper = WeWorkRemotelyScraper(session=self.session)
        self.remoteok_scraper = RemoteOKScraper(session=self.session)
        self.carga_scraper = CargaDeTrabalhosScraper(session=self.session, is_seen_func=is_seen_func, queries=search_queries)
        self.jobicy_scraper = JobicyScraper(session=self.session)
        self.netempregos_scraper = NetEmpregosScraper(session=self.session, is_seen_func=is_seen_func, queries=search_queries)
        self.jobspresso_scraper = JobspressoScraper(session=self.session)
        self.euraxess_scraper = EuraxessScraper(session=self.session, queries=search_queries)
        self.iefp_scraper = IEFPScraper(session=self.session, is_seen_func=is_seen_func)

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
            ("Net-Empregos", self.netempregos_scraper.fetch),
            ("Jobspresso", self.jobspresso_scraper.fetch),
            ("Euraxess / Ergas", self.euraxess_scraper.fetch),
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
                logger.info(f"ℹ️ [{name}] returned 0 jobs for current queries/filters.")

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

