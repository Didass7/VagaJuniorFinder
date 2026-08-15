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
from config import config, load_config
from scraper import Job, clean_job_description, get_random_headers
from matcher import JobMatcher, ScoredJob
from ai_evaluator import AIEvaluator

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
    """Fetches the full 3000+ character description from LinkedIn guest API."""
    try:
        id_match = re.search(r"(\d{8,12})", url)
        if not id_match:
            return ""
        job_id = id_match.group(1)
        api_url = f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"
        headers = get_random_headers()
        headers.update({
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "pt-PT,pt;q=0.9,en-US;q=0.8,en;q=0.7",
        })
        time.sleep(0.4)
        resp = session.get(api_url, headers=headers, timeout=10)
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
    except Exception as e:
        logger.debug(f"Failed fetching LinkedIn job for {url}: {e}")
    return ""

def fetch_generic_job_description(url: str, session: requests.Session) -> str:
    """Fetches text description for non-LinkedIn portals."""
    try:
        headers = get_random_headers()
        time.sleep(0.3)
        resp = session.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            return clean_job_description(resp.text)
    except Exception as e:
        logger.debug(f"Failed fetching generic job for {url}: {e}")
    return ""

def reevaluate_notion_jobs():
    token = config.notion_token
    database_id = config.notion_database_id

    if not token or not database_id:
        logger.error("❌ NOTION_TOKEN or NOTION_DATABASE_ID not configured.")
        return

    headers = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json"
    }

    # Fetch database schema to map property names correctly
    schema_resp = requests.get(f"{NOTION_API_URL}/databases/{database_id}", headers=headers, timeout=15)
    if schema_resp.status_code != 200:
        logger.error(f"❌ Failed to fetch database schema: {schema_resp.text}")
        return
    schema = schema_resp.json().get("properties", {})

    logger.info("🔍 Querying Notion database for pages needing re-evaluation...")
    url = f"{NOTION_API_URL}/databases/{database_id}/query"
    
    pages_to_process = []
    has_more = True
    start_cursor = None

    while has_more:
        payload: Dict[str, Any] = {"page_size": 100}
        if start_cursor:
            payload["start_cursor"] = start_cursor

        resp = requests.post(url, headers=headers, json=payload, timeout=15)
        if resp.status_code != 200:
            logger.error(f"❌ Query error ({resp.status_code}): {resp.text}")
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

    logger.info(f"📊 Found {len(pages_to_process)} total pages in Notion.")

    # Initialize Matcher and AI Evaluator
    matcher = JobMatcher(profile=config.candidate)
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
        mode = item["mode"]
        current_estado = item.get("estado", "Por Candidatar")
        
        logger.info(f"[{idx}/{len(pages_to_process)}] Processing '{title}' @ '{company}'...")

        # 1. Fetch real description
        desc = ""
        if "linkedin.com" in link:
            desc = fetch_linkedin_full_description(link, session)
        else:
            desc = fetch_generic_job_description(link, session)
        
        if not desc or len(desc) < 80:
            logger.info(f"  ↳ Could not fetch fresh full description. Skipping.")
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
        scored_jobs = matcher.process_jobs([job])
        if not scored_jobs or scored_jobs[0].score == 0:
            # Job is disqualified by heuristic or AI
            disqualified_count += 1
            reason = scored_jobs[0].match_reason if scored_jobs else "Requisitos não adequados para Júnior"
            seniority = scored_jobs[0].seniority_status if scored_jobs else "Desqualificada"
            logger.info(f"  ↳ ❌ DISQUALIFIED: {reason} ({seniority})")

            # Only update status to Desqualificada if it's not a manual user status like Entrevista/Candidatado
            patch_props = {}
            if "Match Score (%)" in schema:
                patch_props["Match Score (%)"] = {"number": 0.0}
            if "Senioridade" in schema:
                patch_props["Senioridade"] = {"select": {"name": seniority[:100]}}
            if "Análise IA" in schema:
                patch_props["Análise IA"] = {"rich_text": [{"text": {"content": f"❌ Rejeitada: {reason}"}}]}

            requests.patch(f"{NOTION_API_URL}/pages/{page_id}", headers=headers, json={"properties": patch_props}, timeout=15)
            time.sleep(0.35)
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
        if "Estado" in schema and current_estado in ["Desqualificada", "Rejeitada"]:
            patch_props["Estado"] = {"select": {"name": "Por Candidatar"}}

        patch_resp = requests.patch(f"{NOTION_API_URL}/pages/{page_id}", headers=headers, json={"properties": patch_props}, timeout=15)
        if patch_resp.status_code == 200:
            updated_count += 1
            logger.info(f"  ↳ Updated Notion page successfully.")
        else:
            logger.warning(f"  ↳ Notion patch error ({patch_resp.status_code}): {patch_resp.text}")

        time.sleep(0.35)

    logger.info("==================================================")
    logger.info(f"🎉 Re-evaluation complete! {updated_count} jobs updated, {disqualified_count} jobs flagged/disqualified.")
    logger.info("==================================================")

if __name__ == "__main__":
    reevaluate_notion_jobs()
