from __future__ import annotations
import re
import datetime
import email.utils
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any, Set
from config import CandidateProfile, config
from scraper import Job
from ai_evaluator import AIEvaluator, AIEvaluationResult

logger = logging.getLogger("Matcher")

# Irrelevant Non-Target Roles Disqualifiers (Hard Disqualification if present in title)
IRRELEVANT_ROLE_DISQUALIFIERS = [
    "php", "sap", "abap", "rpa", "blue prism", "embedded", "c++", "c/c++", "dotnet", ".net", 
    "c#", "frontend", "front-end", "front end", "ui engineer", "ux engineer", "ui/ux", "react", 
    "angular", "vue", "node.js", "wordpress", "laravel", "qa", "tester", "salesforce", "cobol", 
    "ios", "android", "flutter", "webmaster", "helpdesk", "support technician", 
    "electronics engineer", "rf engineer", "hardware engineer", "mainframe", "scrum master",
    "gestor de projeto", "project manager", "blockchain", "consultor funcional",
    "marketing", "social media", "paid media", "growth", "seo", "sem", "crm", "copywriter",
    "content writer", "content manager", "content creator", "content strategist",
    "branding", "traffic manager", "sales", "comercial", "orçamentista", "videógrafo", "videografo",
    "video editor", "video specialist", "editor de vídeo", "editor de video", "videomaker", "video producer",
    "multimedia", "multimédia", "graphic designer", "motion designer", "ui designer", "ux designer", "web designer", "3d artist", "animador", "animadora",
    "instructional designer", "e-learning", "elearning",
    "fotógrafo", "podcast", "account executive", "business developer",
    "professor", "professora", "formador", "formadora", "instrutor", "instrutora",
    "teacher", "instructor", "tutor", "docente", "explicador", "explicadora", "sharkcoders", "trainer",
    "administrativo", "administrativa", "contabilidade", "contabilista", "accounting", "accountant", "freelance",
    "recursos humanos", "recruiter", "recrutamento", "secretária", "secretaria", "secretariado", "financeiro", "financeira",
    "hr ", "human resources", "hris", "talent acquisition", "business analyst", "systems analyst", "process analyst",
    "crianças", "criancas", "adolescentes", "pós-letivo", "pos-letivo", "kids", "children", "academias de ia",
    "data entry", "introdução de dados", "introducao de dados", "entry assistant", "entry clerk",
    "volunteer", "voluntário", "voluntario", "trader", "crypto trader", "broker",
    "produção e montagem", "producao e montagem", "montagem", "operador de produção", "operador fabril"
]

# Title Disqualifiers for Senior / Lead / Level II-III / Doctorate Roles
TITLE_SENIORITY_DISQUALIFIERS = [
    "senior", "sénior", "sênior", "sr", "sr.", "snr", "lead", "principal", "head of", "director", "staff", "vp of", "manager",
    "phd", "ph.d", "doctorate", "doutoramento", "postdoc", "post-doc", "postdoctoral", "expert", "consultor sénior", "consultor sênior",
    "responsável", "responsavel", "coordenador", "coordenadora", "diretor", "diretora", "director", "chefe",
    "head", "gestor de equipa", "mid-senior", "mid/senior", "level 2", "level ii", "level 3", "level iii", " ii", " iii"
]

# Text-level Seniority Disqualifiers (Demanding explicit prior professional experience >0 years)
TEXT_SENIORITY_DISQUALIFIERS = [
    "seniority level mid-senior", "seniority level senior", "seniority level director", "seniority level executive",
    "technical leadership", "leadership experience", "experiência em liderança", "liderança técnica", "experiencia em liderança",
    "senior developer", "senior engineer", "senior backend", "senior software",
    "senior data scientist", "senior data engineer", "sénior developer", "sénior engineer", "sénior backend",
    "sr developer", "sr engineer",
    "1+ years", "2+ years", "3+ years", "4+ years", "5+ years", "6+ years", "7+ years", "8+ years", "9+ years", "10+ years",
    "+1 years", "+2 years", "+3 years", "+4 years", "+5 years", "+6 years", "+7 years", "+8 years", "+9 years", "+10 years",
    "+1 year", "+2 year", "+3 year",
    "1+ anos", "2+ anos", "3+ anos", "4+ anos", "5+ anos", "6+ anos", "7+ anos", "8+ anos", "9+ anos", "10+ anos",
    "+1 anos", "+2 anos", "+3 anos", "+4 anos", "+5 anos", "+6 anos", "+7 anos", "+8+ anos", "+9 anos", "+10 anos",
    "+1 ano", "+2 ano", "+3 ano",
    "1 ano de experiência", "2 anos de experiência", "3 anos de experiência", "4 anos de experiência", "5 anos de experiência",
    "1 year of experience", "2 years of experience", "3 years of experience", "4 years of experience", "5 years of experience",
    "1-2 years", "1-2 anos", "1 a 2 anos", "1 to 2 years", "1 to 3 years", "1 a 3 anos",
    "2 to 5 years", "2 a 5 anos", "2 a 3 anos", "2 to 3 years", "2 to 4 years", "2 a 4 anos", "3 to 5 years", "3 a 5 anos",
    "mínimo de 1 ano", "minimo de 1 ano", "mínimo de 2 anos", "minimo de 2 anos", "mínimo de 3 anos", "minimo de 3 anos",
    "minimum 1 year", "minimum 2 years", "minimum 3 years", "minimum of 1 year", "minimum of 2 years"
]

