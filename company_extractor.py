import re
import requests
import logging
from bs4 import BeautifulSoup
from typing import Optional

logger = logging.getLogger("CompanyExtractor")

WEB_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
}

GENERIC_COMPANY_NAMES = {
    "empresa", "empresa via itjobs", "empresa via net-empregos", "empresa no linkedin",
    "empresa via carga de trabalhos", "empresa confidencial", "desconhecida", "n/a",
    "landing.jobs company", "remotive company", "arbeitnow company", "weworkremotely company",
    "remoteok company", "jobicy company", ""
}

def is_generic_company(name: Optional[str]) -> bool:
    if not name:
        return True
    clean = name.strip().lower()
    return clean in GENERIC_COMPANY_NAMES or clean.startswith("empresa via") or clean.startswith("empresa no")

_COMPANY_CACHE = {}

def extract_company_from_link(link: str, title: str = "", current_company: str = "") -> str:
    """Extracts a real, clean company name from job link, page title, or HTML metadata."""
    if current_company and not is_generic_company(current_company):
        return current_company.strip()

    if not link:
        return current_company if current_company else "Empresa Confidencial"

    if link in _COMPANY_CACHE:
        return _COMPANY_CACHE[link]

    link_lower = link.lower()

    result = None
    # 1. LinkedIn URL slug pattern: ...-at-company-name-12345678
    m = re.search(r'-at-([a-z0-9\-]+)-\d+', link, re.I)
    if m:
        slug_company = m.group(1).replace('-', ' ').title()
        if not is_generic_company(slug_company) and len(slug_company) > 1:
            result = slug_company

    # 2. Try web fetch for portals
    if not result:
        try:
            r = requests.get(link, headers=WEB_HEADERS, timeout=6)
            if r.status_code == 200:
                soup = BeautifulSoup(r.text, 'html.parser')

                # ITJobs.pt
                if 'itjobs.pt' in link_lower:
                    if soup.title:
                        parts = [p.strip() for p in soup.title.text.split(' - ')]
                        if len(parts) >= 3 and parts[-1] == 'ITJobs':
                            c_val = parts[-2]
                            if not is_generic_company(c_val):
                                result = c_val
                    if not result:
                        for a in soup.find_all('a', href=True):
                            if '/empresa/' in a['href'] or '/company/' in a['href']:
                                txt = a.get_text(strip=True)
                                if not is_generic_company(txt) and len(txt) > 1 and txt.lower() not in ['empresas', 'empresa', 'login']:
                                    result = txt
                                    break

                # Net-Empregos.com
                elif 'net-empregos.com' in link_lower:
                    for a in soup.find_all('a', href=True):
                        if '/emprego-empresa-id/' in a['href']:
                            txt = a.get_text(strip=True)
                            if not is_generic_company(txt) and len(txt) > 1:
                                result = txt
                                break

                # Carga de Trabalhos
                elif 'cargadetrabalhos.pt' in link_lower:
                    for tag in soup.find_all(['strong', 'b', 'h2', 'h3']):
                        txt = tag.get_text(strip=True)
                        if txt and not is_generic_company(txt) and 2 < len(txt) < 50:
                            result = txt
                            break

                # Generic HTML title parsing: "Job Title - Company Name" or "Job Title at Company Name"
                if not result and soup.title:
                    t_text = soup.title.text.strip()
                    if ' at ' in t_text:
                        c_val = t_text.split(' at ')[-1].split('|')[0].split('-')[0].strip()
                        if not is_generic_company(c_val) and len(c_val) > 1:
                            result = c_val
                    elif ' - ' in t_text:
                        parts = [p.strip() for p in t_text.split(' - ')]
                        if len(parts) >= 2 and not is_generic_company(parts[1]):
                            result = parts[1][:60]

        except Exception as e:
            logger.debug(f"Could not extract company from {link}: {e}")

    # Final fallback: return current_company if non-empty, else "Empresa Confidencial"
    if not result:
        result = current_company.strip() if current_company and current_company.strip() else "Empresa Confidencial"

    _COMPANY_CACHE[link] = result
    return result
