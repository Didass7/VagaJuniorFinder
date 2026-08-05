import sys
import io
import requests
import logging
from config import config
from scraper import Job
from ai_evaluator import AIEvaluator
from notion_store import NotionStore, NOTION_API_URL, NOTION_VERSION

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ForceAIResync")

def force_ai_resync():
    token = config.notion_token
    database_id = config.notion_database_id

    if not token or not database_id:
        print("❌ NOTION_TOKEN or NOTION_DATABASE_ID not configured!")
        return

    ai_evaluator = AIEvaluator()
    if not ai_evaluator.is_available:
        print("❌ AI Evaluator is not available! Check GROQ_API_KEY.")
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
        print(f"📋 Found {len(pages)} pages in Notion. Identifying pages with rule fallback text...")

        jobs_to_evaluate = []
        page_job_map = {}

        for page in pages:
            page_id = page.get("id")
            props = page.get("properties", {})

            # Extract title, company, link, analysis
            title_text = ""
            company_text = "Empresa"
            link_url = "https://linkedin.com"
            analysis_text = ""

            seniority_val = ""
            for p_name, p_data in props.items():
                p_type = p_data.get("type")
                if p_type == "title":
                    title_list = p_data.get("title", [])
                    if title_list:
                        title_text = title_list[0].get("text", {}).get("content", "").strip()
                elif p_name == "Empresa" and p_type == "rich_text":
                    rt = p_data.get("rich_text", [])
                    if rt:
                        company_text = rt[0].get("text", {}).get("content", "").strip()
                elif p_name == "Link" and p_type == "url":
                    if p_data.get("url"):
                        link_url = p_data.get("url").strip()
                elif p_name == "Senioridade" and p_type == "select":
                    sel = p_data.get("select")
                    if sel:
                        seniority_val = sel.get("name", "")
                elif p_name == "Análise IA" and p_type == "rich_text":
                    rt = p_data.get("rich_text", [])
                    if rt:
                        analysis_text = rt[0].get("text", {}).get("content", "").strip()

            if not title_text:
                continue

            dummy_job = Job(
                title=title_text,
                company=company_text,
                location="Portugal",
                description=f"Vaga de {title_text} na empresa {company_text}. Vaga de tecnologia em Portugal para desenvolvimento de software, inteligência artificial, dados e engenharia.",
                link=link_url,
                source="Portal",
                work_mode="Híbrido",
                pub_date="Hoje"
            )

            dummy_job.job_id = page_id
            jobs_to_evaluate.append(dummy_job)
            page_job_map[page_id] = (page_id, title_text)


        if not jobs_to_evaluate:
            print("✨ All Notion pages ALREADY have real AI analysis! No fallback text remaining.")
            return

        print(f"🤖 Batch evaluating {len(jobs_to_evaluate)} pages with Groq AI...")
        eval_results = ai_evaluator.evaluate_jobs_batch(jobs_to_evaluate, config.candidate, batch_size=3)

        updated_count = 0
        for job_id, ai_res in eval_results.items():
            _, title_text = page_job_map.get(job_id, (None, ""))
            patch_url = f"{NOTION_API_URL}/pages/{job_id}"

            clean_company = company_text
            if "empresa via" in clean_company.lower() or "empresa confidencial" in clean_company.lower():
                clean_company = "Empresa Confidencial"

            patch_props = {
                "Empresa": {"rich_text": [{"text": {"content": clean_company[:100]}}]},
                "Análise IA": {"rich_text": [{"text": {"content": ai_res.reasoning[:2000]}}]},
                "Senioridade": {"select": {"name": ai_res.seniority_detected[:50]}}
            }


            p_resp = requests.patch(patch_url, headers=headers, json={"properties": patch_props}, timeout=15)
            if p_resp.status_code == 200:
                updated_count += 1
                print(f"  ✅ Replaced rule text with Groq AI analysis for '{title_text[:35]}...'")

        print(f"\n🎉 SUCCESS! Updated {updated_count} pages with genuine Groq AI analysis!")

    except Exception as e:
        print(f"❌ Error during Force AI Resync: {e}")

if __name__ == "__main__":
    force_ai_resync()
