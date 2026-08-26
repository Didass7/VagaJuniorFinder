from __future__ import annotations
import hashlib
import logging
import re
import datetime
import random
import string
from dataclasses import dataclass
from typing import List, Dict, Set, Optional, Any, Callable, Tuple
import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry
from bs4 import BeautifulSoup
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
        allowed_methods=["GET", "POST"],
        raise_on_status=False
    )
    
    adapter = HTTPAdapter(pool_connections=pool_size, pool_maxsize=pool_size, max_retries=retries)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.headers.update(get_random_headers())
    return session

def safe_fetch(url: str, session: Optional[requests.Session] = None, timeout: float = 12.0, headers: Optional[Dict[str, str]] = None) -> Tuple[int, str, bytes]:
    """
    Robust HTTP fetcher using curl_cffi Chrome impersonation (bypasses Cloudflare 403 & WAF on GitHub Actions runners)
    with automatic fallback to requests.Session.
    """
    try:
        from curl_cffi import requests as cureq
        if headers:
            resp = cureq.get(url, headers=headers, impersonate="chrome120", allow_redirects=True, timeout=int(timeout))
        else:
            resp = cureq.get(url, impersonate="chrome120", allow_redirects=True, timeout=int(timeout))
        return resp.status_code, resp.text, resp.content
    except Exception:
        pass
        
    try:
        s = session or requests.Session()
        h = headers or get_random_headers()
        resp = s.get(url, headers=h, allow_redirects=True, timeout=(4.0, timeout))
        return resp.status_code, resp.text, resp.content
    except Exception:
        return 0, "", b""


# Non-job documentation / blog / sponsored domains to exclude
NON_JOB_DOMAINS = [
    "aws.amazon.com", "amazon.com/what-is", "wikipedia.org", "medium.com",
    "github.com", "youtube.com", "google.com", "dev.to", "towardsdatascience.com"
]

# Non-tech noise titles to filter out during ingestion (administrative, sales, non-IT)
PRE_FILTER_DISQUALIFIERS = [
    "salesforce", "sap ", "diagram creator", "diagram creators", "digital design", "circuit design",
    "verilog", "systemverilog", "vhdl", "fpga", "asic", "hardware design",
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

COMPANY_STRIP_SUFFIXES = [
    r"\bconclusion(?:\s+group)?\b",
    r"\bconsulting\b",
    r"\bconsultancy\b",
    r"\bsolutions\b",
    r"\btechnologies\b",
    r"\btechnology\b",
    r"\btech\b",
    r"\bdigital\b",
    r"\bservices\b",
    r"\bgroup\b",
    r"\bgrupo\b",
    r"\bportugal\b",
    r"\bpt\b",
    r"\bcorp\b",
    r"\bcorporation\b",
    r"\binc\b",
    r"\bllc\b",
    r"\bltd\b",
    r"\blimited\b",
    r"\bgmbh\b",
    r"\bs\.?a\.?\b",
    r"\blda\.?\b",
    r"\bunipessoal\b",
    r"\bholding\b",
    r"\bholdings\b",
    r"\bsystems\b",
    r"\binternational\b",
    r"\bglobal\b",
    r"\beurope\b",
]

def clean_company_name(company: str) -> str:
    if not company:
        return "Empresa Confidencial"
    c = company.strip()
    for pat in NOISE_COMPANY_PATTERNS:
        c = re.sub(pat, "", c, flags=re.IGNORECASE).strip()
    c = re.sub(r"[\s\-\|]+$", "", c).strip()
    return c if c else company.strip()

def normalize_company_name(company: str) -> str:
    if not company:
        return ""
    c = clean_company_name(company).lower().strip()
    c = re.sub(r"\[.*?\]|\(.*?\)", " ", c)
    c = c.translate(str.maketrans(string.punctuation, ' ' * len(string.punctuation)))
    for pat in COMPANY_STRIP_SUFFIXES:
        c = re.sub(pat, " ", c, flags=re.IGNORECASE)
    return " ".join(c.split())

def normalize_title_name(title: str) -> str:
    if not title:
        return ""
    t = title.lower().strip()
    t = re.sub(r"\(\s*m\s*/\s*f\s*(?:/\s*[a-z])?\s*\)|\(\s*m\s*/\s*w\s*/\s*d\s*\)", " ", t)
    noise = r"\b(lisboa|porto|portugal|remote|remoto|hybrid|híbrido|hibrido|presencial|estágio|estagio|iefp|ativar|júnior|junior|recém|recem|licenciado|graduates|full-time|fulltime)\b"
    t = re.sub(noise, " ", t, flags=re.IGNORECASE)
    t = t.translate(str.maketrans(string.punctuation, ' ' * len(string.punctuation)))
    return " ".join(t.split())

def get_job_dedup_key(title: str, company: str) -> str:
    nc = normalize_company_name(company)
    nt = normalize_title_name(title)
    return f"{nt}__{nc}"

def normalize_title_company_for_hash(title: str, company: str) -> str:
    return get_job_dedup_key(title, company)

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


class BaseScraper:
    """Base class for all portal scrapers providing shared session, queries, seen-checking, and error handling."""
    def __init__(
        self,
        session: Optional[requests.Session] = None,
        is_seen_func: Optional[Callable[[str, str], bool]] = None,
        queries: Optional[List[str]] = None
    ):
        self.session = session or get_session()
        self.is_seen_func = is_seen_func
        self.queries = queries

    def fetch(self) -> List[Job]:
        raise NotImplementedError("Subclasses must implement fetch()")
