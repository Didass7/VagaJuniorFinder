import re
import datetime
import email.utils
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from config import CandidateProfile, config
from scraper import Job
from ai_evaluator import AIEvaluator, AIEvaluationResult

# Irrelevant Non-Target Roles Disqualifiers (Hard Disqualification if present in title)
# Removed: "network", "cybersecurity", "cibersegurança", "devops engineer", "sysadmin"
IRRELEVANT_ROLE_DISQUALIFIERS = [
    "php", "sap", "abap", "rpa", "blue prism", "embedded", "c++", "c/c++", "dotnet", ".net", 
    "c#", "frontend", "front-end", "front end", "ui engineer", "ux engineer", "ui/ux", "react", 
    "angular", "vue", "node.js", "wordpress", "laravel", "qa", "tester", "salesforce", "cobol", 
    "ios", "android", "flutter", "web developer", "webmaster", "helpdesk", "support technician", 
    "electronics engineer", "rf engineer", "hardware engineer", "mainframe", "scrum master",
    "fullstack", "full stack", "full-stack", "java developer", "backend developer", "back end",
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
    "+2 years", "+3 years", "+4 years", "+5 years", "+6 years", "+7 years", "+8 years", "+9 years", "+10 years",
    "2+ anos", "3+ anos", "4+ anos", "5+ anos", "6+ anos", "7+ anos", "8+ anos", "9+ anos", "10+ anos",
    "+2 anos", "+3 anos", "+4 anos", "+5 anos", "+6 anos", "+7 anos", "+8+ anos", "+9 anos", "+10 anos",
    "2 anos de experiência", "3 anos de experiência", "4 anos de experiência", "5 anos de experiência", "6 anos de experiência", "7 anos de experiência",
    "2 years of experience", "3 years of experience", "4 years of experience", "5 years of experience", "6 years of experience", "7 years of experience"
]

# Precompiled regexes for fast disqualifier matching
def build_strict_pattern(word: str) -> re.Pattern:
    return re.compile(rf"(?<![a-zA-Z0-9_]){re.escape(word.strip())}(?![a-zA-Z0-9_])", re.IGNORECASE)

IRRELEVANT_ROLE_PATTERNS = [(disq, build_strict_pattern(disq)) for disq in IRRELEVANT_ROLE_DISQUALIFIERS]
TITLE_SENIORITY_PATTERNS = [(disq, build_strict_pattern(disq)) for disq in TITLE_SENIORITY_DISQUALIFIERS]
TEXT_SENIORITY_PATTERNS = [(disq, build_strict_pattern(disq)) for disq in TEXT_SENIORITY_DISQUALIFIERS]
YEARS_OF_EXP_PATTERN = re.compile(r"\b(?:[2-9]|1[0-9]|two|three|four|five|six|seven|eight|nine|ten|dois|três|tres|quatro|cinco|seis|sete|oito|nove|dez)\s*(?:to|-|a)?\s*(?:[2-9]|1[0-9]|two|three|four|five|six|seven|eight|nine|ten|dois|três|tres|quatro|cinco|seis|sete|oito|nove|dez)?\s*\+?\s*(?:(?:years?|anos?)\b(?:\s*(?:of|de)\s+)?(?:[\s\S]{0,60})experi(?:ence|ência|encia)\b|(?:\s*(?:of|de)\s+)?experi(?:ence|ência|encia)\b)|(?:\bexperi(?:ence|ência|encia)\b[\s\S]{0,40}\b(?:[2-9]|1[0-9]|two|three|four|five|six|seven|eight|nine|ten|dois|três|tres|quatro|cinco|seis|sete|oito|nove|dez)\s*\+?\s*(?:years?|anos?)\b)", re.IGNORECASE)

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