PORTUGAL_LOCATIONS = [
    "portugal", "lisboa", "lisbon", "porto", "coimbra", "braga", "castelo branco",
    "aveiro", "leiria", "faro", "setúbal", "setubal", "viseu", "évora", "evora",
    "guimarães", "guimaraes", "vila real", "bragança", "braganca", "guarda",
    "beja", "portalegre", "santarém", "santarem", "viana do castelo", "madeira",
    "funchal", "açores", "acores", "ponta delgada", "pombal", "louriçal", "alverca",
    "oeiras", "cascais", "sintra", "almada", "amadora", "matosinhos", "maia", "gaia",
    "vila nova de gaia", "ovar", "são joão da madeira", "figueira da foz", "covilhã",
    "fundão", "seixal", "barreiro", "loures", "odivelas", "vila franca de xira"
]

# Precompiled regexes for fast disqualifier matching
def build_strict_pattern(word: str) -> re.Pattern:
    return re.compile(rf"(?<![a-zA-Z0-9_]){re.escape(word.strip())}(?![a-zA-Z0-9_])", re.IGNORECASE)

IRRELEVANT_ROLE_PATTERNS = [(disq, build_strict_pattern(disq)) for disq in IRRELEVANT_ROLE_DISQUALIFIERS]
TITLE_SENIORITY_PATTERNS = [(disq, build_strict_pattern(disq)) for disq in TITLE_SENIORITY_DISQUALIFIERS]
TEXT_SENIORITY_PATTERNS = [(disq, build_strict_pattern(disq)) for disq in TEXT_SENIORITY_DISQUALIFIERS]
YEARS_OF_EXP_PATTERN = re.compile(
    r"\b(?:(?:mais\s+de|acima\s+de|superior\s+a|pelo\s+menos|no\s+m[ií]nimo|m[ií]nimo\s+de|m[ií]nimo|more\s+than|over|at\s+least|minimum\s+of|minimum)\s+)?"
    r"(?:[1-9]|1[0-9]|one|two|three|four|five|six|seven|eight|nine|ten|um|uma|dois|duas|tr[eê]s|quatro|cinco|seis|sete|oito|nove|dez)\s*\+?\s*(?:to|-|a)?\s*"
    r"(?:[1-9]|1[0-9]|one|two|three|four|five|six|seven|eight|nine|ten|um|uma|dois|duas|tr[eê]s|quatro|cinco|seis|sete|oito|nove|dez)?\s*\+?\s*"
    r"(?:years?|anos?)\s+(?:of\s+|de\s+)?(?:[\w\s]{0,40})?experi(?:ence|[eê]ncia)\b|"
    r"\bexperi(?:ence|[eê]ncia)\b[\w\s]{0,40}\b(?:(?:mais\s+de|acima\s+de|superior\s+a|pelo\s+menos|no\s+m[ií]nimo|m[ií]nimo\s+de|m[ií]nimo|more\s+than|over|at\s+least|minimum\s+of|minimum)\s+)?"
    r"(?:[1-9]|1[0-9]|one|two|three|four|five|six|seven|eight|nine|ten|um|uma|dois|duas|tr[eê]s|quatro|cinco|seis|sete|oito|nove|dez)\s*\+?\s*(?:years?|anos?)\b",
    re.IGNORECASE
)

