import logging
import time
import datetime
import requests
from typing import List, Set, Optional, Dict, Any
from config import config
from matcher import ScoredJob
from company_extractor import extract_company_from_link

logger = logging.getLogger("NotionStore")

NOTION_API_URL = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"

class NotionStore:
    """Manages job storage and candidacy tracking inside a Notion Database via Notion API."""

    def __init__(self, token: Optional[str] = None, database_id: Optional[str] = None):
        self.token = token if token is not None else config.notion_token
        self.database_id = database_id if database_id is not None else config.notion_database_id

        
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json"
        }
        self._db_schema: Optional[Dict[str, Any]] = None

    @property
    def is_configured(self) -> bool:
        return bool(self.token) and bool(self.database_id)

    def get_database_schema(self) -> Dict[str, Any]:
        """Fetches the Database schema from Notion API to inspect existing column names and types."""
        if not self.is_configured:
            return {}
        if self._db_schema is not None and len(self._db_schema) > 0:
            return self._db_schema

        url = f"{NOTION_API_URL}/databases/{self.database_id}"
        max_retries = 3
        for attempt in range(1, max_retries + 1):
            try:
                resp = requests.get(url, headers=self.headers, timeout=15)
                if resp.status_code == 200:
                    self._db_schema = resp.json().get("properties", {})
                    return self._db_schema
                else:
                    logger.warning(f"⚠️ Could not fetch Notion database schema ({resp.status_code}): {resp.text}")
            except Exception as e:
                if attempt < max_retries:
                    logger.warning(f"⚠️ Connection error fetching Notion schema (attempt {attempt}/{max_retries}): {e}. Retrying in {attempt * 2}s...")
                    time.sleep(attempt * 2)
                else:
                    logger.error(f"Exception fetching Notion database schema: {e}")
        
        return {}

    def get_existing_urls(self) -> Set[str]:
        """Queries the Notion Database to retrieve URLs of already synced jobs."""
        if not self.is_configured:
            return set()

        url = f"{NOTION_API_URL}/databases/{self.database_id}/query"
        existing_urls: Set[str] = set()
        
        has_more = True
        start_cursor = None

        while has_more:
            payload: Dict[str, Any] = {"page_size": 100}
            if start_cursor:
                payload["start_cursor"] = start_cursor

            success = False
            for attempt in range(1, 4):
                try:
                    resp = requests.post(url, headers=self.headers, json=payload, timeout=15)
                    if resp.status_code != 200:
                        logger.warning(f"⚠️ Notion API query returned status {resp.status_code}: {resp.text}")
                        break

                    data = resp.json()
                    results = data.get("results", [])
                    
                    for page in results:
                        props = page.get("properties", {})
                        # Check any property of type "url"
                        for prop_data in props.values():
                            if prop_data.get("type") == "url" and prop_data.get("url"):
                                existing_urls.add(prop_data.get("url"))

                    has_more = data.get("has_more", False)
                    start_cursor = data.get("next_cursor")
                    success = True
                    break
                except Exception as e:
                    if attempt < 3:
                        time.sleep(attempt * 2)
                    else:
                        logger.error(f"Error querying Notion Database: {e}")

            if not success:
                break

        return existing_urls

    def sync_jobs(self, scored_jobs: List[ScoredJob]) -> int:
        """Syncs new scored jobs to Notion Database. Returns count of newly created Notion pages."""
        if not self.is_configured:
            logger.info("ℹ️ Notion token or database ID not configured. Skipping Notion sync.")
            return 0

        existing_urls = self.get_existing_urls()
        synced_count = 0

        for sj in scored_jobs:
            if sj.score < 55.0:
                continue

            job = sj.job
            if job.link in existing_urls:
                continue

            try:
                success = self._create_job_page(sj)
                if success:
                    synced_count += 1
                    existing_urls.add(job.link)
                time.sleep(0.35)  # Throttling to stay safely below Notion 3 req/sec rate limit
            except Exception as e:
                logger.error(f"Error syncing job '{job.title}' to Notion: {e}")

        if synced_count > 0:
            logger.info(f"✅ Notion Store: Successfully synced {synced_count} new jobs to Notion Database!")
        else:
            logger.info("ℹ️ Notion Store: All qualified jobs are already present in Notion Database.")

        return synced_count

    @staticmethod
    def _truncate_text(text: str, max_length: int = 1990) -> str:
        """Safely truncates text strings to prevent Notion API rich_text 2000 character validation failures."""
        if not text:
            return ""
        if len(text) > max_length:
            return text[:max_length - 3] + "..."
        return text

    def _create_job_page(self, sj: ScoredJob) -> bool:
        """Creates a new Notion page row in the database matching existing database properties dynamically."""
        job = sj.job
        url = f"{NOTION_API_URL}/pages"
        schema = self.get_database_schema()

        # Find title column in Notion schema
        title_prop_name = "Name"
        for name, prop in schema.items():
            if prop.get("type") == "title":
                title_prop_name = name
                break

        properties: Dict[str, Any] = {
            title_prop_name: {
                "title": [
                    {
                        "text": {
                            "content": self._truncate_text(job.title, 200)
                        }
                    }
                ]
            }
        }

        company_name = extract_company_from_link(job.link, job.title, job.company)

        # Map properties dynamically if present in user's database schema
        raw_reason_text = (sj.ai_reasoning if sj.ai_evaluated else sj.match_reason) or ""
        # Normalize values to match exact Notion schema options
        modo_clean = "Remoto" if "remoto" in job.work_mode.lower() else "Presencial / Híbrido"
        seniority_clean = "Recém-licenciado" if any(t in sj.seniority_status.lower() for t in ["recém", "recem", "0-1", "estágio", "estagio", "iefp", "ativar"]) else "Júnior"
        fonte_clean = self._sanitize_select_name(job.source)

        field_mappings = [
            ("Empresa", ["Empresa", "Company"], "rich_text", [{"text": {"content": self._truncate_text(company_name, 100)}}]),
            ("Match Score (%)", ["Match Score (%)", "Score (%)", "Match", "Score"], "number", float(round(sj.score, 1))),
            ("Senioridade", ["Senioridade", "Seniority", "Nível"], "select", {"name": seniority_clean}),
            ("Link", ["Link", "URL", "Link de Candidatura"], "url", job.link),
            ("Modo", ["Modo", "Modo de Trabalho", "Work Mode"], "select", {"name": modo_clean}),
            ("Fonte", ["Fonte", "Source"], "select", {"name": fonte_clean}),
            ("Elegível IEFP", ["Elegível IEFP", "IEFP"], "checkbox", bool(job.iefp_mentioned)),
            ("Estado", ["Estado", "Status"], "select", {"name": "Por Candidatar"}),
            ("Estado", ["Estado", "Status"], "status", {"name": "Por Candidatar"}),
            ("Data Extração", ["Data Extração", "Data de Extração", "Data Ingestão", "Data/Hora", "Date"], "date", {"start": getattr(job, 'fetched_at', None) if getattr(job, 'fetched_at', None) else datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")}),
            ("Análise IA", ["Análise IA", "Análise da IA", "AI Reasoning", "Notas"], "rich_text", [{"text": {"content": self._truncate_text(raw_reason_text, 1990)}}]),
        ]

        for canonical_name, aliases, p_type, value in field_mappings:
            target_name = None
            for alias in aliases:
                if alias in schema and schema[alias].get("type") == p_type:
                    target_name = alias
                    break
            
            if target_name:
                if p_type == "rich_text":
                    properties[target_name] = {"rich_text": value}
                elif p_type == "number":
                    properties[target_name] = {"number": value}
                elif p_type == "select":
                    properties[target_name] = {"select": value}
                elif p_type == "url":
                    properties[target_name] = {"url": value}
                elif p_type == "checkbox":
                    properties[target_name] = {"checkbox": value}
                elif p_type == "date":
                    properties[target_name] = {"date": value}
                elif p_type == "status":
                    try:
                        properties[target_name] = {"status": value}
                    except Exception:
                        pass


        # Children page content blocks (ensures all job info & AI breakdown is accessible inside the page)
        reason_text = sj.ai_reasoning if sj.ai_evaluated else sj.match_reason
        children = [
            {
                "object": "block",
                "type": "heading_2",
                "heading_2": {
                    "rich_text": [{"type": "text", "text": {"content": "🤖 Análise da IA & Detalhes da Vaga"}}]
                }
            },
            {
                "object": "block",
                "type": "callout",
                "callout": {
                    "rich_text": [{"type": "text", "text": {"content": f"Match Score: {sj.score}% | {sj.seniority_status} | {job.work_mode}"}}],
                    "icon": {"emoji": "🎯"}
                }
            },
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [
                        {"type": "text", "text": {"content": "Empresa: "}, "annotations": {"bold": True}},
                        {"type": "text", "text": {"content": f"{job.company}\n"}},
                        {"type": "text", "text": {"content": "Localização: "}, "annotations": {"bold": True}},
                        {"type": "text", "text": {"content": f"{job.location}\n"}},
                        {"type": "text", "text": {"content": "Fonte: "}, "annotations": {"bold": True}},
                        {"type": "text", "text": {"content": f"{job.source}"}}
                    ]
                }
            }

        ]

        if reason_text:
            children.append({
                "object": "block",
                "type": "quote",
                "quote": {
                    "rich_text": [{"type": "text", "text": {"content": f"Resumo IA: {reason_text}"}}]
                }
            })

        children.append({
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [
                    {"type": "text", "text": {"content": "👉 Candidatar: "}},
                    {"type": "text", "text": {"content": job.link, "link": {"url": job.link}}}
                ]
            }
        })

        payload = {
            "parent": {
                "database_id": self.database_id
            },
            "properties": properties,
            "children": children
        }

        max_retries = 3
        for attempt in range(1, max_retries + 1):
            try:
                resp = requests.post(url, headers=self.headers, json=payload, timeout=15)
                if resp.status_code in [200, 201]:
                    return True
                else:
                    logger.error(f"❌ Failed to create Notion page for '{job.title}' ({resp.status_code}): {resp.text}")
                    return False
            except Exception as e:
                if attempt < max_retries:
                    logger.warning(f"⚠️ Connection error creating Notion page for '{job.title}' (attempt {attempt}/{max_retries}): {e}. Retrying in {attempt * 2}s...")
                    time.sleep(attempt * 2)
                else:
                    logger.error(f"Exception creating Notion page for '{job.title}': {e}")
                    return False

        return False

    def _sanitize_select_name(self, name: str) -> str:
        """Sanitizes select option strings for Notion API (replaces commas and trims length)."""
        if not name:
            return "N/A"
        clean = name.replace(",", " - ").strip()
        while "  " in clean:
            clean = clean.replace("  ", " ")
        return clean[:100] if clean else "N/A"
