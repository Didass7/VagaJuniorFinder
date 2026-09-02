from __future__ import annotations
import os
import json
import tomllib
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
    groq_model_name: str = "openai/gpt-oss-120b"
    enable_ai_evaluation: bool = True

    ai_model_name: str = "gemini-3.5-flash-lite"
    
    # Notion Integration Configuration
    notion_token: str = os.getenv("NOTION_TOKEN", os.getenv("NOTION_API_KEY", ""))
    notion_database_id: str = os.getenv("NOTION_DATABASE_ID", "")
    enable_notion_sync: bool = True
    
    # Data Storage Paths
    cache_file: str = os.path.join("data", "jobs_cache.json")
    
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
    
    # 1. Load defaults from config.toml if present
    if os.path.exists("config.toml"):
        with open("config.toml", "rb") as f:
            toml_data = tomllib.load(f)
            
        app_cfg = toml_data.get("app", {})
        if "enable_ai_evaluation" in app_cfg: cfg.enable_ai_evaluation = app_cfg["enable_ai_evaluation"]
        if "ai_model_name" in app_cfg: cfg.ai_model_name = app_cfg["ai_model_name"]
        if "groq_model_name" in app_cfg: cfg.groq_model_name = app_cfg["groq_model_name"]
        if "enable_notion_sync" in app_cfg: cfg.enable_notion_sync = app_cfg["enable_notion_sync"]
        
        scoring_cfg = toml_data.get("scoring", {})
        if "top_match_threshold" in scoring_cfg: cfg.top_match_threshold = float(scoring_cfg["top_match_threshold"])
        if "promising_match_threshold" in scoring_cfg: cfg.promising_match_threshold = float(scoring_cfg["promising_match_threshold"])
        if "min_blended_score" in scoring_cfg: cfg.min_blended_score = float(scoring_cfg["min_blended_score"])
        if "ai_batch_size" in scoring_cfg: cfg.ai_batch_size = int(scoring_cfg["ai_batch_size"])

    # 2. Load from Profile JSON
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

_config_cache = {}

def get_current_config() -> AppConfig:
    profile = os.getenv("ACTIVE_PROFILE", "diogo").strip().lower()
    if profile not in _config_cache:
        _config_cache[profile] = load_config(profile)
    return _config_cache[profile]

class ConfigProxy:
    def __getattr__(self, name):
        return getattr(get_current_config(), name)
    def __setattr__(self, name, value):
        setattr(get_current_config(), name, value)

config = ConfigProxy()
