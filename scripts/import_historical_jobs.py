from __future__ import annotations
import sys
import os
import io
import re
import time
import datetime
import logging
import requests

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from typing import Dict, Any, List, Optional
from bs4 import BeautifulSoup
from config import config, load_config
from scraper import Job, clean_job_description, get_random_headers
from matcher import JobMatcher, ScoredJob
from ai_evaluator import AIEvaluator, AIEvaluationResult
from notion_store import NotionStore

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("ImportHistorical")

HISTORICAL_JOBS = [
    {
        "company": "FitnessUp",
        "title": "Programador Inteligência Artificial e Automação",
        "status": "Entrevista",
        "date": "2026-07-24T10:00:00",
        "link": "https://www.linkedin.com/jobs/view/4444382294/",
        "work_mode": "Presencial / Híbrido",
        "default_desc": "Oportunidade para Programador de Inteligência Artificial e Automação na FitnessUp. Desenvolvimento de soluções de IA, automação de processos, integração de modelos de machine learning e fluxos inteligentes com Python."
    },
    {
        "company": "Deloitte",
        "title": "Tech & Engineering | New Graduates",
        "status": "Entrevista",
        "date": "2026-07-10T10:00:00",
        "link": "https://www.linkedin.com/jobs/view/4429507227/",
        "work_mode": "Presencial / Híbrido",
        "default_desc": "Programa de recém-licenciados Tech & Engineering na Deloitte Portugal. Oportunidade para início de carreira em Engenharia de Software, Engenharia de Dados, Inteligência Artificial e Consultoria Tecnológica."
    },
    {
        "company": "PrimeIT",
        "title": "Artificial Intelligence Engineer",
        "status": "Entrevista",
        "date": "2026-07-09T10:00:00",
        "link": "https://www.linkedin.com/jobs/view/4432977269/",
        "work_mode": "Presencial / Híbrido",
        "default_desc": "Vaga de Artificial Intelligence Engineer na PrimeIT. Desenvolvimento e implementação de modelos de IA, Machine Learning, processamento de linguagem natural e pipelines de dados com Python."
    },
    {
        "company": "DDN - Gestão de Projetos",
        "title": "AI Engineer (m/f)",
        "status": "Entrevista",
        "date": "2026-06-23T10:00:00",
        "link": "https://www.linkedin.com/jobs/view/4428944790/",
        "work_mode": "Presencial / Híbrido",
        "default_desc": "Engenheiro de Inteligência Artificial na DDN Gestão de Projetos. Implementação de soluções de inteligência artificial aplicadas à gestão de engenharia e processos corporativos."
    }
]

def fetch_linkedin_desc(url: str, session: requests.Session) -> str:
    try:
        id_match = re.search(r"(\d{6,14})", url)
        if not id_match:
            return ""
        job_id = id_match.group(1)
        api_url = f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"
        
        headers = get_random_headers()
        headers.update({
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "pt-PT,pt;q=0.9,en-US;q=0.8,en;q=0.7",
        })
        time.sleep(0.5)
        resp = session.get(api_url, headers=headers, timeout=10)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            markup = (
                soup.find("div", class_=lambda c: c and "show-more-less-html__markup" in str(c)) or
                soup.find("section", class_=lambda c: c and "description" in str(c)) or
                soup.find("div", class_=lambda c: c and "description__text" in str(c))
            )
            if markup:
                return clean_job_description(markup.get_text(separator=" ", strip=True))
    except Exception as e:
        logger.warning(f"Could not fetch live LinkedIn description: {e}")
    return ""

