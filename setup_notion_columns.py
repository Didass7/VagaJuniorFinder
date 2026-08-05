import sys
import io
import requests
import logging
from config import config

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("NotionSetup")

NOTION_API_URL = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"

def setup_notion_database_columns():
    token = config.notion_token
    database_id = config.notion_database_id

    if not token or not database_id:
        print("❌ NOTION_TOKEN or NOTION_DATABASE_ID not configured in .env!")
        return

    url = f"{NOTION_API_URL}/databases/{database_id}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json"
    }

    properties_to_create = {
        "Empresa": {
            "rich_text": {}
        },
        "Match Score (%)": {
            "number": {
                "format": "number"
            }
        },
        "Senioridade": {
            "select": {}
        },
        "Link": {
            "url": {}
        },
        "Modo": {
            "select": {}
        },
        "Fonte": {
            "select": {}
        },
        "Elegível IEFP": {
            "checkbox": {}
        },
        "Estado": {
            "select": {}
        },

        "Data Extração": {
            "date": {}
        },
        "Análise IA": {
            "rich_text": {}
        }
    }

    payload = {
        "properties": properties_to_create
    }

    print(f"⚙️ Updating Notion Database schema for ID: {database_id[:8]}...")
    try:
        resp = requests.patch(url, headers=headers, json=payload, timeout=15)
        if resp.status_code == 200:
            print("🎉 SUCCESS! Created all database columns in Notion automatically:")
            for col in properties_to_create.keys():
                print(f"  ✅ {col}")
        else:
            print(f"⚠️ Notion API response ({resp.status_code}): {resp.text}")
    except Exception as e:
        print(f"❌ Error updating Notion Database schema: {e}")

if __name__ == "__main__":
    setup_notion_database_columns()