# Geo-Restricted Remote Pattern (e.g. US/UK only)
GEO_RESTRICTED_REMOTE_PATTERN = re.compile(
    r"\b(?:based\s+in\s+(?:the\s+)?(?:us|united\s+states|usa|uk|united\s+kingdom)|legally\s+authorized\s+to\s+work\s+in\s+(?:the\s+)?(?:us|united\s+states|usa|uk|united\s+kingdom)|work\s+from\s+anywhere\s+in\s+(?:the\s+)?(?:us|united\s+states|usa|uk|united\s+kingdom)|(?:us|uk)\s+residents\s+only|only\s+open\s+to\s+(?:us|uk)\s+candidates|right\s+to\s+work\s+in\s+(?:the\s+)?(?:us|uk|united\s+states|united\s+kingdom)|located\s+in\s+(?:the\s+)?(?:us|usa|united\s+states|uk|united\s+kingdom))\b",
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
            return ScoredJob(job=job, score=0.0, matched_skills=[], missing_skills=[], seniority_status="Descrição Incompleta / Bloqueada", match_reason="Descrição indisponível")

        if any(exp_term in clean_desc_lower for exp_term in ["oferta expirada", "vaga expirada", "anúncio expirado", "job no longer available", "no longer accepting applications", "this job is no longer available"]):
            return ScoredJob(job=job, score=0.0, matched_skills=[], missing_skills=[], seniority_status="Oferta Expirada", match_reason="Anúncio marcado como expirado")

        today = datetime.date.today()
        job_date = parse_job_date(job.pub_date)
        if (today - job_date).days > 14:
            return ScoredJob(job=job, score=0.0, matched_skills=[], missing_skills=[], seniority_status="Vaga Antiga (> 14 dias)", match_reason="Oferta expirada (> 14 dias)")

        is_portugal = any(loc in location_lower for loc in ["portugal", "lisboa", "lisbon", "porto", "coimbra", "braga", "castelo branco", "aveiro", "leiria", "faro"])
        is_strictly_remote = (work_mode_lower == "remoto") or ("remoto" in location_lower) or ("remote" in location_lower) or ("teletrabalho" in location_lower)

        if not is_portugal and not is_strictly_remote:
            return ScoredJob(job=job, score=0.0, matched_skills=[], missing_skills=[], seniority_status="Fora do Âmbito Geográfico", match_reason="Presencial/Híbrido no Estrangeiro")

        if is_strictly_remote and GEO_RESTRICTED_REMOTE_PATTERN.search(text):
            return ScoredJob(job=job, score=0.0, matched_skills=[], missing_skills=[], seniority_status="Remoto Geobloqueado", match_reason="Vaga remota mas restrita")

        for disq, pattern in IRRELEVANT_ROLE_PATTERNS:
            if pattern.search(title_lower):
                return ScoredJob(job=job, score=0.0, matched_skills=[], missing_skills=[], seniority_status="Cargo Irrelevante", match_reason=f"Título desqualificado por conter '{disq}'")

        if any(k in text for k in ["crianças", "criancas", "adolescentes", "pós-letivo", "pos-letivo", "sharkcoders"]):
            return ScoredJob(job=job, score=0.0, matched_skills=[], missing_skills=[], seniority_status="Ensino Infantil", match_reason="Ensino de crianças/adolescentes")

        # Dynamic Core Domain Check based on profile's target titles and tech stack
        target_titles_lower = [t.lower() for t in self.profile.target_titles]
        tech_stack_lower = [t.lower() for t in self.profile.tech_stack]
        
        # We consider a job relevant if the title contains ANY of the target titles,
        # OR if it contains ANY of the tech stack keywords.
        has_target_title = any(tt in title_lower for tt in target_titles_lower)
        has_tech_in_title = any(ts in title_lower for ts in tech_stack_lower)
        
        if not has_target_title and not has_tech_in_title:
            return ScoredJob(job=job, score=0.0, matched_skills=[], missing_skills=[], seniority_status="Fora do Perfil", match_reason="Título não corresponde às funções ou tecnologias alvo do candidato")

        if PHD_REQUIREMENT_PATTERN.search(title_lower) or PHD_REQUIREMENT_PATTERN.search(text):
            return ScoredJob(job=job, score=0.0, matched_skills=[], missing_skills=[], seniority_status="Requer Doutoramento", match_reason="Exige PhD ou Doutoramento")

        if MANDATORY_OTHER_LANGUAGES_PATTERN.search(text) or FOREIGN_JOB_POST_PATTERN.search(text):
            return ScoredJob(job=job, score=0.0, matched_skills=[], missing_skills=[], seniority_status="Idioma Não Suportado", match_reason="Exige outro idioma nativo/fluente")

        is_explicit_junior = any(j_term in title_lower for j_term in ["junior", "jr", "estágio", "estagio", "trainee", "graduate", "entry level", "intern"])
        is_explicit_zero_to_one = any(b in text for b in ["recém-licenciado", "recem licenciado", "0-1", " graduate", "0 a 1 ano", "0 to 1 year"])
        has_verified_junior_indicator = is_explicit_junior or job.iefp_mentioned or is_explicit_zero_to_one

        for disq, pattern in TITLE_SENIORITY_PATTERNS:
            if pattern.search(title_lower):
                return ScoredJob(job=job, score=0.0, matched_skills=[], missing_skills=[], seniority_status="Sénior / Liderança", match_reason=f"Título sénior ({disq})")

        for disq, pattern in TEXT_SENIORITY_PATTERNS:
            if pattern.search(text):
                return ScoredJob(job=job, score=0.0, matched_skills=[], missing_skills=[], seniority_status="Nível Mid-Senior / Liderança", match_reason=f"Descrição exige nível avançado ({disq})")
                
        exp_match = YEARS_OF_EXP_PATTERN.search(text)
        if exp_match:
            return ScoredJob(job=job, score=0.0, matched_skills=[], missing_skills=[], seniority_status="Requer Experiência", match_reason=f"Requer experiência ({exp_match.group(0).strip()})")


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
            tech_score = -15.0  # Heavy penalty for roles that lack any of the candidate's skills

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
            match_reason=f"Vaga avaliada com base nas preferências dinâmicas do perfil"
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

        # Stage 2: Batch AI Evaluation
        if self.ai_evaluator and self.ai_evaluator.is_available:
            candidate_jobs = [sj.job for sj in heuristic_candidates]
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

        heuristic_candidates.sort(key=lambda x: x.score, reverse=True)
        return heuristic_candidates
