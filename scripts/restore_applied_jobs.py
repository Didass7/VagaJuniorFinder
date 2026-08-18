"""
restore_applied_jobs.py — Restores match scores and positive status for active candidacies in Notion.

Finds all job pages in Notion marked as "Candidatado", "Entrevista", or "Oferta" whose
scores were inadvertently zeroed out by re-evaluation, and restores them to healthy match scores.
"""

import sys
import io
import os
import re
import time
import logging
import requests
from typing import Dict, Any, List

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("RestoreAppliedJobs")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config

NOTION_API_URL = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"

def safe_notion_patch(page_id: str, properties: Dict[str, Any], headers: Dict[str, str], max_retries: int = 4) -> bool:
    url = f"{NOTION_API_URL}/pages/{page_id}"
    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.patch(url, headers=headers, json={"properties": properties}, timeout=15)
            if resp.status_code == 200:
                return True
            elif resp.status_code == 429:
                delay = attempt * 3
                logger.warning(f"⚠️ Notion API 429. Retrying in {delay}s...")
                time.sleep(delay)
            else:
                logger.error(f"❌ Notion patch failed ({resp.status_code}): {resp.text}")
                return False
        except Exception as e:
            if attempt < max_retries:
                time.sleep(attempt * 2)
            else:
                logger.error(f"Exception during patch: {e}")
                return False
    return False

def run_restore():
    token = config.notion_token
    db_id = config.notion_database_id

    if not token or not db_id:
        logger.error("❌ Notion token or database ID not configured in environment / .env.")
        return

    headers = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json"
    }

    # 1. Fetch schema
    db_url = f"{NOTION_API_URL}/databases/{db_id}"
    resp = requests.get(db_url, headers=headers, timeout=15)
    if resp.status_code != 200:
        logger.error(f"❌ Could not fetch database schema ({resp.status_code}): {resp.text}")
        return

    schema = resp.json().get("properties", {})

    # 2. Query all pages
    query_url = f"{NOTION_API_URL}/databases/{db_id}/query"
    has_more = True
    start_cursor = None
    all_pages = []

    logger.info("🔍 Fetching all pages from Notion database...")
    while has_more:
        payload: Dict[str, Any] = {"page_size": 100}
        if start_cursor:
            payload["start_cursor"] = start_cursor

        resp = requests.post(query_url, headers=headers, json=payload, timeout=15)
        if resp.status_code != 200:
            logger.error(f"❌ Error querying Notion: {resp.text}")
            break

        data = resp.json()
        all_pages.extend(data.get("results", []))
        has_more = data.get("has_more", False)
        start_cursor = data.get("next_cursor")

    logger.info(f"📊 Retrieved {len(all_pages)} total pages from Notion.")

    restored_count = 0

    for page in all_pages:
        page_id = page.get("id")
        props = page.get("properties", {})

        title = ""
        for p in props.values():
            if p.get("type") == "title":
                tl = p.get("title", [])
                if tl:
                    title = tl[0].get("text", {}).get("content", "")
                break

        company = ""
        if "Empresa" in props and props["Empresa"].get("rich_text"):
            cl = props["Empresa"]["rich_text"]
            if cl:
                company = cl[0].get("text", {}).get("content", "")

        estado = "Por Candidatar"
        if "Estado" in props and props["Estado"].get("select"):
            estado = props["Estado"]["select"].get("name", estado)

        current_score = None
        if "Match Score (%)" in props and props["Match Score (%)"].get("number") is not None:
            current_score = props["Match Score (%)"]["number"]

        analysis_text = ""
        if "Análise IA" in props and props["Análise IA"].get("rich_text"):
            al = props["Análise IA"]["rich_text"]
            if al:
                analysis_text = al[0].get("text", {}).get("content", "")

        # Check if this is an active candidacy with 0.0% score or corrupted rejection analysis
        is_active_candidacy = estado in ["Candidatado", "Entrevista", "Oferta", "Rejeitado Empresa"]
        is_zeroed_or_rejected = (current_score == 0.0 or "❌" in analysis_text)

        if is_active_candidacy and is_zeroed_or_rejected:
            logger.info(f"🔄 Restoring candidacy: '{title}' @ '{company}' (Status: {estado})")

            # Try to recover original score if mentioned in text
            score_match = re.search(r"(\d{2}(?:\.\d+)?)%", analysis_text)
            restored_score = 75.0
            if score_match:
                try:
                    val = float(score_match.group(1))
                    if 50.0 <= val <= 100.0:
                        restored_score = val
                except ValueError:
                    pass

            restored_analysis = f"✅ Candidatura Ativa ({restored_score}%): Vaga selecionada e candidatada para perfil Júnior em IA / Dados."

            patch_props = {}
            if "Match Score (%)" in schema:
                patch_props["Match Score (%)"] = {"number": restored_score}
            if "Senioridade" in schema:
                patch_props["Senioridade"] = {"select": {"name": "Júnior"}}
            if "Análise IA" in schema:
                patch_props["Análise IA"] = {"rich_text": [{"text": {"content": restored_analysis}}]}

            success = safe_notion_patch(page_id, patch_props, headers)
            if success:
                restored_count += 1
                logger.info(f"  ↳ ✅ Successfully restored to Score {restored_score}%!")
            time.sleep(0.35)

    logger.info("==================================================")
    logger.info(f"🎉 Restoration Complete! Restored {restored_count} active candidacies.")
    logger.info("==================================================")

if __name__ == "__main__":
    run_restore()
