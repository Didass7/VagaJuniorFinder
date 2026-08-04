import os
from dataclasses import dataclass, field
from typing import List, Dict
from dotenv import load_dotenv

load_dotenv()

@dataclass
class CandidateProfile:
    name: str = "Diogo Oliveira"
    email: str = "diogon.oliveira1@gmail.com"
    degree: str = "Licenciatura em Engenharia Informática (Média 15/20)"
    iefp_eligible: bool = True
    languages: List[str] = field(default_factory=lambda: ["Português (Nativo)", "Inglês (C2 - Fluente)"])
    
    # Target job titles
    target_titles: List[str] = field(default_factory=lambda: [
        "Junior AI Engineer", "AI Engineer",
        "Junior Data Scientist", "Data Scientist",
        "Machine Learning Engineer", "Junior ML Engineer",
        "RAG Developer", "NLP Engineer", "LLM Engineer",
        "Estágio AI Engineer", "Estágio Data Scientist"
    ])
    
    # Key technical skills to match in job descriptions
    tech_stack: List[str] = field(default_factory=lambda: [
        "python", "sql", "mysql", "duckdb", "pandas", "numpy",
        "scikit-learn", "sklearn", "xgboost", "random forest",
        "langchain", "chromadb", "huggingface", "embeddings",
        "fastapi", "streamlit", "git", "github actions", "pyarrow",
        "nlp", "rag", "llm", "machine learning", "deep learning",
        "pytorch", "tensorflow"
    ])
    
    # Positive keywords for boosting match score
    junior_boosters: List[str] = field(default_factory=lambda: [
        "junior", "jr", "entry level", "graduate", "trainee",
        "estágio", "estagio", "iefp", "ativar.pt", "ativar",
        "0-1", "0-2", "recém-licenciado", "recem licenciado", "intern", "internship"
    ])
    
    # Negative keywords for disqualification or heavy penalty
    disqualifiers: List[str] = field(default_factory=lambda: [
        "senior", "sr", "lead", "principal", "head of",
        "manager", "director", "architect", "5+ years", "5+ anos",
        "7+ years", "7+ anos", "8+ years", "10+ years"
    ])
    
    # Preferred locations
    locations: List[str] = field(default_factory=lambda: [
        "portugal", "lisboa", "porto", "braga", "coimbra", "remoto", "remote", "hybrid", "híbrido", "europe"
    ])

@dataclass
class AppConfig:
    candidate: CandidateProfile = field(default_factory=CandidateProfile)
    
    # Email / SMTP Configuration
    smtp_server: str = os.getenv("SMTP_SERVER", "smtp.gmail.com")
    smtp_port: int = int(os.getenv("SMTP_PORT", "587"))
    smtp_email: str = os.getenv("SMTP_EMAIL", "diogon.oliveira1@gmail.com")
    smtp_password: str = os.getenv("SMTP_PASSWORD", "")
    receiver_email: str = os.getenv("RECEIVER_EMAIL", "diogon.oliveira1@gmail.com")
    
    # API Keys / Feeds
    itjobs_api_key: str = os.getenv("ITJOBS_API_KEY", "")
    
    # Data Storage Paths
    reports_dir: str = os.getenv("REPORTS_DIR", "reports")
    cache_file: str = os.getenv("CACHE_FILE", "jobs_cache.json")
    
    # Scoring Thresholds
    top_match_threshold: float = 80.0
    promising_match_threshold: float = 60.0

config = AppConfig()
