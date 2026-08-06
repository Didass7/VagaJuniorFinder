import re
import datetime
import email.utils
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from config import CandidateProfile, config
from scraper import Job
from ai_evaluator import AIEvaluator, AIEvaluationResult

# Skill canonical mapping & aliases based on Diogo Oliveira's CV
SKILL_ALIASES: Dict[str, List[str]] = {
    "python": ["python", "py"],
    "sql": ["sql", "mysql", "duckdb", "postgres", "postgresql", "sqlite", "tsql"],
    "duckdb": ["duckdb"],
    "pyarrow": ["pyarrow", "parquet"],
    "pandas": ["pandas", "polars"],
    "numpy": ["numpy"],
    "scikit-learn": ["scikit-learn", "sklearn", "scikitlearn"],
    "xgboost": ["xgboost", "lightgbm", "catboost"],
    "random forest": ["random forest", "decision tree", "ensemble algorithms"],
    "langchain": ["langchain", "llamaindex", "llama-index"],
    "chromadb": ["chromadb", "vector store", "vector database", "qdrant", "pinecone", "faiss"],
    "huggingface": ["huggingface", "hugging face", "transformers", "sentence-transformers"],
    "embeddings": ["embeddings", "vector embeddings"],
    "fastapi": ["fastapi", "flask", "asgi", "uvicorn", "rest api"],
    "streamlit": ["streamlit", "gradio"],
    "git": ["git", "github", "github actions", "ci/cd"],
    "rag": ["rag", "retrieval augmented generation", "retrieval-augmented"],
    "nlp": ["nlp", "natural language processing", "text processing"],
    "llm": ["llm", "llms", "large language model", "generative ai", "genai", "llama", "groq"],
    "machine learning": ["machine learning", "ml", "predictive modeling", "deep learning"],
    "monte carlo": ["monte carlo", "stochastic simulation", "poisson"],
}

# Core Target Role Keywords - Title MUST be an actual AI/ML/Data Engineering/Data Science/Data Analytics technical role
ALLOW_CORE_TITLE_TERMS = [
    "ai engineer", "ai developer", "data scientist", "machine learning engineer", "ml engineer", 
    "rag developer", "nlp engineer", "llm engineer", "data engineer", "data analyst",
    "engenheiro de inteligência artificial", "engenheiro de ia", "cientista de dados",
    "engenheiro de dados", "analista de dados", "python data engineer", "python ai developer",
    "estágio ai", "estágio data scientist", "estágio inteligência artificial",
    "generative ai engineer", "generative ai developer"
]

# Irrelevant Non-AI/Data Roles Disqualifiers (Hard Disqualification if present in title)
IRRELEVANT_ROLE_DISQUALIFIERS = [
    "php", "sap", "abap", "rpa", "blue prism", "embedded", "c++", "c/c++", "dotnet", ".net", 
    "c#", "frontend", "front-end", "front end", "ui engineer", "ux engineer", "ui/ux", "react", 
    "angular", "vue", "node.js", "wordpress", "laravel", "qa", "tester", "sysadmin", "network", 
    "cybersecurity", "cibersegurança", "salesforce", "cobol", "ios", "android", "flutter", 
    "web developer", "webmaster", "helpdesk", "support technician", "electronics engineer",
    "rf engineer", "hardware engineer", "mainframe", "devops engineer", "scrum master",
    "fullstack", "full stack", "full-stack", "java developer", "backend developer", "back end",
    "gestor de projeto", "project manager", "blockchain", "scrum master", "consultor funcional",
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
    "data entry", "introdução de dados", "introducao de dados", "entry assistant", "entry clerk"
]

# Title Disqualifiers for Senior / Lead / Level II-III / Doctorate Roles
TITLE_SENIORITY_DISQUALIFIERS = [
    "senior", "sr", "lead", "principal", "head of", "director", "architect", "staff", "vp of", "manager",
    "phd", "ph.d", "doctorate", "doutoramento", "postdoc", "post-doc", "postdoctoral", "expert", "consultor sénior",
    "responsável", "responsavel", "coordenador", "coordenadora", "diretor", "diretora", "director", "chefe",
    "head", "gestor de", "mid", "mid-level", "mid level", "mid-senior", "mid/senior", "pleno",
    " iii", " ii", " level 3", " level 2", " level iii", " level ii", " 3", " 2"
]

