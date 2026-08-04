import re
import datetime
import email.utils
from dataclasses import dataclass
from typing import List, Dict, Optional
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

# Strict Domain Keywords - Title MUST relate to AI, ML, Data Science, Data Engineering, or Data Analytics
AI_DATA_DOMAIN_KEYWORDS = [
    "ai", "ia", "data", "machine learning", "ml", "rag", "nlp", "llm", "deep learning", 
    "computer vision", "inteligência artificial", "inteligencia artificial", "ciência de dados", 
    "ciencia de dados", "analytics", "analista de dados", "engenheiro de dados", "data engineer", 
    "data analyst", "data scientist", "ai engineer", "ml engineer", "bi", "business intelligence", 
    "python", "prompt engineer", "algorithm", "estatística", "dados"
]

# Irrelevant Non-AI/Data Roles Disqualifiers in Title
IRRELEVANT_TECH_DISQUALIFIERS = [
    "php", "sap", "abap", "rpa", "blue prism", "embedded", "c++", "c/c++", "dotnet", ".net", 
    "c#", "frontend", "front-end", "front end", "react", "angular", "vue", "node.js", "wordpress", 
    "laravel", "qa", "tester", "sysadmin", "network", "cybersecurity", "cibersegurança", "salesforce", 
    "cobol", "ios", "android", "flutter", "web developer", "webmaster", "helpdesk", "support technician",
    "mainframe", "devops engineer", "scrum master"
]

TITLE_DISQUALIFIERS = [
    "senior", "sr", "lead", "principal", "head of", "director", "architect", "staff", "vp of", "manager"
]

YEARS_EXP_PATTERN = re.compile(
    r"\b([3-9]|1[0-5])\s*(?:\+|\-|[\u2010-\u2015\~]|to|a)?\s*([3-9]|1[0-5])?\s*(?:years?|yrs?|anos?)|"
    r"\b([3-9]|1[0-5])\s*(?:years?|yrs?|anos?)\s+(?:of\s+)?experience|"
    r"(?:at\s+least|mínimo\s+de?)\s+([3-9]|1[0-5])\s*(?:years?|yrs?|anos?)",
    re.IGNORECASE
)

# Mandatory Non-English/Portuguese Language Disqualifier (German, French, Spanish, Dutch, Italian mandatory requirements)
# Handles German/Portuguese/English phrases: "Du sprichst Deutsch und Englisch fließend", "Sie sprechen Deutsch", "Deutschkenntnisse", "Alemão e Inglês fluente"
MANDATORY_OTHER_LANGUAGES_PATTERN = re.compile(
    r"\b(?:german|deutsch|alemão|alemao|french|français|francais|francês|frances|spanish|español|espanhol|dutch|nederlands|italian|italiano)\b(?:\s*(?:and|&|/|or|und|e)?\s*(?:english|inglês|ingles)?)*\s*(?:fluently|fluent|fluency|c1|c2|b2|native|required|mandatory|essential|language\s+skills|level|nível|nivel|auf\s+c1|auf\s+b2|exigido|obrigatório|fließend|fließendes|fließende|fluente)\b|"
    r"\b(?:sprichst|sprechen|spricht|fließend|fließende|fließendes|gute|sehr\s+gute)\s+(?:deutsch|german)\b|"
    r"\b(?:deutsch|german|alemão|alemao)\s*(?:und|and|&|/|e)?\s*(?:englisch|english|inglês|ingles)?\s*(?:fließend|fließende|fließendes|kenntnisse|sprichst|sprechen|fluente)\b|"
    r"\b(?:speak|speaking|fluent\s+in|fluency\s+in|proficient\s+in|mastery\s+of)\s+(?:both\s+)?(?:german|deutsch|french|français|spanish|español|dutch|italian)\b|"
    r"\b(?:deutschkenntnisse|sprachkenntnisse)\b",
    re.IGNORECASE
)

def parse_job_date(date_str: str) -> datetime.date:
    """Parses various date formats to a standard datetime.date."""
    if not date_str:
        return datetime.date.today()
    try:
        if re.match(r"^\d{4}-\d{2}-\d{2}", date_str):
            return datetime.date.fromisoformat(date_str[:10])
        parsed_tuple = email.utils.parsedate_tz(date_str)
        if parsed_tuple:
            dt = datetime.datetime.fromtimestamp(email.utils.mktime_tz(parsed_tuple))
            return dt.date()
    except Exception:
        pass
    return datetime.date.today()

@dataclass
class ScoredJob:
    job: Job
    score: float
    matched_skills: List[str]
    missing_skills: List[str]
    seniority_status: str

