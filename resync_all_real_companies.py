import sys
import io
import re
import json
import requests
import pandas as pd
import logging
from bs4 import BeautifulSoup
from config import config
from notion_store import NOTION_API_URL, NOTION_VERSION

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ResyncRealCompanies")

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

from company_extractor import extract_company_from_link, is_generic_company

def run_resync():
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
        print(f"📋 Found {len(pages)} pages in Notion. Extracting real company names...")

        notion_updates = 0
        updated_companies = {}

        for page in pages:
            page_id = page.get("id")
            props = page.get("properties", {})
            title_text = ""
            link_url = ""
            current_comp = ""

            for p_name, p_data in props.items():
                p_type = p_data.get("type")
                if p_type == "title":
                    t_list = p_data.get("title", [])
                    if t_list:
                        title_text = t_list[0].get("text", {}).get("content", "").strip()
                elif p_name == "Link" and p_type == "url":
                    if p_data.get("url"):
                        link_url = p_data.get("url").strip()
                elif p_name == "Empresa" and p_type == "rich_text":
                    rt = p_data.get("rich_text", [])
                    if rt:
                        current_comp = rt[0].get("text", {}).get("content", "").strip()

            real_comp = extract_company_from_link(link_url, title_text, current_comp)
            updated_companies[link_url] = real_comp
            if title_text:
                updated_companies[title_text.lower()] = real_comp

            created_time = page.get("created_time", "")[:10] or "2026-08-05"

            patch_url = f"{NOTION_API_URL}/pages/{page_id}"
            patch_props = {
                "Empresa": {"rich_text": [{"text": {"content": real_comp[:100]}}]},
                "Data Extração": {"date": {"start": created_time}}
            }
            p_resp = requests.patch(patch_url, headers=headers, json={"properties": patch_props}, timeout=15)
            if p_resp.status_code == 200:
                notion_updates += 1
                print(f"  🏢 '{title_text[:35]}' -> {real_comp}")

        # Update Excel database if available
        try:
            excel_file = "data/jobs_database.xlsx"
            df = pd.read_excel(excel_file)
            emp_cols = [c for c in df.columns if "empresa" in c.lower() or "company" in c.lower()]
            link_cols = [c for c in df.columns if "link" in c.lower() or "url" in c.lower()]
            title_cols = [c for c in df.columns if "tulo" in c.lower() or "title" in c.lower()]

            if emp_cols and link_cols:
                emp_col = emp_cols[0]
                link_col = link_cols[0]
                title_col = title_cols[0] if title_cols else None

                for idx, row in df.iterrows():
                    link = str(row.get(link_col, '')).strip()
                    title = str(row.get(title_col, '')).strip().lower() if title_col else ""
                    if link in updated_companies:
                        df.at[idx, emp_col] = updated_companies[link]
                    elif title in updated_companies:
                        df.at[idx, emp_col] = updated_companies[title]

                df.to_excel(excel_file, index=False)
                print("✅ Updated jobs_database.xlsx with real company names")
        except Exception as e:
            print(f"⚠️ Note on Excel update: {e}")

        print(f"\n🎉 SUCCESS! Updated Notion with real company names for {notion_updates} pages!")

    except Exception as e:
        print(f"❌ Error syncing Notion: {e}")

if __name__ == "__main__":
    run_resync()
