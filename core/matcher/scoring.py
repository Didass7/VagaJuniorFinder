import re
from dataclasses import dataclass, field
from typing import List

from scrapers import Job
from core.config import CandidateProfile

@dataclass
class ScoreComponents:
    title_score: float
    booster_score: float
    location_score: float
    tech_score: float
    seniority_status: str
    preferred_loc_match: bool
    preferred_loc_name: str
    matched_skills: List[str]

@dataclass
class ScoredJob:
    job: Job
    score: float
    matched_skills: List[str]
    missing_skills: List[str]
    seniority_status: str
    match_reason: str = ""
    ai_evaluated: bool = False
    ai_reasoning: str = ""
    ai_pros: List[str] = field(default_factory=lambda: [])
    ai_cons: List[str] = field(default_factory=lambda: [])

def clean_analysis_text(text: str) -> str:
    if not text:
        return ""
    cleaned = re.sub(r'[\U00010000-\U0010ffff]|[\u2600-\u27bf]|[\u2300-\u23ff]', '', text)
    pattern = r'^\s*(?:Adequada|Inadequada|Aprovada|Rejeitada(?:\s*por\s*IA)?|Filtro\s*Automático)?(?:\s*\([^)]*\))?\s*:\s*'
    for _ in range(5):
        new_cleaned = re.sub(pattern, '', cleaned, count=1, flags=re.IGNORECASE).strip()
        if new_cleaned == cleaned:
            break
        cleaned = new_cleaned
    cleaned = cleaned.strip()
    if cleaned:
        cleaned = cleaned[0].upper() + cleaned[1:]
    return cleaned

def calculate_score(job: Job, profile: CandidateProfile, text: str, title_lower: str, location_lower: str, work_mode_lower: str, is_portugal: bool, is_strictly_remote: bool, has_target_title: bool, has_tech_in_title: bool, is_explicit_junior: bool, is_explicit_zero_to_one: bool, has_verified_junior_indicator: bool) -> ScoreComponents:
    title_score = 0.0
    if has_target_title:
        title_score = 40.0
    elif has_tech_in_title:
        title_score = 30.0
    else:
        title_score = 20.0

    booster_score = 0.0
    seniority_status = "Nível Inicial"

    if job.iefp_mentioned or "iefp" in text or "ativar.pt" in text or "ativar pt" in text:
        booster_score = 30.0
        seniority_status = "Elegível IEFP / ATIVAR.pt"
    elif is_explicit_junior:
        booster_score = 25.0
        seniority_status = "Junior / Entry Level"
    elif is_explicit_zero_to_one:
        booster_score = 20.0
        seniority_status = "Junior (0-1 ano)"
    else:
        booster_score = 10.0
        seniority_status = "Nível Geral (Requer Verificação)"

    location_score = 0.0
    preferred_loc_match = False
    preferred_loc_name = ""

    pref_locs = getattr(profile, "preferred_locations", [])
    for pl in pref_locs:
        pl_lower = pl.lower()
        if len(pl_lower) > 2 and (pl_lower in location_lower or re.search(rf"\b{re.escape(pl_lower)}\b", text)):
            preferred_loc_match = True
            preferred_loc_name = pl.title()
            break

    bonus_amount = getattr(profile, "preferred_location_bonus", 15.0) if preferred_loc_match else 0.0

    if is_portugal:
        location_score = 15.0 + bonus_amount
    elif is_strictly_remote:
        location_score = 12.0 + (bonus_amount if preferred_loc_match else 0.0)

    matched_skills = []
    for skill in profile.tech_stack:
        escaped = re.escape(skill)
        prefix = r"\b" if skill[0].isalnum() else ""
        suffix = r"\b" if skill[-1].isalnum() else ""
        pattern = rf"{prefix}{escaped}{suffix}"
        if re.search(pattern, text, re.IGNORECASE):
            if skill not in matched_skills:
                matched_skills.append(skill)

    tech_score = min(15.0, len(matched_skills) * 3.0)
    if len(matched_skills) == 0:
        tech_score = 0.0 if (has_target_title or has_tech_in_title) else -10.0

    return ScoreComponents(
        title_score=title_score,
        booster_score=booster_score,
        location_score=location_score,
        tech_score=tech_score,
        seniority_status=seniority_status,
        preferred_loc_match=preferred_loc_match,
        preferred_loc_name=preferred_loc_name,
        matched_skills=matched_skills
    )
