from __future__ import annotations
import sys
import os
import io
import re
import time
import datetime
import logging
import requests

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from typing import Dict, Any, List, Optional
from bs4 import BeautifulSoup
from core.config import config, load_config
from scrapers import Job, clean_job_description, get_random_headers
from core.matcher import JobMatcher, ScoredJob
from core.ai_evaluator import AIEvaluator

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("ReevaluateNotion")

NOTION_API_URL = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"

def fetch_linkedin_full_description(url: str, session: requests.Session) -> str:
    """Fetches the full 3000+ character description from LinkedIn guest API with retry support."""
    try:
        id_match = re.search(r"(\d{6,14})", url)
        if not id_match:
            return ""
        job_id = id_match.group(1)
        api_url = f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"
        
        for attempt in range(1, 3):
            headers = get_random_headers()
            headers.update({
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Accept-Language": "pt-PT,pt;q=0.9,en-US;q=0.8,en;q=0.7",
            })
            time.sleep(0.5)
            resp = session.get(api_url, headers=headers, timeout=12)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                markup = (
                    soup.find("div", class_=lambda c: c and "show-more-less-html__markup" in str(c)) or
                    soup.find("section", class_=lambda c: c and "description" in str(c)) or
                    soup.find("div", class_=lambda c: c and "description__text" in str(c))
                )
                if markup:
                    return clean_job_description(markup.get_text(separator=" ", strip=True))
                return clean_job_description(soup.get_text(separator=" ", strip=True))
            elif resp.status_code == 429:
                logger.info(f"  ↳ LinkedIn 429 rate limit. Waiting 2.5s (attempt {attempt}/2)...")
                time.sleep(2.5)
            elif resp.status_code in [404, 410]:
                logger.info(f"  ↳ Job posting {job_id} is no longer available on LinkedIn (HTTP {resp.status_code}).")
                break
    except Exception as e:
        logger.debug(f"Failed fetching LinkedIn job for {url}: {e}")
    return ""

def fetch_generic_job_description(url: str, session: requests.Session) -> str:
    """Fetches text description for non-LinkedIn portals."""
    try:
        clean_url = url.strip()
        if not clean_url.startswith("http://") and not clean_url.startswith("https://"):
            clean_url = "https://" + clean_url
        headers = get_random_headers()
        time.sleep(0.3)
        resp = session.get(clean_url, headers=headers, timeout=10)
        if resp.status_code == 200:
            return clean_job_description(resp.text)
    except Exception as e:
        logger.debug(f"Failed fetching generic job for {url}: {e}")
    return ""

def fetch_notion_page_text(page_id: str, headers: dict) -> str:
    """Fetches text content from Notion page blocks as fallback when web fetch fails."""
    try:
        url = f"{NOTION_API_URL}/blocks/{page_id}/children?page_size=50"
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            blocks = resp.json().get("results", [])
            text_parts = []
            for b in blocks:
                b_type = b.get("type", "")
                if b_type in b and "rich_text" in b[b_type]:
                    for rt in b[b_type]["rich_text"]:
                        content = rt.get("text", {}).get("content", "")
                        if content:
                            text_parts.append(content)
            return " ".join(text_parts).strip()
    except Exception:
        pass
    return ""

def safe_notion_patch(page_id: str, patch_props: dict, headers: dict, max_retries: int = 3) -> bool:
    """Executes a Notion page patch with automatic retries on timeout or 429/500 errors."""
    url = f"{NOTION_API_URL}/pages/{page_id}"
    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.patch(url, headers=headers, json={"properties": patch_props}, timeout=25)
            if resp.status_code == 200:
                return True
            elif resp.status_code == 429:
                logger.warning(f"  ↳ Notion API 429 rate limited. Backing off 3s (attempt {attempt}/{max_retries})...")
                time.sleep(3)
            else:
                logger.warning(f"  ↳ Notion patch returned {resp.status_code}: {resp.text[:200]}")
                time.sleep(1)
        except Exception as e:
            logger.warning(f"  ↳ Notion patch timeout/network issue: {e}. Retrying (attempt {attempt}/{max_retries})...")
            time.sleep(2)
    return False