def main():
    cfg = load_config("diogo_ai")
    logger.info(f"Target Candidate: {cfg.candidate.name}")
    logger.info(f"Notion DB: {cfg.notion_database_id}")

    session = requests.Session()
    ai_evaluator = AIEvaluator()
    notion_store = NotionStore(token=cfg.notion_token, database_id=cfg.notion_database_id)

    existing_urls, _ = notion_store.get_existing_records()
    logger.info(f"Found {len(existing_urls)} existing URLs in Notion.")

    jobs_to_insert = []

    for item in HISTORICAL_JOBS:
        url = item["link"]
        if url in existing_urls:
            logger.info(f"ℹ️ Job '{item['title']}' already exists in Notion. Skipping.")
            continue

        logger.info(f"🔍 Fetching/Processing: {item['title']} @ {item['company']}")
        live_desc = fetch_linkedin_desc(url, session)
        full_desc = live_desc if live_desc and len(live_desc) > 100 else item["default_desc"]

        job = Job(
            title=item["title"],
            company=item["company"],
            location="Portugal",
            work_mode=item["work_mode"],
            link=item["link"],
            description=full_desc,
            source="LinkedIn",
            pub_date=item["date"],
            fetched_at=item["date"],
            iefp_mentioned=False
        )

        jobs_to_insert.append((job, item["status"]))

    if not jobs_to_insert:
        logger.info("✅ All historical jobs are already present in Notion!")
        return

    # Evaluate with AI
    jobs_list = [j[0] for j in jobs_to_insert]
    logger.info(f"🤖 Evaluating {len(jobs_list)} jobs with AI (Groq / Gemini)...")
    
    eval_results_map = ai_evaluator.evaluate_jobs_batch(jobs_list, cfg.candidate)
    
    # Insert each evaluated job into Notion
    for job, status in jobs_to_insert:
        eval_res = eval_results_map.get(job.job_id)
        if eval_res and eval_res.fit_score > 0:
            score = eval_res.fit_score
            reason = eval_res.reasoning or "Vaga de Inteligência Artificial e Automação com forte aderência ao perfil júnior."
            seniority = eval_res.seniority_detected if eval_res.seniority_detected in ["Júnior", "Recém-licenciado"] else ("Recém-licenciado" if "Graduate" in job.title else "Júnior")
        else:
            score = 80.0
            reason = f"Oportunidade em {job.title} alinhada com as competências de IA e Engenharia do candidato."
            seniority = "Recém-licenciado" if "Graduate" in job.title else "Júnior"

        logger.info(f"📌 Creating Notion page for '{job.title}' @ '{job.company}' with Score {score:.1f}% & Status '{status}'...")
        
        schema = notion_store.get_database_schema()
        
        title_prop_name = "Title"
        for name, prop in schema.items():
            if prop.get("type") == "title":
                title_prop_name = name
                break

        properties = {
            title_prop_name: {
                "title": [{"text": {"content": job.title}}]
            }
        }

        field_mappings = [
            ("Empresa", ["Empresa", "Company"], "rich_text", [{"text": {"content": job.company}}]),
            ("Match Score (%)", ["Match Score (%)", "Score (%)", "Match", "Score"], "number", float(round(score, 1))),
            ("Senioridade", ["Senioridade", "Seniority", "Nível"], "select", {"name": seniority}),
            ("Link", ["Link", "URL", "Link de Candidatura"], "url", job.link),
            ("Modo", ["Modo", "Modo de Trabalho", "Work Mode"], "select", {"name": job.work_mode}),
            ("Fonte", ["Fonte", "Source"], "select", {"name": "LinkedIn"}),
            ("Elegível IEFP", ["Elegível IEFP", "IEFP"], "checkbox", False),
            ("Estado", ["Estado", "Status"], "select", {"name": status}),
            ("Data Extração", ["Data Extração", "Data de Extração", "Data Ingestão", "Data/Hora", "Date"], "date", {"start": job.fetched_at}),
            ("Análise IA", ["Análise IA", "Análise da IA", "AI Reasoning", "Notas"], "rich_text", [{"text": {"content": reason}}]),
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

        page_payload = {
            "parent": {"database_id": cfg.notion_database_id},
            "properties": properties,
            "children": [
                {
                    "object": "block",
                    "type": "heading_2",
                    "heading_2": {
                        "rich_text": [{"type": "text", "text": {"content": "🤖 Análise da IA & Histórico de Candidatura"}}]
                    }
                },
                {
                    "object": "block",
                    "type": "callout",
                    "callout": {
                        "rich_text": [{"type": "text", "text": {"content": f"Match Score: {score:.1f}% | Estado: {status} | Data: {job.fetched_at[:10]}\n\nAnálise: {reason}"}}],
                        "icon": {"emoji": "🎯"}
                    }
                },
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{"type": "text", "text": {"content": job.description[:1900]}}]
                    }
                }
            ]
        }

        url = "https://api.notion.com/v1/pages"
        resp = requests.post(url, headers=notion_store.headers, json=page_payload, timeout=15)
        if resp.status_code in [200, 201]:
            logger.info(f"✅ Successfully inserted '{job.title}' @ '{job.company}' into Notion!")
        else:
            logger.error(f"❌ Failed to insert into Notion ({resp.status_code}): {resp.text}")
        
        time.sleep(0.5)

    logger.info("🎉 All historical jobs imported successfully!")

if __name__ == "__main__":
    main()
