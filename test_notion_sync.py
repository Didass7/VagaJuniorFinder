import os
import sys
import io
import logging
from config import config

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from scraper import Job

from matcher import JobMatcher, ScoredJob
from notion_store import NotionStore
from ai_evaluator import AIEvaluator

logging.basicConfig(level=logging.INFO)

def test_live_notion_and_groq():
    print("🚀 Testing Groq AI & Notion Sync Live...")
    
    # 1. Mock Sample Job
    sample_job = Job(
        title="Junior AI Engineer",
        company="Tech Innovation Lab",
        location="Lisboa, Portugal (Híbrido)",
        work_mode="Híbrido",
        description="Procuramos um Junior AI Engineer recém-licenciado com paixão por Python, SQL, LLMs e RAG. Vaga elegível para Estágio Profissional IEFP / ATIVAR.pt. Excelente oportunidade para início de carreira em Inteligência Artificial.",
        link="https://example.com/test-job-ai-engineer-12345",
        source="LinkedIn",
        pub_date="2026-08-05"
    )

    # 2. Evaluate with JobMatcher & AI Evaluator
    matcher = JobMatcher(config.candidate)
    evaluator = AIEvaluator()

    print(f"🤖 Active AI Provider: {evaluator.active_provider}")
    ai_result = evaluator.evaluate_job(sample_job, config.candidate)
    
    if ai_result:
        print(f"✅ AI Fit Score: {ai_result.fit_score}%")
        print(f"✅ AI Reasoning: {ai_result.reasoning}")
        print(f"✅ AI Seniority Detected: {ai_result.seniority_detected}")
        
        scored_job = ScoredJob(
            job=sample_job,
            score=ai_result.fit_score,
            matched_skills=["python", "sql", "rag", "llm"],
            missing_skills=[],
            seniority_status="Elegível IEFP / ATIVAR.pt",
            match_reason=ai_result.reasoning,
            ai_evaluated=True,
            ai_reasoning=ai_result.reasoning,
            ai_pros=ai_result.pros,
            ai_cons=ai_result.cons
        )
    else:
        print("⚠️ AI evaluation skipped (no API key configured). Using rule matcher score.")
        scored_job = matcher.evaluate_job(sample_job)

    # 3. Sync to Notion
    notion_store = NotionStore()
    if notion_store.is_configured:
        print(f"📡 Syncing sample job to Notion Database ID: {notion_store.database_id[:8]}...")
        synced = notion_store.sync_jobs([scored_job])
        if synced > 0:
            print("🎉 SUCCESS! Sample job successfully created inside your Notion Database!")
        else:
            print("ℹ️ Sample job was already present or Notion response failed. Check logs above.")
    else:
        print("⚠️ Notion NOT configured. Please verify NOTION_TOKEN and NOTION_DATABASE_ID in your .env file.")

if __name__ == "__main__":
    test_live_notion_and_groq()
