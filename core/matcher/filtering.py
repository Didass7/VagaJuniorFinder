import datetime
from typing import Optional

from scrapers import Job
from core.config import CandidateProfile
from core.matcher.scoring import ScoredJob
from core.matcher.rules import (
    COMPANY_HISTORY_PATTERN, PORTUGAL_LOCATIONS, GEO_RESTRICTED_REMOTE_PATTERN, 
    CROWDSOURCING_MICROTASKS_PATTERN, SENIOR_COMPENSATION_PATTERN,
    IRRELEVANT_ROLE_PATTERNS, PHD_REQUIREMENT_PATTERN, MANDATORY_OTHER_LANGUAGES_PATTERN,
    FOREIGN_JOB_POST_PATTERN, ZERO_EXP_INDICATOR_PATTERN, TITLE_SENIORITY_PATTERNS,
    ADVANCED_EXP_HARD_DISQUALIFIERS_PATTERN, TEXT_SENIORITY_PATTERNS, YEARS_OF_EXP_PATTERN,
    parse_job_date
)

def check_hard_disqualifiers(job: Job, profile: CandidateProfile, text: str, clean_desc_lower: str, title_lower: str, location_lower: str, work_mode_lower: str, is_portugal: bool, is_strictly_remote: bool, has_target_title: bool, has_tech_in_title: bool) -> Optional[ScoredJob]:
    incomplete_indicators = [
        "join or sign in to find your next job",
        "sign in to view", "sign in to apply", "log in to view", "faça login",
        "entre para ver", "registar para ver", "crie uma conta", "sign in to see more",
        "oportunidade de emprego publicada no linkedin",
        "oportunidade de emprego publicada no linkedin jobs"
    ]
    
    clean_desc = COMPANY_HISTORY_PATTERN.sub(" ", job.description).strip()
    if len(clean_desc) < 100 or any(ind in clean_desc_lower for ind in incomplete_indicators):
        return ScoredJob(job=job, score=0.0, matched_skills=[], missing_skills=[], seniority_status="Descrição Incompleta / Bloqueada", match_reason="Descrição indisponível", ai_reasoning="Filtro Automático: Descrição indisponível ou protegida por login")

    if any(exp_term in clean_desc_lower for exp_term in ["oferta expirada", "vaga expirada", "anúncio expirado", "job no longer available", "no longer accepting applications", "this job is no longer available"]):
        return ScoredJob(job=job, score=0.0, matched_skills=[], missing_skills=[], seniority_status="Oferta Expirada", match_reason="Anúncio marcado como expirado", ai_reasoning="Filtro Automático: Anúncio de vaga já expirado")

    today = datetime.date.today()
    job_date = parse_job_date(job.pub_date)
    if (today - job_date).days > 14:
        return ScoredJob(job=job, score=0.0, matched_skills=[], missing_skills=[], seniority_status="Vaga Antiga (> 14 dias)", match_reason="Oferta expirada (> 14 dias)", ai_reasoning="Filtro Automático: Publicada há mais de 14 dias")

    if not is_portugal and not is_strictly_remote:
        return ScoredJob(job=job, score=0.0, matched_skills=[], missing_skills=[], seniority_status="Fora do Âmbito Geográfico", match_reason="Presencial/Híbrido no Estrangeiro", ai_reasoning="Filtro Automático: Vaga presencial/híbrida no estrangeiro")

    geo_match = GEO_RESTRICTED_REMOTE_PATTERN.search(text)
    if is_strictly_remote and geo_match:
        return ScoredJob(job=job, score=0.0, matched_skills=[], missing_skills=[], seniority_status="Remoto Geobloqueado", match_reason=f"Vaga remota restrita ({geo_match.group(0).strip()})", ai_reasoning=f"Filtro Automático: Vaga remota com restrição geográfica a outros países ({geo_match.group(0).strip()})")

    crowd_match = CROWDSOURCING_MICROTASKS_PATTERN.search(text)
    if crowd_match:
        return ScoredJob(job=job, score=0.0, matched_skills=[], missing_skills=[], seniority_status="Microtarefas / Crowdsourcing", match_reason=f"Oportunidade de crowdsourcing/microtarefas ({crowd_match.group(0).strip()})", ai_reasoning=f"Filtro Automático: Microtarefas/Crowdsourcing não elegível como emprego formal ({crowd_match.group(0).strip()})")

    comp_match = SENIOR_COMPENSATION_PATTERN.search(text)
    if comp_match:
        return ScoredJob(job=job, score=0.0, matched_skills=[], missing_skills=[], seniority_status="Remuneração Sénior/Staff", match_reason=f"Faixa salarial de nível sénior/staff ({comp_match.group(0).strip()})", ai_reasoning=f"Filtro Automático: Faixa salarial de nível Sénior/Staff ({comp_match.group(0).strip()})")

    target_titles_lower = [t.lower() for t in profile.target_titles]
    tech_stack_lower = [t.lower() for t in profile.tech_stack]
    profile_languages = [l.lower() for l in profile.languages]
    speaks_spanish = any("espanhol" in l or "spanish" in l for l in profile_languages)
    speaks_french = any("francês" in l or "frances" in l or "french" in l for l in profile_languages)
    speaks_german = any("alemão" in l or "alemao" in l or "german" in l or "deutsch" in l for l in profile_languages)
    speaks_italian = any("italiano" in l or "italian" in l for l in profile_languages)
    speaks_dutch = any("holandês" in l or "holandes" in l or "dutch" in l or "nederlands" in l for l in profile_languages)

    for disq, pattern in IRRELEVANT_ROLE_PATTERNS:
        if any(disq in tt for tt in target_titles_lower) or any(disq in ts for ts in tech_stack_lower):
            continue
        if pattern.search(title_lower):
            return ScoredJob(job=job, score=0.0, matched_skills=[], missing_skills=[], seniority_status="Cargo Irrelevante", match_reason=f"Título desqualificado por conter '{disq}'", ai_reasoning=f"Filtro Automático: Cargo irrelevante ({disq})")

    if any(k in text for k in ["crianças", "criancas", "adolescentes", "pós-letivo", "pos-letivo", "sharkcoders"]):
        return ScoredJob(job=job, score=0.0, matched_skills=[], missing_skills=[], seniority_status="Ensino Infantil", match_reason="Ensino de crianças/adolescentes", ai_reasoning="Filtro Automático: Ensino de crianças/adolescentes")

    import re
    core_domain_words = {
        "estágio", "estagio", "intern", "internship", "trainee", "iefp", "ativar",
        "developer", "software", "programador", "desenvolvedor", "consultor", "consultant",
        "graduate", "fellowship", "bolsa", "investigador", "engenharia", "engineering",
        "informática", "informatica", "junior", "júnior", "tech", "tecnologia"
    }
    for tt in target_titles_lower:
        for w in tt.split():
            if len(w) >= 3 and w not in ["engineer", "analyst", "engenheiro", "analista", "técnico", "tecnico"]:
                core_domain_words.add(w)
    for ts in tech_stack_lower:
        for w in ts.split():
            if len(w) >= 3:
                core_domain_words.add(w)

    has_it_role = bool(re.search(r"\b(?:it|ti)\b", title_lower)) and bool(re.search(r"\b(?:junior|júnior|trainee|graduate|consultor|consultant|developer|support|suporte|estagio|estágio)\b", title_lower))
    has_domain_in_title = any(cd in title_lower for cd in core_domain_words) or has_it_role

    DOMAIN_CLUSTERS = {
        "data_ai": [
            "data engineer", "data scientist", "cientista de dados", "bi analyst", "analista de bi", "data architect",
            "ai engineer", "engenheiro de ia", "machine learning", "computer vision", "nlp engineer"
        ],
        "security_network": [
            "cybersecurity", "cibersegurança", "network engineer", "soc analyst", "sysadmin", "analista de soc",
            "técnico de redes", "administrador de redes", "administrador de sistemas", "devops engineer", "secops"
        ],
        "frontend_design": [
            "frontend developer", "front-end developer", "ui developer", "ux developer", "react developer",
            "angular developer", "vue developer", "web designer", "ui/ux designer"
        ],
        "mobile": [
            "ios developer", "android developer", "flutter developer", "mobile developer",
            "react native developer", "swift developer", "kotlin developer"
        ],
    }

    target_titles_str = " ".join(target_titles_lower)
    profile_domains = set()
    for domain, terms in DOMAIN_CLUSTERS.items():
        if any(term in target_titles_str for term in terms):
            profile_domains.add(domain)

    if profile_domains:
        for domain, terms in DOMAIN_CLUSTERS.items():
            if domain not in profile_domains:
                if any(term in title_lower for term in terms):
                    return ScoredJob(
                        job=job, score=0.0, matched_skills=[], missing_skills=[],
                        seniority_status="Fora do Perfil",
                        match_reason=f"Vaga de domínio '{domain}' fora do perfil do candidato",
                        ai_reasoning=f"Filtro Automático: Cargo fora do domínio do candidato"
                    )

    if not has_domain_in_title and not has_target_title and not has_tech_in_title:
        return ScoredJob(job=job, score=0.0, matched_skills=[], missing_skills=[], seniority_status="Fora do Perfil", match_reason="Título não corresponde às funções ou tecnologias alvo do candidato", ai_reasoning="Filtro Automático: Título não corresponde às funções alvo do candidato")

    if PHD_REQUIREMENT_PATTERN.search(title_lower) or PHD_REQUIREMENT_PATTERN.search(text):
        return ScoredJob(job=job, score=0.0, matched_skills=[], missing_skills=[], seniority_status="Requer Doutoramento", match_reason="Exige PhD ou Doutoramento", ai_reasoning="Filtro Automático: Exige Doutoramento (PhD)")

    candidate_degree = getattr(profile, 'degree', '').lower()
    has_masters = "mestrado" in candidate_degree or "master" in candidate_degree
    if not has_masters:
        has_bachelor_option = bool(re.search(r"\b(?:licenciatura|licenciad[oa]s?|bachelor'?s?|bsc)\b", text))
        masters_pattern = re.compile(
            r"\b(?:habilita[cç][aã]o\s+base\s*:\s*mestrado|n[ií]vel\s+7\b|exige\s+mestrado|mestrado\s+(?:obrigat[oó]rio|completo|exigido))\b|"
            r"\b(?:qualifica[cç][oõ]es\s+(?:acad[eé]micas?|m[ií]nimas?)?|requisitos\s+acad[eé]micos?|forma[cç][aã]o\s+(?:acad[eé]mica|base)?|perfil)\s*:\s*mestrado\b|"
            r"\bqualifica[cç][oõ]es\s+acad[eé]micas\s+mestrado\b|"
            r"\bmaster'?s?\s+degree\s+(?:in\s+[\w\s]+)?required\b|"
            r"\bmsc\s+(?:in\s+[\w\s]+)?required\b",
            re.IGNORECASE
        )
        masters_preferred_pattern = re.compile(
            r"\b(?:valoriza-se|prefer[ií]vel|preferência|preferencia|preferred|nice\s+to\s+have|desejável|desejavel|factor\s+prefer|fator\s+prefer|valorizamos|valorizado|valorizada|diferencial|plus|asset|bonus|advantage)\b",
            re.IGNORECASE
        )
        masters_match = masters_pattern.search(text)
        if masters_match and not has_bachelor_option:
            match_start = max(0, masters_match.start() - 80)
            match_end = min(len(text), masters_match.end() + 40)
            surrounding_text = text[match_start:match_end]
            if not masters_preferred_pattern.search(surrounding_text):
                return ScoredJob(job=job, score=0.0, matched_skills=[], missing_skills=[], seniority_status="Requer Mestrado", match_reason=f"Oferta exige Mestrado ({masters_match.group(0).strip()}), incompatível com Licenciatura", ai_reasoning=f"Filtro Automático: Exige Mestrado ({masters_match.group(0).strip()})")

    lang_match = MANDATORY_OTHER_LANGUAGES_PATTERN.search(text)
    if lang_match:
        matched_str = lang_match.group(0).lower()
        is_exempted = (
            (speaks_spanish and any(sp in matched_str for sp in ["spanish", "español", "espanhol"])) or
            (speaks_french and any(fr in matched_str for fr in ["french", "français", "francais"])) or
            (speaks_german and any(de in matched_str for de in ["german", "deutsch", "alemão", "alemao"])) or
            (speaks_italian and any(it in matched_str for it in ["italian", "italiano"])) or
            (speaks_dutch and any(nl in matched_str for nl in ["dutch", "nederlands", "holandês", "holandes"]))
        )
        if not is_exempted:
            return ScoredJob(job=job, score=0.0, matched_skills=[], missing_skills=[], seniority_status="Idioma Não Suportado", match_reason=f"Exige outro idioma ({matched_str})", ai_reasoning=f"Filtro Automático: Exige outro idioma ({matched_str})")

    foreign_post_match = FOREIGN_JOB_POST_PATTERN.search(text)
    if foreign_post_match:
        matched_post = foreign_post_match.group(0).lower()
        is_spanish_post = any(sp in matched_post for sp in ["sobre nosotros", "buscamos", "tus funciones", "tu perfil", "requisitos del puesto"])
        is_french_post = any(fr in matched_post for fr in ["à propos de nous", "nous recherchons", "vos missions", "votre profil"])
        is_german_post = any(de in matched_post for de in ["über uns", "wir suchen", "deine aufgaben", "dein profil", "wir bieten", "bewirb dich"])
        is_exempted_post = (
            (speaks_spanish and is_spanish_post) or
            (speaks_french and is_french_post) or
            (speaks_german and is_german_post)
        )
        if not is_exempted_post:
            return ScoredJob(job=job, score=0.0, matched_skills=[], missing_skills=[], seniority_status="Idioma Não Suportado", match_reason=f"Anúncio noutro idioma ({matched_post})", ai_reasoning=f"Filtro Automático: Anúncio noutro idioma ({matched_post})")

    is_explicit_zero_exp = (
        bool(ZERO_EXP_INDICATOR_PATTERN.search(text))
        or job.iefp_mentioned
        or any(t in title_lower for t in ["estágio", "estagio", "trainee", "recém-licenciado", "recem-licenciado", "junior", "júnior", "entry level", "entry-level", "graduate", "bolsa", "fellowship"])
    )

    for disq, pattern in TITLE_SENIORITY_PATTERNS:
        if pattern.search(title_lower):
            return ScoredJob(job=job, score=0.0, matched_skills=[], missing_skills=[], seniority_status="Sénior / Liderança", match_reason=f"Título sénior ({disq})", ai_reasoning=f"Filtro Automático: Título sénior ({disq})")

    adv_exp_match = ADVANCED_EXP_HARD_DISQUALIFIERS_PATTERN.search(text)
    if adv_exp_match:
        return ScoredJob(
            job=job, score=0.0, matched_skills=[], missing_skills=[],
            seniority_status="Requer Experiência (>0 anos)",
            match_reason=f"Exige experiência sénior ({adv_exp_match.group(0).strip()})",
            ai_reasoning=f"Filtro Automático: Exige experiência sénior ({adv_exp_match.group(0).strip()})"
        )

    if not is_explicit_zero_exp:
        for disq, pattern in TEXT_SENIORITY_PATTERNS:
            if pattern.search(text):
                return ScoredJob(job=job, score=0.0, matched_skills=[], missing_skills=[], seniority_status="Requer Experiência (>0 anos)", match_reason=f"Exige experiência prévia ({disq})", ai_reasoning=f"Filtro Automático: Exige experiência prévia ({disq})")
                
        exp_match = YEARS_OF_EXP_PATTERN.search(text)
        if exp_match:
            return ScoredJob(job=job, score=0.0, matched_skills=[], missing_skills=[], seniority_status="Requer Experiência (>0 anos)", match_reason=f"Exige experiência prévia ({exp_match.group(0).strip()})", ai_reasoning=f"Filtro Automático: Exige experiência prévia ({exp_match.group(0).strip()})")

    return None
