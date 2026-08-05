import sys
import io
import re
import requests
from config import config
from notion_store import NOTION_API_URL, NOTION_VERSION

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

def clean_text(raw_text: str) -> str:
    if not raw_text:
        return ""
    # 1. Strip emojis and whitespace
    text = re.sub(r'[\U00010000-\U0010ffff\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF🤖🤖]', '', raw_text)
    # 2. Strip prefixes like "IA (80%):", "IA (90%):", "IA:", "Resumo IA:"
    text = re.sub(r'^\s*(?:IA\s*\(\d+%\)\s*:?|IA\s*:?|Resumo IA\s*:?)\s*', '', text, flags=re.I)
    return text.strip()

def clean_all_notion_pages():
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
        print(f"📋 Found {len(pages)} pages in Notion. Cleaning 'Análise IA' column...")

        updated_count = 0
        for page in pages:
            page_id = page.get("id")
            props = page.get("properties", {})
            
            title_text = ""
            analysis_text = ""

            for p_name, p_data in props.items():
                p_type = p_data.get("type")
                if p_type == "title":
                    t_list = p_data.get("title", [])
                    if t_list:
                        title_text = t_list[0].get("text", {}).get("content", "").strip()
                elif p_name == "Análise IA" and p_type == "rich_text":
                    rt = p_data.get("rich_text", [])
                    if rt:
                        analysis_text = rt[0].get("text", {}).get("content", "").strip()

            cleaned = clean_text(analysis_text)
            if cleaned != analysis_text:
                patch_url = f"{NOTION_API_URL}/pages/{page_id}"
                patch_props = {
                    "Análise IA": {"rich_text": [{"text": {"content": cleaned[:2000]}}]}
                }
                p_resp = requests.patch(patch_url, headers=headers, json={"properties": patch_props}, timeout=15)
                if p_resp.status_code == 200:
                    updated_count += 1
                    print(f"  🧹 Cleaned '{title_text[:30]}' -> '{cleaned[:60]}...'")

        print(f"\n🎉 SUCCESS! Cleaned 'Análise IA' text for {updated_count} Notion pages!")

    except Exception as e:
        print(f"❌ Error during text cleanup: {e}")

if __name__ == "__main__":
    clean_all_notion_pages()
