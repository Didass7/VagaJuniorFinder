import os
from dataclasses import dataclass, field
from typing import List, Dict
from dotenv import load_dotenv

load_dotenv()

@dataclass
class CandidateProfile:
    name: str = "Diogo Oliveira"
    email: str = "diogon.oliveira1@gmail.com"
    degree: str = "Licenciatura em Engenharia Informática (IPCB-ESTCB | Média 15/20)"
    iefp_eligible: bool = True
    languages: List[str] = field(default_factory=lambda: [
        "Português (Nativo)", "Inglês (C2 - Proficiente)", "Espanhol (B1)", "Alemão (A2)"
    ])
    
    # Target job titles strictly in AI, Data Science, ML, and Data Engineering
    target_titles: List[str] = field(default_factory=lambda: [
        "Junior AI Engineer", "AI Engineer", "AI Developer",
        "Junior Data Scientist", "Data Scientist",
        "Machine Learning Engineer", "Junior ML Engineer",
        "RAG Developer", "NLP Engineer", "LLM Engineer",
        "Junior Data Engineer", "Junior Data Analyst",
        "Estágio AI Engineer", "Estágio Data Scientist",
        "Estágio Profissional IEFP", "Estágio ATIVAR.pt"
    ])
    
    # Key technical skills from Diogo's CV to match in job descriptions
    tech_stack: List[str] = field(default_factory=lambda: [
        "python", "sql", "mysql", "duckdb", "pandas", "numpy",
        "scikit-learn", "sklearn", "xgboost", "random forest",
        "langchain", "chromadb", "huggingface", "embeddings",
        "fastapi", "streamlit", "git", "github actions", "pyarrow", "parquet",
        "nlp", "rag", "llm", "machine learning", "deep learning",
        "monte carlo", "poisson"
    ])
    
    # Positive keywords for boosting match score
    junior_boosters: List[str] = field(default_factory=lambda: [
        "junior", "jr", "entry level", "graduate", "trainee",
        "estágio", "estagio", "iefp", "ativar.pt", "ativar",
        "0-1", "recém-licenciado", "recem licenciado", "intern", "internship"
    ])
    
    # Preferred locations
    locations: List[str] = field(default_factory=lambda: [
        "portugal", "lisboa", "porto", "braga", "coimbra", "castelo branco",
        "remoto", "remote", "hybrid", "híbrido"
    ])

@dataclass
class AppConfig:
    candidate: CandidateProfile = field(default_factory=CandidateProfile)
    

    
    # API Keys / Feeds
    itjobs_api_key: str = os.getenv("ITJOBS_API_KEY", "")
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", os.getenv("GOOGLE_API_KEY", ""))
    groq_api_key: str = os.getenv("GROQ_API_KEY", "")
    groq_model_name: str = os.getenv("GROQ_MODEL_NAME", "llama-3.1-8b-instant")
    enable_ai_evaluation: bool = os.getenv("ENABLE_AI_EVALUATION", "true").lower() == "true"

    ai_model_name: str = os.getenv("AI_MODEL_NAME", "gemini-2.5-flash")
    
    # Notion Integration Configuration
    notion_token: str = os.getenv("NOTION_TOKEN", os.getenv("NOTION_API_KEY", ""))
    notion_database_id: str = os.getenv("NOTION_DATABASE_ID", "")
    enable_notion_sync: bool = os.getenv("ENABLE_NOTION_SYNC", "true").lower() == "true"
    
    # Data Storage Paths
    cache_file: str = os.getenv("CACHE_FILE", os.path.join("data", "jobs_cache.json"))
    
    # Scoring Thresholds
    top_match_threshold: float = 75.0
    promising_match_threshold: float = 55.0

config = AppConfig()