class JobMatcher:
    def __init__(self, profile: CandidateProfile):
        self.profile = profile

    def evaluate_job(self, job: Job) -> ScoredJob:
        text = f"{job.title} {job.description}".lower()
        title_lower = job.title.lower()

        # 0. 24-Hour Freshness Filter (Max 1 day old)
        today = datetime.date.today()
        job_date = parse_job_date(job.pub_date)
        days_old = (today - job_date).days

        if days_old > 1:
            return ScoredJob(
                job=job,
                score=0.0,
                matched_skills=[],
                missing_skills=[],
                seniority_status="Vaga Antiga (> 24h)"
            )

        # 1. Mandatory Non-English/Portuguese Language Disqualification (German, French, Spanish, etc.)
        if MANDATORY_OTHER_LANGUAGES_PATTERN.search(text):
            return ScoredJob(
                job=job,
                score=0.0,
                matched_skills=[],
                missing_skills=[],
                seniority_status="Exige Outro Idioma (Alemão/Francês/Espanhol)"
            )

        # 2. Strict Irrelevant Role Disqualification (PHP, SAP, RPA, Embedded, C++, QA, Web Dev)
        for disq in IRRELEVANT_TECH_DISQUALIFIERS:
            if re.search(rf"\b{re.escape(disq)}\b", title_lower):
                return ScoredJob(job=job, score=0.0, matched_skills=[], missing_skills=[], seniority_status="Tecnologia Irrelevante")

        # 3. Mandatory AI & Data Science Domain Check
        has_domain_match = any(kw in title_lower for kw in ["ai", "ia", "data", "machine learning", "ml", "rag", "nlp", "llm", "analytics", "dados", "python"])
        if not has_domain_match:
            if not any(k in text for k in ["data scientist", "ai engineer", "machine learning", "python", "sql", "data analyst"]):
                return ScoredJob(job=job, score=0.0, matched_skills=[], missing_skills=[], seniority_status="Fora do Âmbito AI/Data Science")

        # 4. Seniority & Experience Disqualification Logic
        is_explicit_junior = any(j_term in title_lower for j_term in ["junior", "jr", "estágio", "estagio", "trainee", "graduate", "entry level", "intern"])
        
        disqualified = False
        if not is_explicit_junior:
            for disq in TITLE_DISQUALIFIERS:
                pattern = rf"\b{re.escape(disq)}\b" if len(disq) <= 3 else re.escape(disq)
                if re.search(pattern, title_lower):
                    disqualified = True
                    break

        if not disqualified:
            if YEARS_EXP_PATTERN.search(text) and not is_explicit_junior:
                disqualified = True

        if disqualified:
            return ScoredJob(
                job=job,
                score=0.0,
                matched_skills=[],
                missing_skills=[],
                seniority_status="Sénior / Requisitos Desajustados"
            )

        # 5. Target Role Title Base Score (55.0 points base for matching target AI/Data roles)
        title_score = 0.0
        exact_targets = ["data scientist", "ai engineer", "machine learning", "ml engineer", "rag", "nlp", "llm", "data analyst", "data engineer", "inteligência artificial", "ciência de dados"]
        
        if any(t in title_lower for t in exact_targets):
            title_score = 55.0
        elif any(t in title_lower for t in ["data", "ai", "ia", "python"]):
            title_score = 45.0
        else:
            title_score = 35.0

        # 6. Junior / Entry Level / IEFP Booster (+25.0 points)
        booster_score = 0.0
        seniority_status = "Geral / Pleno"

        if job.iefp_mentioned or "iefp" in text or "ativar" in text:
            booster_score = 25.0
            seniority_status = "Junior / Estágio IEFP"
        elif is_explicit_junior:
            booster_score = 25.0
            seniority_status = "Junior / Entry Level"
        elif any(b in text for b in ["recém-licenciado", "recem licenciado", "0-1", "0-2", "1-2", "trainee"]):
            booster_score = 20.0
            seniority_status = "Junior / 0-2 anos"

        # 7. Tech Stack Skill Matching (+5.0 points per matched skill)
        matched_skills: List[str] = []
        for canonical_skill, aliases in SKILL_ALIASES.items():
            for alias in aliases:
                pattern = rf"\b{re.escape(alias)}\b"
                if re.search(pattern, text):
                    matched_skills.append(canonical_skill)
                    break

        tech_score = min(20.0, len(matched_skills) * 5.0)

        # Calculate Final Match Score
        final_score = min(100.0, title_score + booster_score + tech_score)

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
            if evaluated.score >= 40.0:
                scored_jobs.append(evaluated)

        scored_jobs.sort(key=lambda x: x.score, reverse=True)
        return scored_jobs
