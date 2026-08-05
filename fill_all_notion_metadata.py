import sys
import io
import requests
import logging
from config import config
from notion_store import NOTION_API_URL, NOTION_VERSION, NotionStore

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("FillMetadata")

def fill_all_metadata():
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
        print(f"📋 Found {len(pages)} pages in Notion. Backfilling Fonte, Modo, Senioridade & Data Extração...")

        notion_store = NotionStore()
        updated_count = 0

        for page in pages:
            page_id = page.get("id")
            props = page.get("properties", {})
            
            title_text = ""
            link_url = ""
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
                elif p_name == "Análise IA" and p_type == "rich_text":
                    rt = p_data.get("rich_text", [])
                    if rt:
                        analysis_text = rt[0].get("text", {}).get("content", "").strip()

            text_corpus = f"{title_text} {link_url} {analysis_text}".lower()

            # 1. Infer Fonte
            if "linkedin.com" in link_url.lower():
                fonte = "LinkedIn"
            elif "itjobs.pt" in link_url.lower():
                fonte = "ITJobs.pt"
            elif "net-empregos.com" in link_url.lower():
                fonte = "Net-Empregos"
            elif "teamlyzer.com" in link_url.lower():
                fonte = "Teamlyzer"
            elif "cargadetrabalhos.pt" in link_url.lower():
                fonte = "Carga de Trabalhos"
            elif "landing.jobs" in link_url.lower():
                fonte = "Landing.jobs"
            elif "remotive.com" in link_url.lower():
                fonte = "Remotive"
            elif "arbeitnow.com" in link_url.lower():
                fonte = "Arbeitnow"
            elif "weworkremotely.com" in link_url.lower():
                fonte = "WeWorkRemotely"
            elif "remoteok.com" in link_url.lower():
                fonte = "RemoteOK"
            elif "jobicy.com" in link_url.lower():
                fonte = "Jobicy"
            elif "himalayas.app" in link_url.lower():
                fonte = "Himalayas"
            else:
                fonte = "Portal"

            # 2. Infer Modo
            if any(term in text_corpus for term in ["remoto", "remote", "teletrabalho", "anywhere"]):
                modo = "Remoto"
            elif any(term in text_corpus for term in ["híbrido", "hibrido", "hybrid"]):
                modo = "Híbrido"
            elif any(term in text_corpus for term in ["onsite", "on-site", "presencial"]):
                modo = "Presencial"
            else:
                modo = "Presencial / Híbrido"

            # 3. Infer Senioridade
            if any(term in text_corpus for term in ["iefp", "ativar.pt", "ativar pt", "estágio", "estagio", "intern", "trainee"]):
                senioridade = "Estágio / IEFP"
            elif any(term in text_corpus for term in ["mid", "sénior", "senior", "lead", "lider"]):
                senioridade = "Mid / Sénior"
            else:
                senioridade = "Júnior"

            # 4. Data Extração
            created_date = page.get("created_time", "")[:10] or "2026-08-05"

            patch_url = f"{NOTION_API_URL}/pages/{page_id}"
            patch_props = {
                "Fonte": {"select": {"name": notion_store._sanitize_select_name(fonte)}},
                "Modo": {"select": {"name": notion_store._sanitize_select_name(modo)}},
                "Senioridade": {"select": {"name": notion_store._sanitize_select_name(senioridade)}},
                "Data Extração": {"date": {"start": created_date}}
            }

            p_resp = requests.patch(patch_url, headers=headers, json={"properties": patch_props}, timeout=15)
            if p_resp.status_code == 200:
                updated_count += 1
                print(f"  ✅ Updated '{title_text[:30]}' -> Fonte: {fonte} | Modo: {modo} | Senioridade: {senioridade}")
            else:
                print(f"  ❌ Error for '{title_text[:30]}' ({p_resp.status_code}): {p_resp.text}")

        print(f"\n🎉 SUCCESS! Backfilled Fonte, Modo, Senioridade & Data Extração for {updated_count} Notion pages!")

    except Exception as e:
        print(f"❌ Error during backfill: {e}")

if __name__ == "__main__":
    fill_all_metadata()