# Text-level Seniority Disqualifiers (Catches LinkedIn tags & description requirements)
TEXT_SENIORITY_DISQUALIFIERS = [
    "mid-senior", "mid senior", "mid-to-senior", "mid to senior", "mid-to-senior-level", "mid to senior level",
    "mid-level to senior", "mid level to senior", "seniority level mid-senior", "seniority level senior",
    "seniority level director", "seniority level executive", "technical leadership",
    "leadership experience", "experiência em liderança", "liderança técnica", "experiencia em liderança",
    "experiência profissional comprovada", "experiência comprovada", "experiencia profissional comprovada",
    "experiencia comprovada", "comprovada experiência", "comprovada experiencia",
    "proven experience", "proven track record", "experiência sólida", "experiencia sólida", "solid experience",
    "significant professional experience", "significant experience", "senior-level", "senior level",
    "senior developer", "senior engineer", "senior backend", "senior software", "senior data scientist",
    "senior data engineer", "sénior developer", "sénior engineer", "sénior backend", "sr developer", "sr engineer",
    "2+ years", "3+ years", "4+ years", "5+ years", "6+ years", "7+ years", "8+ years", "9+ years", "10+ years",
    "2+ anos", "3+ anos", "4+ anos", "5+ anos", "6+ anos", "7+ anos", "8+ anos", "9+ anos", "10+ anos",
    "2 anos de experiência", "3 anos de experiência", "4 anos de experiência", "5 anos de experiência", "6 anos de experiência", "7 anos de experiência",
    "2 years of experience", "3 years of experience", "4 years of experience", "5 years of experience", "6 years of experience", "7 years of experience"
]

# Precompiled regexes for fast disqualifier matching
# Using lookarounds (?<![a-zA-Z0-9_]) and (?![a-zA-Z0-9_]) instead of \b to properly match words with punctuation like .net or c++
def build_strict_pattern(word: str) -> re.Pattern:
    return re.compile(rf"(?<![a-zA-Z0-9_]){re.escape(word.strip())}(?![a-zA-Z0-9_])", re.IGNORECASE)

IRRELEVANT_ROLE_PATTERNS = [(disq, build_strict_pattern(disq)) for disq in IRRELEVANT_ROLE_DISQUALIFIERS]
TITLE_SENIORITY_PATTERNS = [(disq, build_strict_pattern(disq)) for disq in TITLE_SENIORITY_DISQUALIFIERS]
TEXT_SENIORITY_PATTERNS = [(disq, build_strict_pattern(disq)) for disq in TEXT_SENIORITY_DISQUALIFIERS]
YEARS_OF_EXP_PATTERN = re.compile(r"\b(?:[2-9]|1[0-9])\s*(?:to|-|a)?\s*(?:[2-9]|1[0-9])?\s*\+?\s*(?:(?:years?|anos?)\b(?:\s*(?:of|de)\s+)?(?:[a-zA-Z,\- ]{0,60})experi(?:ence|ência|encia)\b|(?:\s*(?:of|de)\s+)?experi(?:ence|ência|encia)\b)", re.IGNORECASE)
BASIC_TITLE_PATTERN = re.compile(r"(?<![a-zA-Z0-9_])(?:ai|ia|data|ml|machine\s+learning|inteligência|inteligencia|dados)(?![a-zA-Z0-9_])", re.IGNORECASE)

# Titles with just 'python' need a secondary AI/Data context check in the description
PYTHON_ONLY_TITLE_PATTERN = re.compile(r"\bpython\b", re.IGNORECASE)
AI_DATA_CONTEXT_IN_DESC = re.compile(r"\b(?:data|ai|ia|machine\s*learning|ml|nlp|llm|deep\s*learning|analytics|dados|ciência\s*de\s*dados|inteligência\s*artificial|rag|embeddings|genai|generative)\b", re.IGNORECASE)

# Disqualify jobs requiring PhD / Doctorate
PHD_REQUIREMENT_PATTERN = re.compile(
    r"\b(?:phd|ph\.d|doctorate|doutoramento|postdoc|post-doc|postdoctoral)\b",
    re.IGNORECASE
)


