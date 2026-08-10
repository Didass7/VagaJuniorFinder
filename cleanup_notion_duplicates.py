import sys
import io
import re
import string
import requests
import logging
from config import config
from notion_store import NOTION_API_URL, NOTION_VERSION

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("NotionCleanup")

def cleanup_database(database_id: str, is_rafael: bool = False):
    token = config.notion_token
    if not token or not database_id:
        return

    url_query = f"{NOTION_API_URL}/databases/{database_id}/query"
    headers = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json"
    }

    try:
        pages = []
        has_more = True
        start_cursor = None

        while has_more:
            payload = {"page_size": 100}
            if start_cursor:
                payload["start_cursor"] = start_cursor
            resp = requests.post(url_query, headers=headers, json=payload, timeout=15)
            if resp.status_code != 200:
                print(f"❌ Error querying Notion ({resp.status_code}): {resp.text}")
                break
            res_data = resp.json()
            pages.extend(res_data.get("results", []))
            has_more = res_data.get("has_more", False)
            start_cursor = res_data.get("next_cursor")

        target_name = "Rafael" if is_rafael else "Diogo"
        print(f"📋 Querying {len(pages)} total pages in Notion ({target_name}'s database) to clean up...")

        seen_titles = set()
        archived_count = 0

        for page in pages:
            page_id = page.get("id")
            props = page.get("properties", {})
            
            title_prop = props.get("Título da Vaga", {}).get("title", [])
            title_text = title_prop[0].get("text", {}).get("content", "").strip() if title_prop else ""
            
            empresa_prop = props.get("Empresa", {}).get("rich_text", [])
            empresa_text = empresa_prop[0].get("text", {}).get("content", "").strip() if empresa_prop else ""

            link_prop = props.get("Link", {}).get("url")
            link_url = link_prop.strip() if link_prop else ""

            def _clean(s: str) -> str:
                if not s: return ""
                s_clean = re.sub(r"\b(remote|remoto|teletrabalho|híbrido|hibrido|hybrid|presencial|lisboa|lisbon|portugal|modelo)\b.*$", "", s, flags=re.IGNORECASE)
                return " ".join(s_clean.lower().translate(str.maketrans('', '', string.punctuation)).split())

            title_key = _clean(title_text)
            comp_key = _clean(empresa_text)
            unique_key = f"{title_key}_{comp_key}" if title_key else link_url

            score_val = props.get("Match Score (%)", {}).get("number")
            analysis_prop = props.get("Análise IA", {}).get("rich_text", [])
            analysis_text = analysis_prop[0].get("text", {}).get("content", "").lower() if analysis_prop else ""

            disq_terms = [
                '2 anos', '3 anos', '4 anos', '5 anos', '6 anos', '7 anos', '7+', '6+', '5+', '4+', '3+', '2+',
                '2 years', '3 years', '4 years', '5 years', 'at least 3', 'at least 2', '2 to 5', '2 a 5', '2 a 3', '2-5',
                'superior a 2', 'superior a 1', 'mais de 2', 'mais de 1-2', 'experiência superior', 'experiencia superior',
                'experiência profissional comprovada', 'experiência comprovada', 'experiencia profissional comprovada', 'experiencia comprovada',
                'proven experience', 'mid-senior', 'mid senior', 'senior', 'sénior', 'backend developer',
                'data annotator', 'video specialist', 'generative ai video', 'editor de vídeo', 'editor de video', 'videógrafo', 'videografo'
            ]
            
            is_disqualified = any(term in title_text.lower() or term in analysis_text for term in disq_terms) or ("081f8b24fdc9370c" in link_url) or ("a97995c0ea22a779" in link_url)
            
            if is_rafael:
                # Disqualify Data Science / Data Engineering jobs for Rafael
                rafael_alien_terms = ["data engineer", "data scientist", "cientista de dados", "bi analyst", "analista de bi"]
                if any(term in title_text.lower() for term in rafael_alien_terms):
                    is_disqualified = True

            status_prop = props.get("Status", {}).get("select", {}) or props.get("Status", {}).get("status", {})
            status_val = status_prop.get("name", "").strip() if status_prop else ""

            # ABSOLUTE SAFETY RULE: NEVER TOUCH OR ARCHIVE JOBS THE USER HAS ALREADY APPLIED TO OR SAVED!
            if status_val and status_val.lower() != "por candidatar":
                if unique_key:
                    seen_titles.add(unique_key)
                continue

            if not title_text or not link_url or score_val is None or unique_key in seen_titles or "example.com" in link_url or is_disqualified:
                archive_url = f"{NOTION_API_URL}/pages/{page_id}"
                p_resp = requests.patch(archive_url, headers=headers, json={"archived": True}, timeout=15)
                if p_resp.status_code == 200:
                    archived_count += 1
                    print(f"  🗑️ Archived row: '{title_text or 'Sem Título'}' @ '{empresa_text}' ({link_url})")

            else:
                if unique_key:
                    seen_titles.add(unique_key)

        print(f"🎉 Cleaned up {archived_count} rows from {target_name}'s Notion database!\n")

    except Exception as e:
        print(f"❌ Error during Notion cleanup for {database_id}: {e}")

def cleanup_empty_or_duplicate_notion_pages():
    # Clean Diogo database
    if config.notion_database_id:
        cleanup_database(config.notion_database_id, is_rafael=False)
    # Clean Rafael database
    rafael_db_id = "3b54e649adbe80e2b707db08342758c4"
    cleanup_database(rafael_db_id, is_rafael=True)

if __name__ == "__main__":
    cleanup_empty_or_duplicate_notion_pages()
