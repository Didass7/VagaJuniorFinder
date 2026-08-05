import sys
import io
import requests
import datetime
from config import config
from scraper import Job
from matcher import JobMatcher
from notion_store import NOTION_API_URL, NOTION_VERSION, NotionStore

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

def resync_all_notion_metadata():
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

    resp = requests.post(url_query, headers=headers, json={"page_size": 100}, timeout=15)
    if resp.status_code != 200:
        print(f"❌ Error querying Notion ({resp.status_code})")
        return

    pages = resp.json().get("results", [])
    print(f"📋 Resyncing AI Analysis, Seniority, and Extraction Datetime for {len(pages)} Notion pages...")

    matcher = JobMatcher(config.candidate)
    notion_store = NotionStore()

    jobs_to_eval = []
    page_map = {}

    for p in pages:
        pid = p["id"]
        props = p.get("properties", {})
        
        title_text = ""
        link_url = ""
        company_text = ""
        source_text = "Portal"

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
            elif p_name == "Fonte" and p_type == "select":
                s = p_data.get("select")
                if s:
                    source_text = s.get("name")

        job = Job(
            title=title_text,
            company=company_text,
            location="Portugal",
            work_mode="Presencial / Híbrido",
            link=link_url or "https://example.com",
            description=f"Vaga de {title_text} na empresa {company_text}.",
            source=source_text,
            pub_date="Hoje"
        )
        jobs_to_eval.append(job)
        page_map[job.job_id] = (pid, title_text, job)

    updated_count = 0
    now_iso = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

    for p in pages:
        pid = p["id"]
        props = p.get("properties", {})
        
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

        text_corpus = f"{title_text} {analysis_text}".lower()
        
        # Determine exact seniority
        if "iefp" in text_corpus or "ativar.pt" in text_corpus or "ativar pt" in text_corpus:
            seniority = "Elegível IEFP / ATIVAR.pt"
        elif "estágio" in text_corpus or "estagio" in text_corpus or "intern" in text_corpus or "trainee" in text_corpus:
            seniority = "Estágio / Trainee"
        elif "recém-licenciado" in text_corpus or "recem-licenciado" in text_corpus or "0-1" in text_corpus:
            seniority = "Recém-Licenciado (0-1 anos)"
        elif "junior" in title_text.lower() or "júnior" in title_text.lower() or "jr" in title_text.lower():
            seniority = "Júnior (0-2 anos)"
        else:
            seniority = "Júnior / Entry-Level"

        clean_seniority = notion_store._sanitize_select_name(seniority)
        
        if not analysis_text:
            analysis_text = f"Vaga de {title_text} adequada para desenvolvimento e análise em Tecnologia/IA"

        patch_url = f"{NOTION_API_URL}/pages/{pid}"
        patch_props = {
            "Senioridade": {"select": {"name": clean_seniority}},
            "Análise IA": {"rich_text": [{"text": {"content": analysis_text}}]},
            "Data Extração": {"date": {"start": now_iso}}
        }

        p_resp = requests.patch(patch_url, headers=headers, json={"properties": patch_props}, timeout=15)
        if p_resp.status_code == 200:
            updated_count += 1
            print(f"  ✅ '{title_text[:30]}' -> Senioridade: {clean_seniority} | Data Extração: {now_iso}")

    print(f"\n🎉 SUCCESS! Fully updated AI Analysis, Seniority, and Extraction Datetime for {updated_count} Notion pages!")

if __name__ == "__main__":
    resync_all_notion_metadata()
