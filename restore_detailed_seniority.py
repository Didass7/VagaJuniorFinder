import sys
import io
import requests
import logging
from config import config
from scraper import Job
from matcher import JobMatcher
from notion_store import NOTION_API_URL, NOTION_VERSION, NotionStore

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("RestoreDetailedSeniority")

def restore_seniority():
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
        print(f"📋 Found {len(pages)} pages in Notion. Analyzing real detailed seniority for each job...")

        matcher = JobMatcher(config.candidate)
        notion_store = NotionStore()
        updated_count = 0

        for page in pages:
            page_id = page.get("id")
            props = page.get("properties", {})
            
            title_text = ""
            link_url = ""
            company_text = ""
            analysis_text = ""

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
                        company_text = rt[0].get("text", {}).get("content", "").strip()
                elif p_name == "Análise IA" and p_type == "rich_text":
                    rt = p_data.get("rich_text", [])
                    if rt:
                        analysis_text = rt[0].get("text", {}).get("content", "").strip()

            dummy_job = Job(
                title=title_text,
                company=company_text,
                location="Portugal",
                work_mode="Presencial / Híbrido",
                link=link_url or "https://example.com",
                description=f"{title_text} na empresa {company_text}. {analysis_text}",
                source="Portal",
                pub_date="Hoje"
            )

            text_corpus = f"{title_text} {analysis_text}".lower()
            if "iefp" in text_corpus or "ativar.pt" in text_corpus or "ativar pt" in text_corpus:
                real_seniority = "Elegível IEFP / ATIVAR.pt"
            elif "estágio" in text_corpus or "estagio" in text_corpus or "intern" in text_corpus or "trainee" in text_corpus:
                real_seniority = "Estágio / Trainee"
            elif "recém-licenciado" in text_corpus or "recem-licenciado" in text_corpus or "recem licenciado" in text_corpus or "0-1" in text_corpus:
                real_seniority = "Recém-Licenciado (0-1 anos)"
            elif "junior" in title_text.lower() or "júnior" in title_text.lower() or "jr" in title_text.lower():
                real_seniority = "Júnior (0-2 anos)"
            else:
                real_seniority = "Júnior / Entry-Level"

            clean_seniority = notion_store._sanitize_select_name(real_seniority)

            patch_url = f"{NOTION_API_URL}/pages/{page_id}"
            patch_props = {
                "Senioridade": {"select": {"name": clean_seniority}}
            }

            p_resp = requests.patch(patch_url, headers=headers, json={"properties": patch_props}, timeout=15)
            if p_resp.status_code == 200:
                updated_count += 1
                print(f"  🏢 '{title_text[:30]}' -> Senioridade: {clean_seniority}")

        print(f"\n🎉 SUCCESS! Updated detailed seniority labels for {updated_count} Notion pages!")

    except Exception as e:
        print(f"❌ Error restoring detailed seniority: {e}")

if __name__ == "__main__":
    restore_seniority()
