from __future__ import annotations
import os
import json
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
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
    preferred_locations: List[str] = field(default_factory=list)
    preferred_location_bonus: float = 15.0

@dataclass
class AppConfig:
    candidate: CandidateProfile = field(default_factory=CandidateProfile)
    
    # API Keys / Feeds
    itjobs_api_key: str = os.getenv("ITJOBS_API_KEY", "")
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", os.getenv("GOOGLE_API_KEY", ""))
    groq_api_key: str = os.getenv("GROQ_API_KEY", "")
    groq_model_name: str = os.getenv("GROQ_MODEL_NAME", "openai/gpt-oss-120b")
    enable_ai_evaluation: bool = os.getenv("ENABLE_AI_EVALUATION", "true").lower() == "true"

    ai_model_name: str = os.getenv("AI_MODEL_NAME", "gemini-3.5-flash-lite")
    
    # Notion Integration Configuration
    notion_token: str = os.getenv("NOTION_TOKEN", os.getenv("NOTION_API_KEY", ""))
    notion_database_id: str = os.getenv("NOTION_DATABASE_ID", "")
    enable_notion_sync: bool = os.getenv("ENABLE_NOTION_SYNC", "true").lower() == "true"
    
    # Data Storage Paths
    cache_file: str = os.getenv("CACHE_FILE", os.path.join("data", "jobs_cache.json"))
    
    # Extra Scrapers & API Configurations
    indeed_cookies: str = os.getenv("INDEED_COOKIES", "")
    indeed_proxy: str = os.getenv("INDEED_PROXY", "")
    jooble_api_key: str = os.getenv("JOOBLE_API_KEY", "")
    rapidapi_key: str = os.getenv("RAPIDAPI_KEY", os.getenv("JSEARCH_API_KEY", ""))
    adzuna_app_id: str = os.getenv("ADZUNA_APP_ID", "")
    adzuna_app_key: str = os.getenv("ADZUNA_APP_KEY", "")

    # Scoring Thresholds & Batch Parameters
    top_match_threshold: float = 75.0
    promising_match_threshold: float = 55.0
    min_blended_score: float = 50.0
    ai_batch_size: int = 4

def load_config(profile_name: Optional[str] = None) -> AppConfig:
    cfg = AppConfig()
    
    active_profile = profile_name or os.getenv("ACTIVE_PROFILE", "diogo")
    profile_path = os.path.join("profiles", f"{active_profile}.json")
    
    # Make cache file specific to the profile (respect explicit CACHE_FILE env var if set)
    if not os.getenv("CACHE_FILE"):
        cfg.cache_file = os.path.join("data", f"jobs_cache_{active_profile}.json")
    os.makedirs(os.path.dirname(cfg.cache_file) or "data", exist_ok=True)
    
    if os.path.exists(profile_path):
        with open(profile_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
            # Load candidate info defensively
            if "candidate" in data:
                from dataclasses import fields
                valid_keys = {f.name for f in fields(CandidateProfile)}
                filtered_candidate = {k: v for k, v in data["candidate"].items() if k in valid_keys}
                cfg.candidate = CandidateProfile(**filtered_candidate)
            
            # Override notion database ID if provided
            if data.get("notion_database_id"):
                cfg.notion_database_id = data["notion_database_id"]

            # Custom profile thresholds (if configured)
            if "promising_match_threshold" in data:
                cfg.promising_match_threshold = float(data["promising_match_threshold"])
            if "top_match_threshold" in data:
                cfg.top_match_threshold = float(data["top_match_threshold"])
            if "min_blended_score" in data:
                cfg.min_blended_score = float(data["min_blended_score"])
            if "ai_batch_size" in data:
                cfg.ai_batch_size = int(data["ai_batch_size"])
    else:
        print(f"Warning: Profile '{active_profile}' not found at {profile_path}. Using empty defaults.")
        
    return cfg

config = load_config()