# Mandatory Non-English/Portuguese Language Requirements Pattern
MANDATORY_OTHER_LANGUAGES_PATTERN = re.compile(
    r"\b(?:native|fluent|fluency\s+in|proficiency\s+in|proficient\s+in|spoken|speaking|must\s+speak|knowledge\s+of)\s+(?:both\s+)?(?:german|deutsch|french|français|francais|spanish|español|espanhol|dutch|nederlands|italian|italiano)\b|"
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

        # 0.0 Description Integrity & Completeness Check
        clean_desc = job.description.strip()
        clean_desc_lower = clean_desc.lower()
        incomplete_indicators = [
            "join or sign in to find your next job",
            "sign in to view",
            "sign in to apply",
            "log in to view",
            "faça login",
            "entre para ver",
            "registar para ver",
            "crie uma conta",
            "sign in to see more"
        ]
        
        # Se a descrição tiver menos de 100 caracteres, é porque o scraper falhou 
        # (ex: timeout) e só conseguiu extrair o título da vaga. É impossível 
        # determinar a senioridade sem o corpo do anúncio.
        if len(clean_desc) < 100 or any(ind in clean_desc_lower for ind in incomplete_indicators):
            return ScoredJob(job=job, score=0.0, matched_skills=[], missing_skills=[], seniority_status="Descrição Incompleta / Bloqueada", match_reason="Descrição indisponível, bloqueada ou demasiado curta (falha na extração)")

        # 0.0 Expired Job Check (Text level)
        clean_desc_lower = clean_desc.lower()
        if any(exp_term in clean_desc_lower for exp_term in ["oferta expirada", "vaga expirada", "anúncio expirado", "job no longer available", "no longer accepting applications", "this job is no longer available"]):
            return ScoredJob(job=job, score=0.0, matched_skills=[], missing_skills=[], seniority_status="Oferta Expirada", match_reason="Anúncio marcado como expirado no portal")

        # 0. Freshness Filter (Max 24 hours / 1 day old)
        today = datetime.date.today()
        job_date = parse_job_date(job.pub_date)
        days_old = (today - job_date).days
        if days_old > 1:
            return ScoredJob(job=job, score=0.0, matched_skills=[], missing_skills=[], seniority_status="Vaga Antiga (> 24h)", match_reason="Oferta expirada (> 24h)")

        # 1. Location & Work Mode Filter (STRICT)
        # If job is outside Portugal, it MUST BE 100% REMOTO! Foreign On-site/Hybrid is REJECTED!
        is_portugal = any(loc in location_lower for loc in ["portugal", "lisboa", "lisbon", "porto", "coimbra", "braga", "castelo branco", "aveiro", "leiria", "faro"])
        is_strictly_remote = (work_mode_lower == "remoto") or ("remoto" in location_lower) or ("remote" in location_lower) or ("teletrabalho" in location_lower)

        if not is_portugal and not is_strictly_remote:
            return ScoredJob(job=job, score=0.0, matched_skills=[], missing_skills=[], seniority_status="Fora do Âmbito Geográfico", match_reason="Presencial/Híbrido no Estrangeiro")

        # 2. Strict Irrelevant Role Disqualification
        for disq, pattern in IRRELEVANT_ROLE_PATTERNS:
            if pattern.search(title_lower):
                return ScoredJob(job=job, score=0.0, matched_skills=[], missing_skills=[], seniority_status="Cargo Irrelevante", match_reason=f"Título desqualificado por conter '{disq}'")

        # Check text-level Kids / Teaching / Tutoring disqualifier
        if any(k in text for k in ["crianças", "criancas", "adolescentes", "pós-letivo", "pos-letivo", "sharkcoders"]):
            return ScoredJob(job=job, score=0.0, matched_skills=[], missing_skills=[], seniority_status="Ensino Infantil / Tutoria", match_reason="Ensino de programação/IA a crianças/adolescentes")

        # 3. Mandatory AI & Data Science Core Domain Check
        has_core_title = any(ct in title_lower for ct in ALLOW_CORE_TITLE_TERMS)
        if not has_core_title:
            has_basic_ai_data_title = BASIC_TITLE_PATTERN.search(title_lower)
            has_python_title = PYTHON_ONLY_TITLE_PATTERN.search(title_lower)
            
            if has_basic_ai_data_title:
                pass  # Title contains AI/Data/ML terms — proceed
            elif has_python_title:
                # 'Python' alone in title is too generic — only allow if description has AI/Data context
                if not AI_DATA_CONTEXT_IN_DESC.search(text):
                    return ScoredJob(job=job, score=0.0, matched_skills=[], missing_skills=[], seniority_status="Python Genérico (Sem Contexto AI/Data)", match_reason="Título 'Python Developer' sem contexto de AI, ML ou Data Science na descrição")
            else:
                return ScoredJob(job=job, score=0.0, matched_skills=[], missing_skills=[], seniority_status="Fora de AI/Data Science", match_reason="Título não se enquadra em AI, ML ou Data Science")

        # 4. PhD / Doctorate Degree Requirement Disqualification
        if PHD_REQUIREMENT_PATTERN.search(title_lower) or PHD_REQUIREMENT_PATTERN.search(text):
            return ScoredJob(job=job, score=0.0, matched_skills=[], missing_skills=[], seniority_status="Requer Doutoramento", match_reason="Exige PhD ou Doutoramento")

        # 5. Foreign Language Requirement Disqualification
        if MANDATORY_OTHER_LANGUAGES_PATTERN.search(text) or FOREIGN_JOB_POST_PATTERN.search(text):
            return ScoredJob(job=job, score=0.0, matched_skills=[], missing_skills=[], seniority_status="Idioma Não Suportado", match_reason="Exige Alemão/Francês/Espanhol obrigatório")

        # 6. Seniority & Experience Disqualification (STRICT: MAX 0-1 YEAR EXP & NO SENIOR TITLES)
        is_explicit_junior = any(j_term in title_lower for j_term in ["junior", "jr", "estágio", "estagio", "trainee", "graduate", "entry level", "intern"])
        is_explicit_zero_to_one = any(b in text for b in ["recém-licenciado", "recem licenciado", "0-1", " graduate", "0 a 1 ano", "0 to 1 year"])
        has_verified_junior_indicator = is_explicit_junior or job.iefp_mentioned or is_explicit_zero_to_one

        # Check Senior Title Disqualifiers (Senior, Sr, Lead, Principal, III, Level 3, Manager, etc.)
        for disq, pattern in TITLE_SENIORITY_PATTERNS:
            if pattern.search(title_lower):
                return ScoredJob(job=job, score=0.0, matched_skills=[], missing_skills=[], seniority_status="Sénior / Liderança / Nível Avançado", match_reason=f"Título sénior ({disq})")

        # Check Text-level Seniority Disqualifiers (LinkedIn Mid-Senior tags, Technical Leadership, etc.)
        for disq, pattern in TEXT_SENIORITY_PATTERNS:
            if pattern.search(text):
                return ScoredJob(job=job, score=0.0, matched_skills=[], missing_skills=[], seniority_status="Nível Mid-Senior / Liderança", match_reason=f"Descrição ou tag exige nível avançado ({disq})")
                
        # Regex for generic X+ years of experience
        exp_match = YEARS_OF_EXP_PATTERN.search(text)
        if exp_match:
            return ScoredJob(job=job, score=0.0, matched_skills=[], missing_skills=[], seniority_status="Requer Experiência", match_reason=f"Requer experiência ({exp_match.group(0).strip()})")


        # -------------------------------------------------------------
        # PHASE 2: WEIGHTED SCORING SYSTEM (0.0 to 100.0)
        # -------------------------------------------------------------

        # A. Target Role Title Base Score (Max 40.0 pts)
        title_score = 0.0
        exact_ai_data_targets = [
            "junior ai engineer", "ai engineer", "junior data scientist", "data scientist", 
            "junior ml engineer", "machine learning engineer", "rag developer", "nlp engineer", 
            "llm engineer", "junior data engineer", "data engineer", "inteligência artificial", "ciência de dados"
        ]
        
        if any(t in title_lower for t in exact_ai_data_targets):
            title_score = 40.0
        elif any(t in title_lower for t in ["data", "ai", "ia", "python"]):
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
        matched_skills: List[str] = []
        for canonical_skill, aliases in SKILL_ALIASES.items():
            for alias in aliases:
                escaped = re.escape(alias)
                prefix = r"\b" if alias[0].isalnum() else ""
                suffix = r"\b" if alias[-1].isalnum() else ""
                pattern = rf"{prefix}{escaped}{suffix}"
                if re.search(pattern, text, re.IGNORECASE):
                    matched_skills.append(canonical_skill)
                    break

        tech_score = min(15.0, len(matched_skills) * 3.0)
        if len(matched_skills) == 0:
            tech_score = -15.0  # Heavy penalty for roles that lack any technical AI/Data keywords

        # Final Combined Score Calculation
        raw_score = title_score + booster_score + location_score + tech_score

        # MODERATE MODE RULE (Option 2):
        # 1. Verified Junior / IEFP / 0-1 year roles can reach Destaque (>=75.0%, up to 100.0%)
        # 2. Unverified General Roles (e.g. AI Engineer, Data Scientist) are capped at 65.0% MAX -> appear in "Promissoras (55-74%)" with warning tag
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
            match_reason=f"Vaga de {job.title} adequada para perfil Júnior em Tecnologia/IA"
        )

    def process_jobs(self, jobs: List[Job]) -> List[ScoredJob]:
        # Stage 1: Fast Heuristic Pre-filter
        heuristic_candidates: List[ScoredJob] = []
        for job in jobs:
            evaluated = self.evaluate_job(job)
            if evaluated.score >= 55.0:
                heuristic_candidates.append(evaluated)

        if not heuristic_candidates:
            return []

        # Stage 2: Batch AI Evaluation (if enabled and available)
        if self.ai_evaluator and self.ai_evaluator.is_available:
            candidate_jobs = [sj.job for sj in heuristic_candidates]
            # Reduce batch size to 2 to minimize payload size and avoid triggering Groq TPM limits
            ai_results = self.ai_evaluator.evaluate_jobs_batch(candidate_jobs, self.profile, batch_size=2)

            final_scored_jobs: List[ScoredJob] = []
            for sj in heuristic_candidates:
                ai_res = ai_results.get(sj.job.job_id)
                if ai_res:
                    reason_lower = ai_res.reasoning.lower()
                    seniority_det_lower = (ai_res.seniority_detected or "").lower()
                    is_non_junior = any(s in seniority_det_lower for s in ["mid", "senior", "sénior", "lead", "pleno", "avançado", "director", "executive"])
                    if not ai_res.is_suitable or is_non_junior or ("exige" in reason_lower and ("2 anos" in reason_lower or "3 anos" in reason_lower or "superior a" in reason_lower)):
                        sj.score = 0.0
                        sj.seniority_status = f"Rejeitada por IA ({ai_res.seniority_detected})"
                        sj.match_reason = ai_res.reasoning
                        continue

                    blended_score = round(0.5 * sj.score + 0.5 * ai_res.fit_score, 1)
                    sj.score = blended_score
                    sj.ai_evaluated = True
                    sj.ai_reasoning = ai_res.reasoning
                    if ai_res.seniority_detected and ai_res.seniority_detected != "Desconhecido":
                        sj.seniority_status = ai_res.seniority_detected
                    sj.ai_pros = ai_res.pros
                    sj.ai_cons = ai_res.cons
                    final_scored_jobs.append(sj)
                else:
                    # Fallback if AI batch didn't return result for this candidate (e.g., rate limit or API crash)
                    text_c = f"{sj.job.title} {sj.job.description}".lower()
                    if "iefp" in text_c or "ativar.pt" in text_c:
                        sj.seniority_status = "Elegível IEFP (Avaliado s/ IA)"
                    elif "estágio" in text_c or "estagio" in text_c or "trainee" in text_c:
                        sj.seniority_status = "Estágio (Avaliado s/ IA)"
                    elif "recém-licenciado" in text_c or "recem-licenciado" in text_c or "0-1" in text_c:
                        sj.seniority_status = "Recém-Licenciado (Avaliado s/ IA)"
                    else:
                        sj.seniority_status = "Júnior Potencial (Avaliado s/ IA)"

                    if not sj.ai_reasoning:
                        sj.ai_reasoning = f"⚠️ [Falha IA] Avaliada por heurística: Vaga adequada para perfil Júnior"
                    final_scored_jobs.append(sj)

            final_scored_jobs.sort(key=lambda x: x.score, reverse=True)
            return final_scored_jobs

        # Fallback if AI not available
        heuristic_candidates.sort(key=lambda x: x.score, reverse=True)
        return heuristic_candidates


