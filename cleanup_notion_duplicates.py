import sys
import io
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

def cleanup_empty_or_duplicate_notion_pages():
    token = config.notion_token
    database_id = config.notion_database_id

    if not token or not database_id:
        print("❌ NOTION_TOKEN or NOTION_DATABASE_ID not configured in .env!")
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
            print(f"❌ Error querying Notion ({resp.status_code}): {resp.text}")
            return

        pages = resp.json().get("results", [])
        print(f"📋 Querying {len(pages)} pages in Notion to clean up duplicates and empty rows...")

        seen_titles = set()
        archived_count = 0

        for page in pages:
            page_id = page.get("id")
            props = page.get("properties", {})
            
            # Extract title and link
            title_text = ""
            link_url = ""

            for p_name, p_data in props.items():
                p_type = p_data.get("type")
                if p_type == "title":
                    title_list = p_data.get("title", [])
                    if title_list:
                        title_text = title_list[0].get("text", {}).get("content", "").strip()
                elif p_type == "url" and p_data.get("url"):
                    link_url = p_data.get("url").strip()

            empresa_prop = props.get("Empresa", {}).get("rich_text", [])
            has_empresa = bool(empresa_prop)

            score_val = props.get("Match Score (%)", {}).get("number")
            analysis_text = props.get("Análise IA", {}).get("rich_text", [{}])[0].get("text", {}).get("content", "").lower() if props.get("Análise IA", {}).get("rich_text") else ""

            # Check if empty row (no title, no link, no score), duplicate title/link, or disqualified role
            unique_key = link_url if link_url else title_text.lower()
            disq_terms = ['2 anos', '3 anos', '4 anos', '5 anos', 'superior a 2', 'superior a 1', 'mais de 2', 'mais de 1-2', 'experiência superior', 'experiencia superior', 'experiência profissional comprovada', 'experiência comprovada', 'experiencia profissional comprovada', 'experiencia comprovada', 'proven experience', 'mid-senior', 'mid senior', 'data annotator', 'video specialist', 'generative ai video', 'editor de vídeo', 'editor de video', 'videógrafo', 'videografo']
            is_disqualified = any(term in title_text.lower() or term in analysis_text for term in disq_terms)

            if not title_text or not link_url or score_val is None or unique_key in seen_titles or "example.com" in link_url or is_disqualified:
                # Archive dummy test / duplicate / incomplete / disqualified row
                archive_url = f"{NOTION_API_URL}/pages/{page_id}"
                p_resp = requests.patch(archive_url, headers=headers, json={"archived": True}, timeout=15)
                if p_resp.status_code == 200:
                    archived_count += 1
                    print(f"  🗑️ Archived test/incomplete/disqualified row: '{title_text or 'Sem Título'}' ({link_url})")

            else:
                if unique_key:
                    seen_titles.add(unique_key)


        print(f"\n🎉 SUCCESS! Cleaned up {archived_count} empty/duplicate rows from Notion!")

    except Exception as e:
        print(f"❌ Error during Notion cleanup: {e}")

if __name__ == "__main__":
    cleanup_empty_or_duplicate_notion_pages()
