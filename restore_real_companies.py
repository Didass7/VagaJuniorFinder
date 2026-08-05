import sys
import io
import requests
import pandas as pd
import logging
from config import config
from notion_store import NOTION_API_URL, NOTION_VERSION

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("RestoreCompanies")

def restore_companies():
    token = config.notion_token
    database_id = config.notion_database_id

    if not token or not database_id:
        print("❌ NOTION_TOKEN or NOTION_DATABASE_ID not configured!")
        return

    # Load master jobs Excel database
    company_map = {}
    try:
        df = pd.read_excel('data/jobs_database.xlsx')
        title_col = [c for c in df.columns if "tulo" in c.lower() or "title" in c.lower()][0]
        link_col = [c for c in df.columns if "link" in c.lower() or "url" in c.lower()][0]
        empresa_col = [c for c in df.columns if "empresa" in c.lower() or "company" in c.lower()][0]

        for _, row in df.iterrows():
            title = str(row.get(title_col, '')).strip().lower()
            comp = str(row.get(empresa_col, '')).strip()
            link = str(row.get(link_col, '')).strip()

            if "empresa via" in comp.lower():
                comp = "Empresa Confidencial"

            if title and comp:
                company_map[title] = comp
            if link and comp:
                company_map[link] = comp

        print(f"📊 Loaded {len(company_map)} real company mappings from Excel database.")

    except Exception as e:
        print(f"❌ Error loading Excel database: {e}")

    url_query = f"{NOTION_API_URL}/databases/{database_id}/query"
    headers = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json"
    }

    try:
        resp = requests.post(url_query, headers=headers, json={"page_size": 100}, timeout=15)
        if resp.status_code != 200:
            print(f"❌ Error querying Notion ({resp.status_code}): {resp.text}")
            return

        pages = resp.json().get("results", [])
        print(f"📋 Querying {len(pages)} pages in Notion to restore real company names...")

        updated_count = 0
        for page in pages:
            page_id = page.get("id")
            props = page.get("properties", {})

            title_text = ""
            link_url = ""

            for p_name, p_data in props.items():
                p_type = p_data.get("type")
                if p_type == "title":
                    title_list = p_data.get("title", [])
                    if title_list:
                        title_text = title_list[0].get("text", {}).get("content", "").strip()
                elif p_name == "Link" and p_type == "url":
                    if p_data.get("url"):
                        link_url = p_data.get("url").strip()

            if not title_text:
                continue

            # Lookup real company name from Excel
            real_company = company_map.get(link_url) or company_map.get(title_text.lower(), "Empresa Confidencial")

            patch_url = f"{NOTION_API_URL}/pages/{page_id}"
            patch_props = {
                "Empresa": {"rich_text": [{"text": {"content": real_company[:100]}}]}
            }

            p_resp = requests.patch(patch_url, headers=headers, json={"properties": patch_props}, timeout=15)
            if p_resp.status_code == 200:
                updated_count += 1
                print(f"  🏢 Restored company for '{title_text[:35]}...' -> {real_company}")

        print(f"\n🎉 SUCCESS! Restored company names for {updated_count} Notion pages!")

    except Exception as e:
        print(f"❌ Error during company restore: {e}")

if __name__ == "__main__":
    restore_companies()
