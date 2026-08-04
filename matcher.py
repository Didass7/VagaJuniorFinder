import re
from dataclasses import dataclass
from typing import List, Dict
from config import CandidateProfile
from scraper import Job

SKILL_ALIASES: Dict[str, List[str]] = {
    "python": ["python", "py"],
    "sql": ["sql", "mysql", "duckdb", "postgres", "postgresql", "sqlite", "tsql"],
    "pandas": ["pandas", "polars", "pyarrow"],
    "numpy": ["numpy"],
    "scikit-learn": ["scikit-learn", "sklearn", "scikitlearn"],
    "xgboost": ["xgboost", "lightgbm", "catboost"],
    "random forest": ["random forest", "decision tree"],
    "langchain": ["langchain", "llamaindex", "llama-index"],
    "chromadb": ["chromadb", "vector store", "vector database", "qdrant", "pinecone", "faiss"],
    "huggingface": ["huggingface", "hugging face", "transformers", "sentence-transformers"],
    "embeddings": ["embeddings", "vector embeddings"],
    "fastapi": ["fastapi", "flask", "rest api", "restful api"],
    "streamlit": ["streamlit", "gradio"],
    "git": ["git", "github", "github actions", "gitlab"],
    "rag": ["rag", "retrieval augmented generation", "retrieval-augmented"],
    "nlp": ["nlp", "natural language processing", "text processing"],
    "llm": ["llm", "llms", "large language model", "generative ai", "genai", "gpt"],
    "machine learning": ["machine learning", "ml", "deep learning"],
}

TITLE_DISQUALIFIERS = [
    "senior", "sr", "lead", "principal", "head of", "director", "architect", "staff", "vp of", "manager"
]

# Regex pattern catching experience requirements >= 3 years:
# Matches: "5 to 7 years", "5-7 years", "3 to 5 years", "3-5 years", "3+ years", "4+ years", "5+ years",
# "5 years of experience", "at least 3 years", "mínimo de 3 anos", etc.
YEARS_EXP_PATTERN = re.compile(
    r"\b([3-9]|1[0-5])\s*(?:\+|\-|to|a)\s*([3-9]|1[0-5])?\s*(?:years?|anos?)|"
    r"\b([3-9]|1[0-5])\s*\+\s*(?:years?|anos?)|"
    r"\b([3-9]|1[0-5])\s*(?:years?|anos?)\s+(?:of\s+)?experience|"
    r"at\s+least\s+([3-9]|1[0-5])\s*(?:years?|anos?)|"
    r"mínimo\s+de?\s+([3-9]|1[0-5])\s*(?:years?|anos?)",
    re.IGNORECASE
)

@dataclass
class ScoredJob:
    job: Job
    score: float
    matched_skills: List[str]
    missing_skills: List[str]
    seniority_status: str  # "Junior / Estágio IEFP", "Junior / Entry Level", "Geral / Pleno"

class JobMatcher:
    def __init__(self, profile: CandidateProfile):
        self.profile = profile

    def evaluate_job(self, job: Job) -> ScoredJob:
        text = f"{job.title} {job.description}".lower()
        title_lower = job.title.lower()

        # 1. Disqualification Logic
        is_explicit_junior = any(j_term in title_lower for j_term in ["junior", "jr", "estágio", "estagio", "trainee", "graduate", "entry level", "intern"])
        
        disqualified = False
        
        # Check Title Disqualifiers (unless explicitly Junior/Entry level in title)
        if not is_explicit_junior:
            for disq in TITLE_DISQUALIFIERS:
                pattern = rf"\b{re.escape(disq)}\b" if len(disq) <= 3 else re.escape(disq)
                if re.search(pattern, title_lower):
                    disqualified = True
                    break

        # Check Experience Years Disqualifier in text (>= 3 years)
        if not disqualified:
            if YEARS_EXP_PATTERN.search(text) and not is_explicit_junior:
                disqualified = True

        if disqualified:
            return ScoredJob(
                job=job,
                score=10.0,
                matched_skills=[],
                missing_skills=[],
                seniority_status="Sénior / Requisitos Desajustados"
            )

        # 2. Tech Stack Skill Matching (with Aliases)
        matched_skills: List[str] = []
        for canonical_skill, aliases in SKILL_ALIASES.items():
            for alias in aliases:
                pattern = rf"\b{re.escape(alias)}\b"
                if re.search(pattern, text):
                    matched_skills.append(canonical_skill)
                    break

        # Tech score calculation (up to 50 points)
        tech_score = min(50.0, len(matched_skills) * 8.5)

        # Tech Combo Bonus: Python + (SQL or Pandas) + (ML or RAG or LLM) -> +10 points
        has_python = "python" in matched_skills
        has_data = any(s in matched_skills for s in ["sql", "pandas", "numpy"])
        has_ai_ml = any(s in matched_skills for s in ["machine learning", "rag", "llm", "scikit-learn", "langchain", "nlp"])
        
        combo_bonus = 0.0
        if has_python and has_data and has_ai_ml:
            combo_bonus = 10.0

        # 3. Target Title Match (up to 25 points)
        title_score = 0.0
        core_role_keywords = ["ai engineer", "data scientist", "machine learning", "ml engineer", "rag", "nlp", "llm", "data analyst", "developer", "engenheiro"]
        
        for target in self.profile.target_titles:
            if target.lower() in title_lower:
                title_score = 25.0
                break
        
        if title_score == 0.0:
            for kw in core_role_keywords:
                if kw in title_lower:
                    title_score = 18.0
                    break

        # 4. Junior & IEFP Seniority Boosters (up to 20 points)
        booster_score = 0.0
        seniority_status = "Geral / Pleno"
        
        has_booster = False
        for booster in self.profile.junior_boosters:
            pattern = rf"\b{re.escape(booster)}\b"
            if re.search(pattern, text):
                has_booster = True
                break

        if job.iefp_mentioned or "iefp" in text or "ativar" in text:
            booster_score = 20.0
            seniority_status = "Junior / Estágio IEFP"
        elif is_explicit_junior or has_booster:
            booster_score = 20.0
            seniority_status = "Junior / Entry Level"
        elif "0-1" in text or "0-2" in text or "1-2" in text or "recém-licenciado" in text or "recem licenciado" in text:
            booster_score = 15.0
            seniority_status = "Junior / 0-2 anos"

        # 5. Location Preference Boost (+5 points for Portugal / Remote)
        location_score = 0.0
        loc_text = f"{job.location} {job.work_mode}".lower()
        if any(loc in loc_text for loc in ["portugal", "lisboa", "porto", "braga", "coimbra", "remoto", "remote"]):
            location_score = 5.0

        # Calculate Final Match Score
        final_score = min(100.0, tech_score + combo_bonus + title_score + booster_score + location_score)
        
        if title_score >= 18.0 and final_score < 45.0:
            final_score = 45.0

        return ScoredJob(
            job=job,
            score=round(final_score, 1),
            matched_skills=matched_skills,
            missing_skills=[],
            seniority_status=seniority_status
        )

    def process_jobs(self, jobs: List[Job]) -> List[ScoredJob]:
        scored_jobs = []
        for job in jobs:
            evaluated = self.evaluate_job(job)
            if evaluated.score >= 35.0:
                scored_jobs.append(evaluated)

        scored_jobs.sort(key=lambda x: x.score, reverse=True)
        return scored_jobs