# Disqualify jobs requiring PhD / Doctorate
PHD_REQUIREMENT_PATTERN = re.compile(
    r"\b(?:phd|ph\.d|doctorate|doutoramento|postdoc|post-doc|postdoctoral)\b",
    re.IGNORECASE
)

# Mandatory Non-English/Portuguese Language Requirements Pattern
MANDATORY_OTHER_LANGUAGES_PATTERN = re.compile(
    r"\b(?:native|fluent|fluently|fluency|fluency\s+in|fluent\s+in|proficiency\s+in|proficient\s+in|spoken|speaking|must\s+speak|knowledge\s+of)\s*(?:(?:in\s+)?(?:both\s+)?(?:english\s+(?:and|&|/|or)\s+|inglês\s+(?:e|ou)\s+|ingles\s+(?:e|ou)\s+))?(?:german|deutsch|french|français|francais|spanish|español|espanhol|dutch|nederlands|italian|italiano)\b|"
    r"\b(?:german|deutsch|french|français|francais|spanish|español|espanhol|dutch|nederlands|italian|italiano)\s+(?:native|proficiency|fluent|fluency|language|skills|speaker|speaking|clinics|customers|clients|partners|market|c1|c2|b2)\b|"
    r"\b(?:german|deutsch|french|français|francais|spanish|español|espanhol|dutch|nederlands|italian|italiano)\b(?:\s*(?:and|&|/|or|und|e)?\s*(?:english|inglês|ingles)?)*\s*(?:fluently|fluent|fluency|c1|c2|b2|native|required|mandatory|essential|language|level|nível|nivel|auf\s+c1|auf\s+b2|exigido|obrigatório|fließend|fließendes|fließende|fluente|proficiency)\b|"
    r"\b(?:sprichst|sprechen|spricht|fließend|fließende|fließendes|gute|sehr\s+gute)\s+(?:deutsch|german)\b|"
    r"\b(?:deutsch|german|alemão|alemao)\s*(?:und|and|&|/|e)?\s*(?:englisch|english|inglês|ingles)?\s*(?:fließend|fließende|fließendes|kenntnisse|sprichst|sprechen|fluente)\b|"
    r"\b(?:deutschkenntnisse|sprachkenntnisse)\b",
    re.IGNORECASE
)

# Foreign Language Post Pattern
FOREIGN_JOB_POST_PATTERN = re.compile(
    r"\b(?:über\s+uns|wir\s+suchen|deine\s+aufgaben|dein\s+profil|das\s+bringst\du\s+mit|unsere\s+anforderungen|in\s+deutschland|du\s+bist|unser\s+team|wir\s+bieten|bewirb\s+dich|standort|vollzeit|teilzeit|mehrparteienhäuser|mehrfamilienhäuser)\b|"
    r"\b(?:à\s+propos\s+de\s+nous|nous\s+recherchons|vos\s+missions|votre\s+profil|ce\s+que\s+nous\s+offrons)\b|"
    r"\b(?:sobre\s+nosotros|buscamos|tus\s+funciones|tu\s+perfil|requisitos\s+del\s+puesto)\b",
    re.IGNORECASE
)

# Geo-Restricted Remote Pattern (e.g. US/UK only, specific country lists without Portugal)
GEO_RESTRICTED_REMOTE_PATTERN = re.compile(
    r"\b(?:(?:we\s+are\s+)?(?:looking\s+for|open\s+to|hiring)\s+(?:candidates|people|engineers|talent)?\s*(?:in|from)\s+(?:the\s+)?(?:[a-zA-Z,\s]+)?only\b)|"
    r"\b(?:based\s+in|located\s+in|residing\s+in|resident\s+in|must\s+reside\s+in|must\s+be\s+located\s+in|living\s+in)\s+(?:the\s+)?(?:us|united\s+states|usa|uk|united\s+kingdom|germany|france|spain|italy|ireland|poland|canada|latin\s+america|latam|apac)\b|"
    r"\b(?:us|uk|usa|united\s+states|united\s+kingdom|germany|france|spain|canada)\s+only\b|"
    r"\b(?:only\s+open\s+to|only\s+hiring\s+in|only\s+for\s+candidates\s+in)\s+(?:the\s+)?(?:us|uk|united\s+states|united\s+kingdom|germany|france|spain|canada)\b|"
    r"\b(?:right\s+to\s+work\s+in|legally\s+authorized\s+to\s+work\s+in)\s+(?:the\s+)?(?:us|uk|united\s+states|united\s+kingdom|germany|france|canada)\b|"
    r"\|\s*(?:uk|us|usa|united\s+kingdom|germany|france|spain|italy|ireland|canada|emea|apac|latam)\s*\||"
    r"\(\s*(?:uk|us|usa|germany|france|spain|canada)\s+only\s*\)",
    re.IGNORECASE
)

