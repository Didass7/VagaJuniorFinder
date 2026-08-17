import os
import json
from dataclasses import dataclass, field
from typing import List, Dict
from dotenv import load_dotenv

load_dotenv()

@dataclass
class CandidateProfile:
    name: str = ""
    email: str = ""
    degree: str = ""
    iefp_eligible: bool = False
    languages: List[str] = field(default_factory=list)
    search_queries: List[str] = field(default_factory=list)
    target_titles: List[str] = field(default_factory=list)
    tech_stack: List[str] = field(default_factory=list)
    junior_boosters: List[str] = field(default_factory=list)
    locations: List[str] = field(default_factory=list)

@dataclass
class AppConfig:
    candidate: CandidateProfile = field(default_factory=CandidateProfile)
    
    # API Keys / Feeds
    itjobs_api_key: str = os.getenv("ITJOBS_API_KEY", "")
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", os.getenv("GOOGLE_API_KEY", ""))
    groq_api_key: str = os.getenv("GROQ_API_KEY", "")
    groq_model_name: str = os.getenv("GROQ_MODEL_NAME", "openai/gpt-oss-120b")
    enable_ai_evaluation: bool = os.getenv("ENABLE_AI_EVALUATION", "true").lower() == "true"

    ai_model_name: str = os.getenv("AI_MODEL_NAME", "gemini-3.6-flash")
    
    # Notion Integration Configuration
    notion_token: str = os.getenv("NOTION_TOKEN", os.getenv("NOTION_API_KEY", ""))
    notion_database_id: str = os.getenv("NOTION_DATABASE_ID", "")
    enable_notion_sync: bool = os.getenv("ENABLE_NOTION_SYNC", "true").lower() == "true"
    
    # Data Storage Paths
    cache_file: str = os.getenv("CACHE_FILE", os.path.join("data", "jobs_cache.json"))
    
    # Scoring Thresholds
    top_match_threshold: float = 75.0
    promising_match_threshold: float = 55.0

def load_config() -> AppConfig:
    cfg = AppConfig()
    
    active_profile = os.getenv("ACTIVE_PROFILE", "diogo_ai")
    profile_path = os.path.join("profiles", f"{active_profile}.json")
    
    # Make cache file specific to the profile
    cfg.cache_file = os.path.join("data", f"jobs_cache_{active_profile}.json")
    
    if os.path.exists(profile_path):
        with open(profile_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
            # Load candidate info
            if "candidate" in data:
                cfg.candidate = CandidateProfile(**data["candidate"])
            
            # Override notion database ID if provided
            if data.get("notion_database_id"):
                cfg.notion_database_id = data["notion_database_id"]
    else:
        print(f"Warning: Profile '{active_profile}' not found at {profile_path}. Using empty defaults.")
        
    return cfg

config = load_config()