def reevaluate_notion_jobs_for_profile(profile_name: str):
    os.environ["ACTIVE_PROFILE"] = profile_name
    current_config = load_config()

    token = current_config.notion_token
    database_id = current_config.notion_database_id

    if not token or not database_id:
        logger.warning(f"⚠️ Skipping profile '{profile_name}': NOTION_TOKEN or NOTION_DATABASE_ID not configured.")
        return

    logger.info("==================================================")
    logger.info(f"🚀 RE-EVALUATING NOTION DATABASE FOR: {current_config.candidate.name} ({profile_name})")
    logger.info(f"📋 Database ID: {database_id}")
    logger.info("==================================================")

    headers = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json"
    }

    # Fetch database schema to map property names correctly
    schema_resp = requests.get(f"{NOTION_API_URL}/databases/{database_id}", headers=headers, timeout=20)
    if schema_resp.status_code != 200:
        logger.error(f"❌ Failed to fetch database schema for {profile_name}: {schema_resp.text}")
        return
    schema = schema_resp.json().get("properties", {})

    logger.info(f"🔍 Querying Notion database for pages needing re-evaluation ({profile_name})...")
    url = f"{NOTION_API_URL}/databases/{database_id}/query"
    
    pages_to_process = []
    has_more = True
    start_cursor = None

    while has_more:
        payload: Dict[str, Any] = {"page_size": 100}
        if start_cursor:
            payload["start_cursor"] = start_cursor

        resp = None
        for q_attempt in range(1, 4):
            try:
                resp = requests.post(url, headers=headers, json=payload, timeout=25)
                if resp.status_code == 200:
                    break
                elif resp.status_code == 429:
                    time.sleep(3)
            except Exception as e:
                logger.warning(f"Query attempt {q_attempt} timed out ({e}). Retrying in 2s...")
                time.sleep(2)

        if not resp or resp.status_code != 200:
            logger.error(f"❌ Query error for {profile_name}")
            break

        data = resp.json()
        for page in data.get("results", []):
            page_id = page.get("id")
            props = page.get("properties", {})
            
            # Title
            title = ""
            for p in props.values():
                if p.get("type") == "title":
                    title_list = p.get("title", [])
                    if title_list:
                        title = title_list[0].get("text", {}).get("content", "")
                    break

            # URL
            link = ""
            for p in props.values():
                if p.get("type") == "url" and p.get("url"):
                    link = p.get("url")
                    break

            # Company
            company = ""
            if "Empresa" in props and props["Empresa"].get("rich_text"):
                company = props["Empresa"]["rich_text"][0].get("text", {}).get("content", "")

            # Location / Mode
            mode = "Presencial / Híbrido"
            if "Modo" in props and props["Modo"].get("select"):
                mode = props["Modo"]["select"].get("name", mode)

            # Estado / Status
            estado = "Por Candidatar"
            if "Estado" in props and props["Estado"].get("select"):
                estado = props["Estado"]["select"].get("name", estado)

            # Senioridade
            seniority_val = ""
            if "Senioridade" in props and props["Senioridade"].get("select"):
                seniority_val = props["Senioridade"]["select"].get("name", "")

            # Analysis text
            analysis = ""
            if "Análise IA" in props and props["Análise IA"].get("rich_text"):
                analysis_list = props["Análise IA"].get("rich_text", [])
                if analysis_list:
                    analysis = analysis_list[0].get("text", {}).get("content", "")

            pages_to_process.append({
                "page_id": page_id,
                "title": title,
                "link": link,
                "company": company,
                "mode": mode,
                "analysis": analysis,
                "estado": estado
            })

        has_more = data.get("has_more", False)
        start_cursor = data.get("next_cursor")

    logger.info(f"📊 Found {len(pages_to_process)} total pages to re-evaluate in Notion for {profile_name}.")

    # Initialize Matcher and AI Evaluator for this profile
    matcher = JobMatcher(profile=current_config.candidate)
    ai_evaluator = AIEvaluator()
    logger.info(f"🤖 AI Evaluator Status: {'ACTIVE (' + ai_evaluator.active_provider + ')' if ai_evaluator.is_available else 'INACTIVE (Heuristic Only)'}")

    session = requests.Session()
    updated_count = 0
    disqualified_count = 0

    for idx, item in enumerate(pages_to_process, 1):
        page_id = item["page_id"]
        title = item["title"]
        link = item["link"]
        company = item["company"]
        mode = item.get("mode", "Presencial / Híbrido")
        current_estado = item.get("estado", "Por Candidatar")
        
        # If user already applied or is in interview, NEVER touch or overwrite their candidacy score/status
        if current_estado in ["Candidatado", "Entrevista", "Oferta", "Rejeitado Empresa"]:
            logger.info(f"[{idx}/{len(pages_to_process)}] 🛡️ ACTIVE CANDIDACY ({current_estado}): Preserving '{title}' @ '{company}' without modifications.")
            continue

        logger.info(f"[{idx}/{len(pages_to_process)}] Processing '{title}' @ '{company}'...")

        # 1. Fetch real description (try web first, then Notion page blocks fallback)
        desc = ""
        if "linkedin.com" in link:
            desc = fetch_linkedin_full_description(link, session)
        elif link:
            desc = fetch_generic_job_description(link, session)
        
        if not desc or len(desc) < 150:
            page_text = fetch_notion_page_text(page_id, headers)
            if page_text and len(page_text) >= 150:
                desc = page_text
        
        # If full description cannot be retrieved, do NOT guess or falsely disqualify — preserve existing score
        if not desc or len(desc) < 150:
            logger.info(f"  ↳ ⚠️ Insufficient description text (<150 chars). Preserving existing page score without modification.")
            continue

        job = Job(
            title=title,
            company=company,
            location="Portugal",
            work_mode=mode,
            link=link,
            description=desc,
            source="LinkedIn" if "linkedin" in link else "Outro",
            pub_date=datetime.date.today().isoformat()
        )

        # 2. Re-evaluate with Matcher & AI
        scored_jobs = matcher.process_jobs([job], include_disqualified=True)
        
        # A job is qualified ONLY if it passed Stage 1 (>= 55%) and was approved by AI Stage 2 (or score >= 50% if AI is disabled)
        is_qualified = False
        if scored_jobs and scored_jobs[0].score >= 50.0:
            if ai_evaluator.is_available:
                is_qualified = bool(scored_jobs[0].ai_evaluated and scored_jobs[0].score > 0)
            else:
                is_qualified = True

        if not is_qualified:
            # Job is disqualified by heuristic or AI
            disqualified_count += 1
            reason = scored_jobs[0].match_reason if (scored_jobs and scored_jobs[0].match_reason) else "Requisitos não adequados para Júnior"
            seniority = scored_jobs[0].seniority_status if (scored_jobs and scored_jobs[0].seniority_status) else "Desqualificada"
            ai_reason_text = scored_jobs[0].ai_reasoning if (scored_jobs and scored_jobs[0].ai_reasoning) else f"❌ Rejeitada: {reason}"
            logger.info(f"  ↳ ❌ DISQUALIFIED: {ai_reason_text} ({seniority})")

            patch_props = {}
            if "Match Score (%)" in schema:
                patch_props["Match Score (%)"] = {"number": 0.0}
            if "Senioridade" in schema:
                patch_props["Senioridade"] = {"select": {"name": seniority[:100]}}
            if "Estado" in schema and current_estado not in ["Entrevista", "Candidatado", "Oferta"]:
                patch_props["Estado"] = {"select": {"name": "Desqualificada"}}
            if "Análise IA" in schema:
                patch_props["Análise IA"] = {"rich_text": [{"text": {"content": ai_reason_text[:1990]}}]}

            safe_notion_patch(page_id, patch_props, headers)
            time.sleep(0.3)
            continue

        sj = scored_jobs[0]
        logger.info(f"  ↳ ✅ QUALIFIED: Score {sj.score}% | Seniority: {sj.seniority_status} | Skills: {', '.join(sj.matched_skills)}")

        # 3. Patch Notion page with real score and analysis
        patch_props = {}
        if "Match Score (%)" in schema:
            patch_props["Match Score (%)"] = {"number": float(sj.score)}
        if "Senioridade" in schema:
            seniority_clean = "Recém-licenciado" if any(t in sj.seniority_status.lower() for t in ["recém", "recem", "0-1", "estágio", "estagio", "iefp", "ativar"]) else "Júnior"
            patch_props["Senioridade"] = {"select": {"name": seniority_clean}}
        if "Análise IA" in schema:
            reason_text = sj.ai_reasoning if sj.ai_reasoning else sj.match_reason
            patch_props["Análise IA"] = {"rich_text": [{"text": {"content": reason_text[:1990]}}]}

        # If it was marked as Desqualificada earlier, restore it back to Por Candidatar (preserve Entrevista/Candidatado)
        if "Estado" in schema and current_estado in ["Desqualificada", "Rejeitada", "Não Adequada", "Nao Adequada"]:
            patch_props["Estado"] = {"select": {"name": "Por Candidatar"}}

        success = safe_notion_patch(page_id, patch_props, headers)
        if success:
            updated_count += 1
            logger.info(f"  ↳ Updated Notion page successfully.")
        else:
            logger.warning(f"  ↳ Failed to update Notion page after retries.")

        time.sleep(1.0)

    logger.info("==================================================")
    logger.info(f"🎉 Re-evaluation complete for {profile_name}! {updated_count} jobs updated, {disqualified_count} jobs flagged/disqualified.")
    logger.info("==================================================")

def reevaluate_all_profiles():
    import glob
    profiles_dir = "profiles"
    if not os.path.exists(profiles_dir):
        reevaluate_notion_jobs_for_profile("diogo_ai")
        return

    profile_files = sorted(glob.glob(os.path.join(profiles_dir, "*.json")))
    if not profile_files:
        reevaluate_notion_jobs_for_profile("diogo_ai")
        return

    for p_file in profile_files:
        p_name = os.path.splitext(os.path.basename(p_file))[0]
        reevaluate_notion_jobs_for_profile(p_name)

if __name__ == "__main__":
    reevaluate_all_profiles()
