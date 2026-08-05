import sys
import io
import re
import requests
import logging
from bs4 import BeautifulSoup
from config import config
from notion_store import NOTION_API_URL, NOTION_VERSION, NotionStore

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("RestoreWorkMode")

WEB_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
}

def detect_work_mode(title: str, link: str) -> str:
    title_lower = title.lower()
    link_lower = link.lower()

    # 1. Quick check title and link URL
    if any(t in title_lower or t in link_lower for t in ["remoto", "remote", "teletrabalho", "anywhere", "workweek & remote"]):
        return "Remoto"
    if any(t in title_lower or t in link_lower for t in ["híbrido", "hibrido", "hybrid"]):
        return "Híbrido"
    if any(t in title_lower or t in link_lower for t in ["onsite", "on-site", "presencial"]):
        return "Presencial"

    # 2. Fetch page HTML text if available
    try:
        if link and "example.com" not in link:
            r = requests.get(link, headers=WEB_HEADERS, timeout=6)
            if r.status_code == 200:
                soup = BeautifulSoup(r.text, 'html.parser')
                body_text = soup.get_text(separator=' ', strip=True).lower()

                # Search body text
                if "híbrido" in body_text or "hibrido" in body_text or "hybrid" in body_text:
                    return "Híbrido"
                elif "remoto" in body_text or "remote" in body_text or "teletrabalho" in body_text:
                    return "Remoto"
                elif "presencial" in body_text or "onsite" in body_text or "on-site" in body_text:
                    return "Presencial"
    except Exception as e:
        logger.debug(f"Could not fetch {link}: {e}")

    # Fallback default if not specified
    return "Híbrido"

def restore_work_modes():
    token = config.notion_token
    database_id = config.notion_database_id

    if not token or not database_id:
        print("❌ NOTION_TOKEN or NOTION_DATABASE_ID missing")
        return

    url_query = f"{NOTION_API_URL}/databases/{database_id}/query"
    headers = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json"
    }

    try:
        resp = requests.post(url_query, headers=headers, json={"page_size": 100}, timeout=15)
        if resp.status_code != 200:
            print(f"❌ Error querying Notion ({resp.status_code})")
            return

        pages = resp.json().get("results", [])
        print(f"📋 Found {len(pages)} pages in Notion. Analyzing real work mode (Remoto, Híbrido, Presencial)...")

        notion_store = NotionStore()
        updated_count = 0

        for page in pages:
            page_id = page.get("id")
            props = page.get("properties", {})
            
            title_text = ""
            link_url = ""

            for p_name, p_data in props.items():
                p_type = p_data.get("type")
                if p_type == "title":
                    t_list = p_data.get("title", [])
                    if t_list:
                        title_text = t_list[0].get("text", {}).get("content", "").strip()
                elif p_name == "Link" and p_type == "url":
                    if p_data.get("url"):
                        link_url = p_data.get("url").strip()

            real_mode = detect_work_mode(title_text, link_url)
            clean_mode = notion_store._sanitize_select_name(real_mode)

            patch_url = f"{NOTION_API_URL}/pages/{page_id}"
            patch_props = {
                "Modo": {"select": {"name": clean_mode}}
            }

            p_resp = requests.patch(patch_url, headers=headers, json={"properties": patch_props}, timeout=15)
            if p_resp.status_code == 200:
                updated_count += 1
                print(f"  🏠 '{title_text[:30]}' -> Modo: {clean_mode}")

        print(f"\n🎉 SUCCESS! Updated work modes (Remoto, Híbrido, Presencial) for {updated_count} Notion pages!")

    except Exception as e:
        print(f"❌ Error restoring work mode: {e}")

if __name__ == "__main__":
    restore_work_modes()