# Zero-Experience Indicator Pattern (Strict word boundaries to prevent 'graduates' matching general degree requirements)
ZERO_EXP_INDICATOR_PATTERN = re.compile(
    r"\b(?:0\s*(?:a|to|-)\s*1\s*(?:ano|anos|year|years)|0\s*(?:anos|years)|sem\s+experi[eê]ncia|n[aã]o\s+[eé]\s+necess[aá]ria\s+experi[eê]ncia|n[aã]o\s+requer\s+experi[eê]ncia|rec[eé]m[- ]licenciad[oa]s?|est[aá]gio\s+profissional|est[aá]gios?|trainees?|internships?|\binterns?\b|\b(?:recém[- ]graduad[oa]s?|recem[- ]graduad[oa]s?|recent\s+graduates?|fresh\s+graduates?|new\s+graduates?|graduate\s+program|graduate\s+scheme)\b)\b",
    re.IGNORECASE
)

# Advanced Seniority Experience Hard Disqualifier Pattern (3+, 4+, 5+ years, +5 years, minimum 3+ years)
ADVANCED_EXP_HARD_DISQUALIFIERS_PATTERN = re.compile(
    r"(?:(?:\+|\>|mais\s+de|superior\s+a|pelo\s+menos|no\s+m[ií]nimo|m[ií]nimo\s+de|more\s+than|over|at\s+least|minimum\s+of|minimum)\s*)?"
    r"(?:[3-9]|1[0-9]|three|four|five|six|seven|eight|nine|ten|tr[eê]s|quatro|cinco|seis|sete|oito|nove|dez)\s*\+?\s*"
    r"(?:years?|anos?)\s+(?:of\s+|de\s+)?(?:[\w\s]{0,40})?experi(?:ence|[eê]ncia)\b|"
    r"(?<!\w)(?:\+|\>)?\s*[3-9]\s*\+?\s*(?:years?|anos?)\b|"
    r"\bexperi(?:ence|[eê]ncia)\b[\w\s]{0,40}(?:(?:\+|\>|mais\s+de|superior\s+a|pelo\s+menos|no\s+m[ií]nimo|m[ií]nimo\s+de|more\s+than|over|at\s+least|minimum\s+of|minimum)\s*)?(?:[3-9]|1[0-9]|three|four|five|six|seven|eight|nine|ten|tr[eê]s|quatro|cinco|seis|sete|oito|nove|dez)\s*\+?\s*(?:years?|anos?)\b",
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
    match_reason: str = ""
    ai_evaluated: bool = False
    ai_reasoning: str = ""
    ai_pros: List[str] = field(default_factory=lambda: [])
    ai_cons: List[str] = field(default_factory=lambda: [])

class JobMatcher:
    def __init__(self, profile: CandidateProfile):
        self.profile = profile
        self.ai_evaluator = AIEvaluator() if config.enable_ai_evaluation else None

    def evaluate_job(self, job: Job) -> ScoredJob:
        text = f"{job.title} {job.description}".lower()
        title_lower = job.title.lower()
        location_lower = job.location.lower()
        work_mode_lower = job.work_mode.lower()

        # -------------------------------------------------------------
        # HARD DISQUALIFICATION FILTERS (Score = 0.0)
        # -------------------------------------------------------------

        clean_desc = job.description.strip()
        clean_desc_lower = clean_desc.lower()
        incomplete_indicators = [
            "join or sign in to find your next job",
            "sign in to view", "sign in to apply", "log in to view", "faça login",
            "entre para ver", "registar para ver", "crie uma conta", "sign in to see more"
        ]
        
        if len(clean_desc) < 100 or any(ind in clean_desc_lower for ind in incomplete_indicators):
            return ScoredJob(job=job, score=0.0, matched_skills=[], missing_skills=[], seniority_status="Descrição Incompleta / Bloqueada", match_reason="Descrição indisponível", ai_reasoning="❌ Filtro Automático: Descrição indisponível ou protegida por login")

        if any(exp_term in clean_desc_lower for exp_term in ["oferta expirada", "vaga expirada", "anúncio expirado", "job no longer available", "no longer accepting applications", "this job is no longer available"]):
            return ScoredJob(job=job, score=0.0, matched_skills=[], missing_skills=[], seniority_status="Oferta Expirada", match_reason="Anúncio marcado como expirado", ai_reasoning="❌ Filtro Automático: Anúncio de vaga já expirado")

        today = datetime.date.today()
        job_date = parse_job_date(job.pub_date)
        if (today - job_date).days > 14:
            return ScoredJob(job=job, score=0.0, matched_skills=[], missing_skills=[], seniority_status="Vaga Antiga (> 14 dias)", match_reason="Oferta expirada (> 14 dias)", ai_reasoning="❌ Filtro Automático: Publicada há mais de 14 dias")

        profile_locs = [l.lower() for l in getattr(self.profile, 'locations', []) if l.lower() not in ["remoto", "remote", "hybrid", "híbrido", "hibrido"]]
        allowed_locations = set(PORTUGAL_LOCATIONS + profile_locs)
        is_portugal = any(loc in location_lower for loc in allowed_locations) or ("portugal" in text) or any(loc in text for loc in profile_locs if len(loc) > 3)
        is_strictly_remote = (work_mode_lower == "remoto") or ("remoto" in location_lower) or ("remote" in location_lower) or ("teletrabalho" in location_lower)

        if not is_portugal and not is_strictly_remote:
            return ScoredJob(job=job, score=0.0, matched_skills=[], missing_skills=[], seniority_status="Fora do Âmbito Geográfico", match_reason="Presencial/Híbrido no Estrangeiro", ai_reasoning="❌ Filtro Automático: Vaga presencial/híbrida no estrangeiro")

        if is_strictly_remote and GEO_RESTRICTED_REMOTE_PATTERN.search(text):
            return ScoredJob(job=job, score=0.0, matched_skills=[], missing_skills=[], seniority_status="Remoto Geobloqueado", match_reason="Vaga remota mas restrita", ai_reasoning="❌ Filtro Automático: Vaga remota com restrição geográfica a outros países")

        for disq, pattern in IRRELEVANT_ROLE_PATTERNS:
            if pattern.search(title_lower):
                return ScoredJob(job=job, score=0.0, matched_skills=[], missing_skills=[], seniority_status="Cargo Irrelevante", match_reason=f"Título desqualificado por conter '{disq}'", ai_reasoning=f"❌ Filtro Automático: Cargo irrelevante ({disq})")

        if any(k in text for k in ["crianças", "criancas", "adolescentes", "pós-letivo", "pos-letivo", "sharkcoders"]):
            return ScoredJob(job=job, score=0.0, matched_skills=[], missing_skills=[], seniority_status="Ensino Infantil", match_reason="Ensino de crianças/adolescentes", ai_reasoning="❌ Filtro Automático: Ensino de crianças/adolescentes")

        # Dynamic Core Domain Check based on profile's target titles and tech stack
        target_titles_lower = [t.lower() for t in self.profile.target_titles]
        tech_stack_lower = [t.lower() for t in self.profile.tech_stack]
        
        # Build core domain tokens from candidate profile and standard IT/AI/Data roles
        target_tokens = set()
        for tt in target_titles_lower:
            for token in re.findall(r"\b[a-zA-Z\u00C0-\u00FF]{2,}\b", tt):
                target_tokens.add(token.lower())
        for ts in tech_stack_lower:
            for token in re.findall(r"\b[a-zA-Z\u00C0-\u00FF]{2,}\b", ts):
                target_tokens.add(token.lower())
        
        core_domain_words = {
            "ai", "ia", "data", "dados", "analytics", "analyst", "analista", "scientist", "cientista",
            "machine", "learning", "deep", "nlp", "llm", "software", "developer", "desenvolvedor",
            "programmer", "programador", "engineer", "engenheiro", "engenharia", "python", "backend",
            "fullstack", "it", "ti", "informática", "informatica", "estágio", "estagio", "intern",
            "internship", "trainee", "graduate", "tech", "technology", "tecnologia"
        }
        all_domain_tokens = target_tokens.union(core_domain_words)

        title_tokens = set(re.findall(r"\b[a-zA-Z\u00C0-\u00FF]{2,}\b", title_lower))
        has_domain_in_title = bool(title_tokens.intersection(all_domain_tokens))
        has_target_title = any(tt in title_lower for tt in target_titles_lower) or has_domain_in_title
        has_tech_in_title = any(ts in title_lower for ts in tech_stack_lower)

        # Protect against cross-profile leaks (e.g. Data Engineer job slipping into Cybersecurity/DevOps profile)
        data_domain_terms = ["data engineer", "data scientist", "cientista de dados", "bi analyst", "analista de bi", "data architect"]
        security_net_terms = ["cybersecurity", "cibersegurança", "network engineer", "soc analyst", "sysadmin", "analista de soc", "técnico de redes"]

        target_titles_str = " ".join(target_titles_lower)
        is_security_profile = any(s in target_titles_str for s in ["cybersecurity", "cibersegurança", "devops", "network", "redes", "soc"])
        is_data_profile = any(d in target_titles_str for d in ["data scientist", "cientista de dados", "ai engineer", "engenheiro de ia", "machine learning"])

        if is_security_profile and not is_data_profile:
            if any(dt in title_lower for dt in data_domain_terms):
                return ScoredJob(job=job, score=0.0, matched_skills=[], missing_skills=[], seniority_status="Fora do Perfil", match_reason="Vaga de Engenharia/Ciência de Dados fora do perfil de Cibersegurança/DevOps", ai_reasoning="❌ Filtro Automático: Cargo de Dados fora do perfil de Cibersegurança")

        if is_data_profile and not is_security_profile:
            if any(st in title_lower for st in security_net_terms):
                return ScoredJob(job=job, score=0.0, matched_skills=[], missing_skills=[], seniority_status="Fora do Perfil", match_reason="Vaga de Cibersegurança/Redes fora do perfil de IA/Data", ai_reasoning="❌ Filtro Automático: Cargo de Cibersegurança/Redes fora do perfil de IA/Data")

        if not has_domain_in_title and not has_target_title and not has_tech_in_title:
            return ScoredJob(job=job, score=0.0, matched_skills=[], missing_skills=[], seniority_status="Fora do Perfil", match_reason="Título não corresponde às funções ou tecnologias alvo do candidato", ai_reasoning="❌ Filtro Automático: Título não corresponde às funções alvo do candidato")

        if PHD_REQUIREMENT_PATTERN.search(title_lower) or PHD_REQUIREMENT_PATTERN.search(text):
            return ScoredJob(job=job, score=0.0, matched_skills=[], missing_skills=[], seniority_status="Requer Doutoramento", match_reason="Exige PhD ou Doutoramento", ai_reasoning="❌ Filtro Automático: Exige Doutoramento (PhD)")

        if MANDATORY_OTHER_LANGUAGES_PATTERN.search(text) or FOREIGN_JOB_POST_PATTERN.search(text):
            return ScoredJob(job=job, score=0.0, matched_skills=[], missing_skills=[], seniority_status="Idioma Não Suportado", match_reason="Exige outro idioma nativo/fluente", ai_reasoning="❌ Filtro Automático: Exige outro idioma estrangeiro fluente/nativo")

        is_explicit_junior = any(j_term in title_lower for j_term in ["junior", "jr", "estágio", "estagio", "trainee", "graduate program", "entry level", "intern"])
        is_explicit_zero_to_one = any(b in text for b in ["recém-licenciado", "recem licenciado", "recém licenciado", "0-1", "recent graduate", "fresh graduate", "recém-graduado", "recem-graduado", "0 a 1 ano", "0 to 1 year"])
        has_verified_junior_indicator = is_explicit_junior or job.iefp_mentioned or is_explicit_zero_to_one

        # Check if the job is explicitly targeted at 0 years / Entry-Level / Estágio / Recém-Licenciado
        is_explicit_zero_exp = bool(ZERO_EXP_INDICATOR_PATTERN.search(text)) or job.iefp_mentioned or any(t in title_lower for t in ["estágio", "estagio", "trainee", "recém-licenciado", "recem-licenciado"])

        for disq, pattern in TITLE_SENIORITY_PATTERNS:
            if pattern.search(title_lower):
                return ScoredJob(job=job, score=0.0, matched_skills=[], missing_skills=[], seniority_status="Sénior / Liderança", match_reason=f"Título sénior ({disq})", ai_reasoning=f"❌ Filtro Automático: Título sénior ({disq})")

        # Hard Disqualification: Any explicit 3+, 4+, 5+ years requirement is definitively senior / not junior
        adv_exp_match = ADVANCED_EXP_HARD_DISQUALIFIERS_PATTERN.search(text)
        if adv_exp_match:
            return ScoredJob(
                job=job, score=0.0, matched_skills=[], missing_skills=[],
                seniority_status="Requer Experiência (>0 anos)",
                match_reason=f"Exige experiência sénior ({adv_exp_match.group(0).strip()})",
                ai_reasoning=f"❌ Filtro Automático: Exige experiência sénior ({adv_exp_match.group(0).strip()})"
            )

        # If not explicitly marked as a 0-experience / internship position, check for other experience requirements
        if not is_explicit_zero_exp:
            for disq, pattern in TEXT_SENIORITY_PATTERNS:
                if pattern.search(text):
                    return ScoredJob(job=job, score=0.0, matched_skills=[], missing_skills=[], seniority_status="Requer Experiência (>0 anos)", match_reason=f"Exige experiência prévia ({disq})", ai_reasoning=f"❌ Filtro Automático: Exige experiência prévia ({disq})")
                    
            exp_match = YEARS_OF_EXP_PATTERN.search(text)
            if exp_match:
                return ScoredJob(job=job, score=0.0, matched_skills=[], missing_skills=[], seniority_status="Requer Experiência (>0 anos)", match_reason=f"Exige experiência prévia ({exp_match.group(0).strip()})", ai_reasoning=f"❌ Filtro Automático: Exige experiência prévia ({exp_match.group(0).strip()})")


        # -------------------------------------------------------------
        # PHASE 2: WEIGHTED SCORING SYSTEM (0.0 to 100.0)
        # -------------------------------------------------------------

        # A. Target Role Title Base Score (Max 40.0 pts)
        title_score = 0.0
        if has_target_title:
            title_score = 40.0
        elif has_tech_in_title:
            title_score = 30.0
        else:
            title_score = 20.0

        # B. Seniority & IEFP Booster (Max 30.0 pts)
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

        # C. Location & Work Mode Match (Max 15.0 pts)
        location_score = 0.0
        if is_portugal:
            location_score = 15.0
        elif is_strictly_remote:
            location_score = 12.0

        # D. Tech Stack Skill Matching (Max 15.0 pts - 3.0 pts per matched skill)
        matched_skills = []
        for skill in self.profile.tech_stack:
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

        # Final Combined Score Calculation
        raw_score = title_score + booster_score + location_score + tech_score

        if not has_verified_junior_indicator:
            final_score = min(65.0, raw_score)
        else:
            final_score = min(100.0, raw_score)

        return ScoredJob(
            job=job,
            score=round(final_score, 1),
            matched_skills=matched_skills,
            missing_skills=[],
            seniority_status=seniority_status,
            match_reason=f"Avaliação Heurística. Skills: {', '.join(matched_skills) if matched_skills else 'Nenhuma'}."
        )

    def process_jobs(self, jobs: List[Job], include_disqualified: bool = False) -> List[ScoredJob]:
        # Stage 1: Fast Heuristic Pre-filter
        heuristic_candidates: List[ScoredJob] = []
        disqualified_jobs: List[ScoredJob] = []
        for job in jobs:
            evaluated = self.evaluate_job(job)
            if evaluated.score >= 55.0:
                heuristic_candidates.append(evaluated)
            else:
                disqualified_jobs.append(evaluated)

        if not heuristic_candidates:
            return disqualified_jobs if include_disqualified else []

        # Stage 2: Batch AI Evaluation
        if self.ai_evaluator and self.ai_evaluator.is_available:
            logger.info(f"🤖 Stage 2: AI Evaluator ACTIVE ({self.ai_evaluator.active_provider}). Evaluating {len(heuristic_candidates)} candidate jobs...")
            candidate_jobs = [sj.job for sj in heuristic_candidates]
            ai_results = self.ai_evaluator.evaluate_jobs_batch(candidate_jobs, self.profile, batch_size=4)

            final_scored_jobs: List[ScoredJob] = []
            ai_accepted = 0
            ai_rejected = 0

            for sj in heuristic_candidates:
                ai_res = ai_results.get(sj.job.job_id)
                if ai_res:
                    reason_lower = ai_res.reasoning.lower()
                    seniority_det_lower = (ai_res.seniority_detected or "").lower()
                    is_clearly_senior = any(s in seniority_det_lower for s in ["senior", "sénior", "sênior", "lead", "principal", "director", "executive", "head of"])
                    is_demanding_3plus_years = ("exige" in reason_lower and any(yr in reason_lower for yr in ["3 anos", "4 anos", "5 anos", "6 anos", "7 anos", "8 anos", "10 anos", "superior a 2", "superior a 3"]))

                    # If AI explicitly marked the job as unsuitable, 0 fit score, or non-junior/senior
                    if not ai_res.is_suitable or ai_res.fit_score == 0 or is_clearly_senior or is_demanding_3plus_years:
                        sj.score = 0.0
                        sj.seniority_status = f"Rejeitada por IA ({ai_res.seniority_detected or 'Inadequada'})"
                        sj.match_reason = ai_res.reasoning
                        sj.ai_reasoning = f"❌ Rejeitada por IA: {ai_res.reasoning}"
                        ai_rejected += 1
                        if include_disqualified:
                            final_scored_jobs.append(sj)
                        continue

                    # Only jobs verified as suitable by AI are accepted
                    blended_score = round(0.5 * sj.score + 0.5 * ai_res.fit_score, 1)
                    if blended_score < 50.0:
                        sj.score = 0.0
                        sj.seniority_status = "Score Insuficiente"
                        sj.match_reason = ai_res.reasoning
                        sj.ai_reasoning = f"❌ Score Insuficiente ({blended_score}%): {ai_res.reasoning}"
                        ai_rejected += 1
                        if include_disqualified:
                            final_scored_jobs.append(sj)
                        continue

                    sj.score = blended_score
                    sj.ai_evaluated = True
                    sj.ai_reasoning = f"✅ Adequada ({blended_score}%): {ai_res.reasoning}"
                    if ai_res.seniority_detected and ai_res.seniority_detected != "Desconhecido":
                        sj.seniority_status = ai_res.seniority_detected
                    sj.ai_pros = ai_res.pros
                    sj.ai_cons = ai_res.cons
                    
                    if "[TRUNCADO]" in sj.job.title:
                        sj.seniority_status = "Requer Verificação (Truncado)"
                        sj.score = min(sj.score, 50.0)
                        
                    final_scored_jobs.append(sj)
                    ai_accepted += 1
                else:
                    text_c = f"{sj.job.title} {sj.job.description}".lower()
                    if "iefp" in text_c or "ativar.pt" in text_c:
                        sj.seniority_status = "Elegível IEFP"
                    elif "estágio" in text_c or "estagio" in text_c or "trainee" in text_c:
                        sj.seniority_status = "Estágio"
                    elif "recém-licenciado" in text_c or "recem-licenciado" in text_c or "0-1" in text_c:
                        sj.seniority_status = "Recém-Licenciado"
                    else:
                        sj.seniority_status = "Júnior Potencial"
                        
                    if "[TRUNCADO]" in sj.job.title:
                        sj.seniority_status = "Requer Verificação (Truncado)"
                        sj.score = min(sj.score, 50.0)

                    if not sj.ai_reasoning:
                        sj.ai_reasoning = f"Avaliação Heurística: Vaga adequada para perfil Júnior ({', '.join(sj.matched_skills[:3]) if sj.matched_skills else 'Target Role'})"
                    final_scored_jobs.append(sj)

            logger.info(f"🤖 Stage 2 AI Summary: {ai_accepted} accepted, {ai_rejected} rejected as non-junior/unsuitable.")
            if include_disqualified:
                final_scored_jobs.extend(disqualified_jobs)
            final_scored_jobs.sort(key=lambda x: x.score, reverse=True)
            return final_scored_jobs
        else:
            logger.info("ℹ️ Stage 2: AI Evaluator NOT ACTIVE — Neither GROQ_API_KEY nor GEMINI_API_KEY was found in environment. Using Stage 1 Heuristic Scoring.")
            for sj in heuristic_candidates:
                if not sj.ai_reasoning:
                    sj.ai_reasoning = f"Avaliação Heurística: Vaga adequada para perfil Júnior ({', '.join(sj.matched_skills[:3]) if sj.matched_skills else 'Target Role'})"
            if include_disqualified:
                heuristic_candidates.extend(disqualified_jobs)
            heuristic_candidates.sort(key=lambda x: x.score, reverse=True)
            return heuristic_candidates
