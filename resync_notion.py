import sys
import io
import requests
import logging
from config import config
from scraper import JobIngestionPipeline
from matcher import JobMatcher, ScoredJob
from notion_store import NotionStore, NOTION_API_URL, NOTION_VERSION
from company_extractor import extract_company_from_link

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("NotionResync")

def resync_all_notion_pages():
    token = config.notion_token
    database_id = config.notion_database_id

    if not token or not database_id:
        print("❌ NOTION_TOKEN or NOTION_DATABASE_ID not configured in .env!")
        return

    # 1. Ingest & evaluate jobs
    print("🔍 Fetching and evaluating current pipeline jobs...")
    pipeline = JobIngestionPipeline(itjobs_api_key=config.itjobs_api_key)
    raw_jobs = pipeline.run()
    
    matcher = JobMatcher(config.candidate)
    scored_jobs = matcher.process_jobs(raw_jobs)
    
    # Map job by title / link for quick lookup
    job_map = {sj.job.title.strip().lower(): sj for sj in scored_jobs}
    link_map = {sj.job.link.strip(): sj for sj in scored_jobs}

    # 2. Query all existing pages in Notion Database
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
        print(f"📋 Found {len(pages)} existing pages in Notion. Updating columns...")

        updated_count = 0
        notion_store = NotionStore()
        schema = notion_store.get_database_schema()

        for page in pages:
            page_id = page.get("id")
            props = page.get("properties", {})
            
            # Extract title
            title_text = ""
            for p_name, p_data in props.items():
                if p_data.get("type") == "title":
                    title_list = p_data.get("title", [])
                    if title_list:
                        title_text = title_list[0].get("text", {}).get("content", "")
                    break

            if not title_text:
                continue

            # Find matching scored job
            matched_sj = job_map.get(title_text.strip().lower())
            if not matched_sj:
                # Try finding by link
                for p_name, p_data in props.items():
                    if p_data.get("type") == "url" and p_data.get("url"):
                        matched_sj = link_map.get(p_data.get("url").strip())
                        if matched_sj:
                            break

            if matched_sj:
                job = matched_sj.job
                patch_url = f"{NOTION_API_URL}/pages/{page_id}"
                
                reason_text = matched_sj.ai_reasoning if matched_sj.ai_evaluated else matched_sj.match_reason

                company_name = extract_company_from_link(job.link, job.title, job.company)
                patch_props = {
                    "Empresa": {"rich_text": [{"text": {"content": company_name[:100]}}]},
                    "Match Score (%)": {"number": float(round(matched_sj.score, 1))},
                    "Senioridade": {"select": {"name": notion_store._sanitize_select_name(matched_sj.seniority_status)}},
                    "Link": {"url": job.link},
                    "Modo": {"select": {"name": notion_store._sanitize_select_name(job.work_mode)}},
                    "Fonte": {"select": {"name": notion_store._sanitize_select_name(job.source)}},
                    "Elegível IEFP": {"checkbox": bool(job.iefp_mentioned)},
                    "Análise IA": {"rich_text": [{"text": {"content": reason_text[:2000]}}]}
                }

                # Filter patch_props to only keep columns that exist in schema
                valid_patch_props = {}
                for k, v in patch_props.items():
                    if k in schema:
                        valid_patch_props[k] = v

                p_resp = requests.patch(patch_url, headers=headers, json={"properties": valid_patch_props}, timeout=15)
                if p_resp.status_code == 200:
                    updated_count += 1
                    print(f"  ✅ Backfilled columns for '{job.title[:35]}...'")

        print(f"\n🎉 SUCCESS! Backfilled columns for {updated_count} Notion pages!")

    except Exception as e:
        print(f"❌ Error during Notion backfill: {e}")

if __name__ == "__main__":
    resync_all_notion_pages()
