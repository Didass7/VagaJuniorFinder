from __future__ import annotations
import re
import datetime
import random
import time
import logging
from typing import List, Dict, Set, Optional, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from bs4 import BeautifulSoup
from config import config
from .base import BaseScraper, Job, get_random_headers, clean_job_description, is_valid_job_offer

logger = logging.getLogger("Scraper")

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:134.0) Gecko/20100101 Firefox/134.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.7; rv:133.0) Gecko/20100101 Firefox/133.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36 Edg/132.0.0.0",
]

class LinkedInScraper(BaseScraper):
    """
    High-throughput LinkedIn Public Jobs Scraper.
    Extracts the maximum possible volume of active job postings in Portugal and Remote
    using multi-dimensional search matrix, 10-step continuous pagination, and fast concurrent detail parsing.
    """
    def __init__(self, session: Optional[requests.Session] = None, is_seen_func: Optional[Any] = None, queries: Optional[List[str]] = None):
        super().__init__(session=session, is_seen_func=is_seen_func, queries=queries)

    def _build_search_matrix(self, base_queries: List[str]) -> List[Dict[str, str]]:
        """
        Constructs a comprehensive search matrix covering:
        1. Base candidate profile queries across Portugal
        2. District/City searches (Lisboa, Porto, Braga, Coimbra, Aveiro, etc.)
        3. 100% Remote opportunities in Portugal & Europe (f_WT=2)
        4. Internship & Entry-level filters (f_E=1,2,3)
        5. Broad technology keywords (Software, Data, AI, Python, Developer, Estágio)
        6. Time period filters (f_TPR) to surface different result sets
        7. Job type filters (f_JT) for full-time, internship, contract
        """
        matrix: List[Dict[str, str]] = []
        seen_combos: Set[str] = set()

        # 1. Candidate profile queries
        queries_pool = list(base_queries)
        
        # 2. High-value supplementary tech & junior keywords (significantly expanded)
        supplementary = [
            "junior data", "data scientist", "data analyst", "machine learning",
            "artificial intelligence", "ai engineer", "python developer",
            "junior software engineer", "software engineer", "developer",
            "junior backend", "programador", "estagio ti", "estagio iefp",
            "engenheiro de dados", "cientista de dados", "analista de dados",
            "engenharia informatica", "cloud engineer", "full stack junior",
            # Additional broad tech keywords
            "backend developer", "frontend developer", "full stack developer",
            "devops", "devops engineer", "mlops", "data engineering",
            "deep learning", "nlp engineer", "computer vision",
            "business intelligence", "bi analyst", "power bi",
            "database", "sql developer", "etl developer",
            "junior developer", "trainee developer", "estagiario",
            "software developer", "web developer", "junior web",
            "quality assurance", "qa engineer", "test engineer",
            "cybersecurity", "security analyst", "information security",
            "sistemas de informação", "administrador de sistemas",
            "helpdesk", "it support", "suporte informatico",
            "engenheiro de software", "programador junior",
            "react developer", "java developer", "javascript developer",
            ".net developer", "c# developer", "node.js developer",
            "automation engineer", "rpa developer",
            "product analyst", "data operations",
            "junior consultant", "it consultant",
            "estágio profissional", "primeiro emprego",
            "recém licenciado", "graduate program",
            "trainee program", "internship",
            "analyst", "engineer", "developer portugal",
            "tech", "technology", "informática",
            "IA", "inteligência artificial",
            "LLM", "generative AI", "prompt engineer",
        ]
        for s in supplementary:
            if not any(s.lower() == q.lower() for q in queries_pool):
                queries_pool.append(s)

        # Key Portuguese tech hubs (expanded)
        target_locations = ["Portugal", "Lisboa", "Porto", "Braga", "Coimbra", "Aveiro",
                            "Castelo Branco", "Leiria", "Faro", "Setúbal", "Viseu",
                            "Funchal", "Guimarães", "Évora"]

        for q in queries_pool:
            clean_q = q.strip()
            if not clean_q:
                continue

            # A. National search (Portugal)
            k_pt = f"{clean_q}|Portugal"
            if k_pt not in seen_combos:
                seen_combos.add(k_pt)
                matrix.append({"keywords": clean_q, "location": "Portugal"})

            # B. 100% Remote filter (f_WT=2)
            k_rem = f"{clean_q}|Portugal|remote"
            if k_rem not in seen_combos:
                seen_combos.add(k_rem)
                matrix.append({"keywords": clean_q, "location": "Portugal", "f_WT": "2"})

            # C. Internship & Entry-Level filter (f_E=1,2,3)
            if any(term in clean_q.lower() for term in ["python", "data", "ai", "machine learning", "junior", "estagio", "software", "developer", "engineer", "analyst", "trainee", "intern"]):
                k_entry = f"{clean_q}|Portugal|entry"
                if k_entry not in seen_combos:
                    seen_combos.add(k_entry)
                    matrix.append({"keywords": clean_q, "location": "Portugal", "f_E": "1,2,3"})

            # D. Time period: Past Month (f_TPR=r2592000) — surfaces different result ordering
            if any(term in clean_q.lower() for term in ["python", "data", "ai", "junior", "software", "developer", "engineer", "estagio", "machine learning"]):
                k_month = f"{clean_q}|Portugal|month"
                if k_month not in seen_combos:
                    seen_combos.add(k_month)
                    matrix.append({"keywords": clean_q, "location": "Portugal", "f_TPR": "r2592000"})

            # E. Time period: Past Week (f_TPR=r604800) — freshest listings
            if any(term in clean_q.lower() for term in ["python", "data", "ai", "junior", "estagio", "machine learning", "software"]):
                k_week = f"{clean_q}|Portugal|week"
                if k_week not in seen_combos:
                    seen_combos.add(k_week)
                    matrix.append({"keywords": clean_q, "location": "Portugal", "f_TPR": "r604800"})

            # F. Job type: Full-time (f_JT=F)
            if any(term in clean_q.lower() for term in ["python", "data", "software", "developer", "engineer", "ai"]):
                k_ft = f"{clean_q}|Portugal|fulltime"
                if k_ft not in seen_combos:
                    seen_combos.add(k_ft)
                    matrix.append({"keywords": clean_q, "location": "Portugal", "f_JT": "F"})

            # G. Job type: Internship (f_JT=I)
            if any(term in clean_q.lower() for term in ["estagio", "junior", "trainee", "intern", "data", "python", "software"]):
                k_intern = f"{clean_q}|Portugal|internship"
                if k_intern not in seen_combos:
                    seen_combos.add(k_intern)
                    matrix.append({"keywords": clean_q, "location": "Portugal", "f_JT": "I"})

            # H. Job type: Contract/Temporary (f_JT=C)
            if any(term in clean_q.lower() for term in ["data", "python", "software", "developer", "ai"]):
                k_contract = f"{clean_q}|Portugal|contract"
                if k_contract not in seen_combos:
                    seen_combos.add(k_contract)
                    matrix.append({"keywords": clean_q, "location": "Portugal", "f_JT": "C"})

            # I. Hybrid work filter (f_WT=1)
            if any(term in clean_q.lower() for term in ["python", "data", "ai", "junior", "software"]):
                k_hybrid = f"{clean_q}|Portugal|hybrid"
                if k_hybrid not in seen_combos:
                    seen_combos.add(k_hybrid)
                    matrix.append({"keywords": clean_q, "location": "Portugal", "f_WT": "1"})

        # J. Specific major hub searches for core queries (expanded cities)
        core_queries = [q for q in queries_pool if any(k in q.lower() for k in ["python", "data", "ai", "machine learning", "software", "junior", "estagio", "developer", "engineer", "analyst"])][:15]
        for loc in ["Lisboa", "Porto", "Braga", "Coimbra", "Aveiro", "Leiria", "Setúbal", "Faro"]:
            for cq in core_queries:
                k_loc = f"{cq}|{loc}"
                if k_loc not in seen_combos:
                    seen_combos.add(k_loc)
                    matrix.append({"keywords": cq, "location": f"{loc}, Portugal"})

        # K. European remote searches for high-value queries
        remote_queries = ["python developer", "data scientist", "data analyst", "ai engineer",
                          "machine learning", "junior software engineer", "data engineer",
                          "backend developer", "full stack developer", "nlp engineer",
                          "junior data", "junior developer"]
        for rq in remote_queries:
            k_eu = f"{rq}|Europe|remote"
            if k_eu not in seen_combos:
                seen_combos.add(k_eu)
                matrix.append({"keywords": rq, "location": "European Union", "f_WT": "2"})

        return matrix

    def _fetch_search_cards(self, search_params: Dict[str, str], max_pages: int = 40) -> List[Dict]:
        """
        Paginates through LinkedIn public guest search API in 10-item steps without skipping any postings.
        """
        cards_data: List[Dict] = []
        seen_in_search: Set[str] = set()
        consecutive_empty = 0
        query_str = "&".join(f"{k}={requests.utils.quote(v)}" for k, v in search_params.items())

        for page in range(max_pages):
            # Crucial: LinkedIn guest search API returns 10 items per page; step by 10 to avoid skipping
            start = page * 10
            url = f"https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?{query_str}&start={start}"
            
            headers = get_random_headers()
            headers["User-Agent"] = random.choice(USER_AGENTS)
            headers.update({
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "pt-PT,pt;q=0.9,en-US;q=0.8,en;q=0.7",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
            })

            try:
                resp = self.session.get(url, headers=headers, timeout=(3.0, 8.0))

                # Robust rate-limit handling: retry up to 3 times with escalating backoff
                retry_count = 0
                while resp.status_code == 429 and retry_count < 3:
                    retry_count += 1
                    time.sleep(random.uniform(2.0, 4.0) * retry_count)
                    headers["User-Agent"] = random.choice(USER_AGENTS)
                    resp = self.session.get(url, headers=headers, timeout=(3.0, 8.0))

                if resp.status_code != 200:
                    break

                soup = BeautifulSoup(resp.text, "html.parser")
                cards = soup.find_all("li") or soup.find_all("div", class_=lambda c: c and "base-card" in str(c))
                if not cards:
                    consecutive_empty += 1
                    if consecutive_empty >= 3:
                        break
                    time.sleep(random.uniform(0.3, 0.8))
                    continue

                new_count = 0
                for card in cards:
                    title_elem = card.find("h3", class_=lambda c: c and "title" in str(c)) or card.find("h3") or card.find("h4")
                    link_elem = card.find("a", class_=lambda c: c and "link" in str(c)) or card.find("a")
                    company_elem = card.find("h4", class_=lambda c: c and "subtitle" in str(c)) or card.find("h4") or card.find("h3")
                    loc_elem = card.find("span", class_=lambda c: c and "location" in str(c)) or card.find("span")
                    time_elem = card.find("time")

                    if not link_elem or not link_elem.get("href") or not title_elem:
                        continue

                    raw_link = link_elem.get("href", "")
                    if "/jobs/view/" not in raw_link:
                        continue

                    clean_link = raw_link.split("?")[0].rstrip("/")
                    if clean_link in seen_in_search:
                        continue
                    seen_in_search.add(clean_link)

                    title = title_elem.get_text(separator=" ", strip=True)
                    company = company_elem.get_text(separator=" ", strip=True) if company_elem else "Empresa no LinkedIn"
                    location = loc_elem.get_text(separator=" ", strip=True) if loc_elem else "Portugal"

                    pub_date = datetime.date.today().isoformat()
                    if time_elem and time_elem.get("datetime"):
                        pub_date = time_elem.get("datetime")[:10]

                    if is_valid_job_offer(clean_link, title):
                        cards_data.append({
                            "title": title,
                            "clean_link": clean_link,
                            "company": company,
                            "location": location,
                            "pub_date": pub_date
                        })
                        new_count += 1

                if new_count == 0:
                    consecutive_empty += 1
                    if consecutive_empty >= 3:
                        break
                else:
                    consecutive_empty = 0

                # Small inter-page delay to avoid triggering rate limits
                time.sleep(random.uniform(0.2, 0.6))

            except Exception as e:
                logger.debug(f"[LinkedIn Portal] Search error '{search_params.get('keywords')}' (page {page+1}): {e}")
                break

        return cards_data

    def _fetch_detail_job(self, card_info: Dict) -> Job:
        """
        Fetches full job description with multi-tiered fallback:
        1. LinkedIn guest jobPosting API
        2. Direct job page JSON-LD schema parsing
        3. Direct HTML markup parsing
        4. Structured fallback
        """
        title = card_info["title"]
        clean_link = card_info["clean_link"]
        company = card_info["company"]
        location = card_info["location"]
        pub_date = card_info["pub_date"]

        # If previously seen, we can generate a fast descriptive stub without hitting LinkedIn API
        if self.is_seen_func and self.is_seen_func(title, company):
            desc = f"{title} na empresa {company} ({location}). Oferta de emprego registada no LinkedIn."
            work_mode = "Remoto" if any(r in f"{title} {location}".lower() for r in ["remoto", "remote", "teletrabalho"]) else "Presencial / Híbrido"
            return Job(
                title=title, company=company, location=location,
                work_mode=work_mode, link=clean_link, description=desc,
                source="LinkedIn", pub_date=pub_date
            )

        desc = ""
        try:
            id_match = re.search(r"(\d{8,12})", clean_link)
            if id_match:
                job_posting_id = id_match.group(1)
                guest_api_url = f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_posting_id}"
                headers = get_random_headers()
                headers["User-Agent"] = random.choice(USER_AGENTS)
                headers.update({
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "pt-PT,pt;q=0.9,en-US;q=0.8,en;q=0.7",
                })
                resp = self.session.get(guest_api_url, headers=headers, timeout=(2.5, 5.0))
                if resp.status_code == 200:
                    detail_soup = BeautifulSoup(resp.text, "html.parser")
                    markup = (
                        detail_soup.find("div", class_=lambda c: c and "show-more-less-html__markup" in str(c)) or
                        detail_soup.find("section", class_=lambda c: c and "description" in str(c)) or
                        detail_soup.find("div", class_=lambda c: c and "description__text" in str(c))
                    )
                    text_content = markup.get_text(separator=" ", strip=True) if markup else ""

                    criteria_list = []
                    criteria_elem = detail_soup.find("ul", class_=lambda c: c and "job-criteria" in str(c))
                    if criteria_elem:
                        for li in criteria_elem.find_all("li"):
                            criteria_list.append(li.get_text(separator=": ", strip=True))

                    extra_texts = []
                    for p in detail_soup.find_all(["p", "span", "div"]):
                        p_txt = p.get_text(strip=True)
                        if any(k in p_txt.lower() for k in ["level of experience", "anos de experi", "years of experi"]):
                            extra_texts.append(p.get_text(separator=" ", strip=True))

                    full_parts = [title]
                    if criteria_list:
                        full_parts.append(" | ".join(criteria_list))
                    if extra_texts:
                        full_parts.append(" | ".join(extra_texts))
                    if text_content:
                        full_parts.append(clean_job_description(text_content))

                    combined = " - ".join(full_parts)
                    if len(combined) > 80:
                        desc = combined
        except Exception as d_err:
            logger.debug(f"LinkedIn guest API failed for {clean_link}: {d_err}")

        # Fallback 2: Parse direct job page with JSON-LD / HTML
        if not desc or len(desc) < 80:
            try:
                headers = get_random_headers()
                headers["User-Agent"] = random.choice(USER_AGENTS)
                resp = self.session.get(clean_link, headers=headers, timeout=(2.5, 5.0))
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, "html.parser")
                    import html as html_lib
                    import json as json_lib
                    for script in soup.find_all("script", type="application/ld+json"):
                        try:
                            ld_data = json_lib.loads(script.string)
                            if isinstance(ld_data, dict) and "description" in ld_data:
                                raw_desc = html_lib.unescape(ld_data["description"])
                                clean_text = BeautifulSoup(raw_desc, "html.parser").get_text(separator=" ", strip=True)
                                if len(clean_text) > 80:
                                    desc = f"{title} - {clean_job_description(clean_text)}"
                                    break
                        except Exception:
                            pass

                    if not desc or len(desc) < 80:
                        markup = (
                            soup.find("div", class_=lambda c: c and "show-more-less-html__markup" in str(c)) or
                            soup.find("section", class_=lambda c: c and "description" in str(c))
                        )
                        if markup:
                            text = markup.get_text(separator=" ", strip=True)
                            if len(text) > 80:
                                desc = f"{title} - {clean_job_description(text)}"
            except Exception as page_err:
                logger.debug(f"LinkedIn direct page fallback failed for {clean_link}: {page_err}")

        # Fallback 3: Clean structured description
        if not desc or len(desc) < 80:
            desc = f"{title} na empresa {company} ({location}). Oportunidade de emprego publicada no LinkedIn Jobs Portugal com foco em tecnologia e engenharia informática."

        work_mode = "Remoto" if any(r in f"{title} {location} {desc}".lower() for r in ["remoto", "remote", "teletrabalho"]) else "Presencial / Híbrido"

        return Job(
            title=title, company=company, location=location,
            work_mode=work_mode, link=clean_link, description=desc,
            source="LinkedIn", pub_date=pub_date
        )

    def fetch(self) -> List[Job]:
        raw_queries = self.queries or config.candidate.search_queries or [
            "Junior AI", "Junior Data Scientist", "Machine Learning Trainee",
            "Data Engineer Trainee", "Entry level AI", "Entry level Data"
        ]
        
        # 1. Generate full search matrix across queries, remote filter, and experience levels
        search_matrix = self._build_search_matrix(raw_queries)
        logger.info(f"[LinkedIn Portal] Launching comprehensive search matrix with {len(search_matrix)} targeted queries across Portugal & Remote...")

        all_cards: List[Dict] = []
        seen_links: Set[str] = set()

        # 2. Fetch query cards concurrently across all searches in the matrix
        with ThreadPoolExecutor(max_workers=min(len(search_matrix), 16)) as executor:
            future_to_search = {executor.submit(self._fetch_search_cards, s): s for s in search_matrix}
            for future in as_completed(future_to_search):
                try:
                    res = future.result()
                    for card in res:
                        if card["clean_link"] not in seen_links:
                            seen_links.add(card["clean_link"])
                            all_cards.append(card)
                except Exception as e:
                    logger.debug(f"[LinkedIn Portal] Error fetching search matrix batch: {e}")

        logger.info(f"[LinkedIn Portal] Discovered {len(all_cards)} total unique job offers on LinkedIn. Fetching full details in parallel...")

        # 3. Fetch full details in parallel with high worker pool
        jobs: List[Job] = []
        cards_to_fetch = all_cards
        if cards_to_fetch:
            with ThreadPoolExecutor(max_workers=min(len(cards_to_fetch), 30)) as executor:
                future_to_detail = {executor.submit(self._fetch_detail_job, card): card for card in cards_to_fetch}
                for future in as_completed(future_to_detail):
                    try:
                        job = future.result()
                        if job.description and len(job.description) >= 30:
                            jobs.append(job)
                    except Exception as e:
                        logger.debug(f"[LinkedIn Portal] Error fetching job detail: {e}")

        logger.info(f"[LinkedIn Portal] Safely fetched {len(jobs)} fresh jobs with full detail body parsing across all available pages.")
        return jobs



