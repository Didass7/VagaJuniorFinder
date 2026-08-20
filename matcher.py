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
    "ios", "android", "flutter", "webmaster", "helpdesk", "support technician", "support", "suporte",
    "cloud support", "it support", "customer support", "technical support", "suporte técnico", "suporte tecnico",
    "sysadmin", "administrador de sistemas", "administradores de sistemas", "system administrator", "systems administrator",
    "database administrator", "dba", "network administrator", "administrador de redes", "database engineer",
    "electronics engineer", "rf engineer", "hardware engineer", "mainframe", "scrum master",
    "diagram creator", "diagram creators", "digital design", "circuit design", "verilog", "systemverilog", "vhdl", "fpga", "asic", "hardware design", "microelectronics", "microelectrónica",
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

TEXT_SENIORITY_DISQUALIFIERS = [
    "seniority level: mid-senior", "seniority level: senior", "seniority level: director", "seniority level: executive",
    "seniority level mid-senior", "seniority level senior", "seniority level director", "seniority level executive",
    "seniority levelmid-senior", "seniority levelsenior", "mid-senior level", "senior level",
    "level of experience: mid", "level of experience: senior", "more than 4y", "more than 5y", "more than 6y",
    "a few years in", "a few years of", "several years of", "deep experience", "been doing this a long time",
    "staff/principal", "senior/principal", "mid/senior", "mid-level", "senior-level", "staff-level", "principal-level",
    "lead-level", "growing into platform ownership", "own the data platform", "competence matters more than years",
    "3+ of experience", "4+ of experience", "5+ of experience", "8+ of experience",
    "3+ de experiência", "4+ de experiência", "5+ de experiência", "8+ de experiência",
    "3+ de experiencia", "4+ de experiencia", "5+ de experiencia", "8+ de experiencia",
    "+3 of experience", "+4 of experience", "+5 of experience", "+8 of experience",
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
# Company Longevity / History Pattern (strips company age like 'fundada há 19 anos', '19 years of history/experience in the market')
COMPANY_HISTORY_PATTERN = re.compile(
    r"\b(?:(?:fundad[ao]|criada|nascida|estabelecid[ao]|h[aá]|desde|com|about)\s+(?:mais\s+de\s+|over\s+|more\s+than\s+)?\d+\s+(?:anos|years)\s+(?:de\s+(?:hist[oó]ria|exist[eê]ncia|mercado|experi[eê]ncia|atua[cç][aã]o|vida|sucesso)|no\s+mercado|in\s+the\s+market|of\s+history|of\s+experience|in\s+business|in\s+the\s+industry))\b|"
    r"\b(?:\d+\s+(?:anos|years)\s+(?:de\s+(?:hist[oó]ria|exist[eê]ncia|mercado|atua[cç][aã]o|vida|sucesso)|no\s+mercado|in\s+the\s+market|of\s+history|in\s+business|in\s+the\s+industry))\b|"
    r"\b(?:(?:comemora|celebra|celebrating|celebrates|marking)\s+(?:mais\s+de\s+)?\d+\s+(?:anos|years))\b|"
    r"\b(?:h[aá]\s+\d+\s+anos\b)",
    re.IGNORECASE
)

YEARS_OF_EXP_PATTERN = re.compile(
    r"\b(?:[1-9]|1[0-2])\+?\s*(?:years?|anos?)?\s*(?:of\s+|de\s+)?experi(?:ence|[eê]ncia)\b|"
    r"\bexperi(?:ence|[eê]ncia)\b[\w\s]{0,20}\b(?:[1-9]|1[0-2])\+?\s*(?:years?|anos?)?\b|"
    r"(?:(?:\+|\>|mais\s+de|superior\s+a|acima\s+de|pelo\s+menos|no\s+m[ií]nimo|m[ií]nimo\s+de|m[ií]nimo|more\s+than|over|at\s+least|minimum\s+of|minimum)\s*)?"
    r"(?<!\w)(?:\+|\>)?\s*(?:[1-9]|1[0-2]|one|two|three|four|five|six|seven|eight|nine|ten|twelve|um|uma|dois|duas|tr[eê]s|quatro|cinco|seis|sete|oito|nove|dez|doze)"
    r"(?:\s*\+|\s+or\s+more|\s+ou\s+mais|\s+plus)?"
    r"(?:\s*(?:to|-|a)\s*(?:[1-9]|1[0-2]|one|two|three|four|five|six|seven|eight|nine|ten|twelve|um|uma|dois|duas|tr[eê]s|quatro|cinco|seis|sete|oito|nove|dez|doze)(?:\s*\+|\s+or\s+more|\s+ou\s+mais)?)?"
    r"\s*(?:years?|anos?)"
    r"(?:\s+or\s+more|\s+ou\s+mais|\s+plus|\s+(?:of\s+|de\s+)?(?:[\w\s]{0,40})?experi(?:ence|[eê]ncia))?\b|"
    r"\bexperi(?:ence|[eê]ncia)\b[\w\s]{0,40}(?:(?:\+|\>|mais\s+de|superior\s+a|pelo\s+menos|no\s+m[ií]nimo|m[ií]nimo\s+de|more\s+than|over|at\s+least|minimum\s+of|minimum)\s*)?(?:[1-9]|1[0-2]|one|two|three|four|five|six|seven|eight|nine|ten|twelve|um|uma|dois|duas|tr[eê]s|quatro|cinco|seis|sete|oito|nove|dez|doze)\s*(?:\+|\s+or\s+more|\s+ou\s+mais)?\s*(?:years?|anos?)\b",
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
    r"\b(?:sprichst|sprechen|spricht|fließend|fließende|fließendes|gute|sehr\s+gute|hervorragende|verhandlungssicher|verhandlungssichere|verhandlungssicheres)\s+(?:in\s+wort\s+und\s+schrift\s+)?(?:deutsch|german|auf\s+deutsch)\b|"
    r"\b(?:deutsch|german|alemão|alemao)\s*(?:und|and|&|/|e)?\s*(?:englisch|english|inglês|ingles)?\s*(?:fließend|fließende|fließendes|kenntnisse|sprichst|sprechen|fluente|verhandlungssicher)\b|"
    r"\b(?:deutschkenntnisse|sprachkenntnisse|deutsch\s+in\s+wort\s+und\s+schrift|auf\s+deutsch\s+in\s+wort\s+und\s+schrift)\b|"
    r"\b(?:verhandlungssicher|verhandlungssichere|verhandlungssicheres)\s+(?:auf\s+deutsch|deutsch)\b|"
    r"\bauf\s+deutsch\b.*?\b(?:c1|c2|b2|fließend|verhandlungssicher|wort\s+und\s+schrift)\b|"
    r"\b(?:praktikant|praktikantin|werkstudent|werkstudentin|pflichtpraktikum)\b|"
    r"\(\s*(?:m/w/d|w/m/d|m/f/d|d/m/w|gn)\s*\)",
    re.IGNORECASE
)

# Foreign Language Post Pattern
FOREIGN_JOB_POST_PATTERN = re.compile(
    r"\b(?:über\s+uns|wir\s+suchen|deine\s+aufgaben|dein\s+profil|das\s+bringst\du\s+mit|unsere\s+anforderungen|in\s+deutschland|du\s+bist|unser\s+team|wir\s+bieten|bewirb\s+dich|standort|vollzeit|teilzeit|mehrparteienhäuser|mehrfamilienhäuser|du\s+kommunizierst|mindestens\s+c1|mindestens\s+b2)\b|"
    r"\b(?:à\s+propos\s+de\s+nous|nous\s+recherchons|vos\s+missions|votre\s+profil|ce\s+que\s+nous\s+offrons)\b|"
    r"\b(?:sobre\s+nosotros|buscamos|tus\s+funciones|tu\s+perfil|requisitos\s+del\s+puesto)\b",
    re.IGNORECASE
)

FOREIGN_GEO_REGIONS = (
    r"latam|latin\s+america|am[eé]rica\s+latina|mexico|m[eé]xico|brasil|brazil|peru|chile|argentina|colombia|colômbia|"
    r"uruguay|uruguaio|ecuador|equador|venezuela|costa\s+rica|panama|panam[aá]|guatemala|"
    r"usa|u\.s\.|u\.s\.a\.|united\s+states|estados\s+unidos|canada|canad[aá]|north\s+america|am[eé]rica\s+do\s+norte|"
    r"apac|asia|ásia|asia-pacific|india|[ií]ndia|philippines|filipinas|pakistan|paquist[aã]o|vietnam|singapore|singapura|"
    r"australia|austr[aá]lia|new\s+zealand|nova\s+zel[aâ]ndia|south\s+africa|[aá]frica\s+do\s+sul|nigeria|nig[eé]ria|kenya|qu[eé]nia|"
    r"germany|deutschland|alemanha|uk|u\.k\.|united\s+kingdom|reino\s+unido|france|frança|spain|espanha|italy|itália|netherlands|holanda|poland|polónia|switzerland|suíça|austria|áustria|sweden|suécia|denmark|dinamarca|norway|noruega|finland|finlândia|ireland|irlanda|belgium|bélgica|czech|romania|roménia"
)

# Geo-Restricted Remote Pattern (e.g. LATAM, Brazil, US, Canada, APAC, Germany-only, UK-only, specific country lists without Portugal)
GEO_RESTRICTED_REMOTE_PATTERN = re.compile(
    rf"\b(?:(?:we\s+are\s+)?(?:looking\s+for|open\s+to|hiring)\s+(?:candidates|people|engineers|talent)?\s*(?:in|from)\s+(?:the\s+)?(?:[a-zA-Z,\s]+)?only\b)|"
    rf"\b(?:based\s+in|located\s+in|residing\s+in|resident\s+in|must\s+reside\s+in|must\s+be\s+located\s+in|living\s+in|remote\s+in|remote\s+from|remote\s+within|remote\s+only\s+in|remote\s+across|work\s+from\s+anywhere\s+in|work\s+anywhere\s+in)\s+(?:the\s+)?(?:{FOREIGN_GEO_REGIONS}|us\s+only)\b|"
    rf"\b(?:{FOREIGN_GEO_REGIONS}|us)\s+(?:only|residents\s+only|citizens\s+only|candidates\s+only)\b|"
    rf"\b(?:only\s+open\s+to|only\s+hiring\s+in|only\s+for\s+candidates\s+in)\s+(?:the\s+)?(?:{FOREIGN_GEO_REGIONS})\b|"
    rf"\b(?:right\s+to\s+work\s+in|legally\s+authorized\s+to\s+work\s+in)\s+(?:the\s+)?(?:{FOREIGN_GEO_REGIONS})\b|"
    rf"\b(?:location\s+preference|location\s+requirement|location\s+restrictions?|work\s+location)\s*:\s*(?:[^\n\.\;]{{0,60}})?(?:{FOREIGN_GEO_REGIONS})\b|"
    rf"\|\s*(?:{FOREIGN_GEO_REGIONS})\s*\||"
    rf"\(\s*(?:{FOREIGN_GEO_REGIONS})\s*(?:only)?\s*\)|"
    rf"\b(?:remoto\s*\(\s*(?:{FOREIGN_GEO_REGIONS})\s*\))\b",
    re.IGNORECASE
)

# Disqualify Crowdsourcing / Microtasks / Domestic Video-Audio Recording / Contributor Gigs (e.g. Toloka, Appen, Remotasks, Outlier, DATAmundi)
CROWDSOURCING_MICROTASKS_PATTERN = re.compile(
    r"\b(?:not\s+a\s+job|n[aã]o\s+[eé]\s+um\s+emprego|not\s+an\s+employment|this\s+is\s+not\s+a\s+job|toloka|remotasks|oneforma|clickworker|appen|prolific|mturk|mechanical\s+turk|outlier\s+ai|telus\s+international|datamundi|summa\s+linguae)\b|"
    r"\b(?:dataset\s+project|expert\s+pool|onboard\s+approximately|creating\s+a\s+dataset|dataset\s+creator|diagram\s+creators?|hourly\s+rate\s*:\s*~\s*\d+|~\s*\d+\s*usd/h|usd\s*/\s*h\b)\b|"
    r"\b(?:record\s+(?:your|everyday|point-of-view|household|routine|videos?)|mount\s+your\s+smartphone|household\s+chores|earn\s+while\s+you|get\s+paid\s+(?:just\s+)?for\s+recording|micro-?tasks?|microtarefas?|crowdsourcing|data\s+collector|video\s+recording\s+contributor|audio\s+recording\s+task|voice\s+recording\s+task)\b",
    re.IGNORECASE
)

# Disqualify Extreme Senior/Staff Compensation Packages ($120k-$250k+ USD / 120k€+)
SENIOR_COMPENSATION_PATTERN = re.compile(
    r"\b(?:\$|€|£|eur|usd|gbp)\s*(?:1[2-9]\d|2\d\d|3\d\d|4\d\d|5\d\d)[,\.]?\d{3}\b|"
    r"\b(?:1[2-9]\d|2\d\d|3\d\d|4\d\d|5\d\d)\s*k\s*(?:\$|€|£|eur|usd|gbp|\b)|"
    r"\b(?:\$|€|£|eur|usd|gbp)\s*(?:1[2-9]\d|2\d\d|3\d\d|4\d\d|5\d\d)\s*k\b|"
    r"\b(?:1[2-9]\d|2\d\d|3\d\d|4\d\d|5\d\d)[,\.]000\s*(?:usd|eur|€|\$)",
    re.IGNORECASE
)

# Zero-Experience Indicator Pattern (Strict word boundaries to prevent 'graduates' matching general degree requirements)
ZERO_EXP_INDICATOR_PATTERN = re.compile(
    r"\b(?:0\s*(?:a|to|-)\s*1\s*(?:ano|anos|year|years)|0\s*(?:anos|years)|sem\s+experi[eê]ncia|n[aã]o\s+[eé]\s+necess[aá]ria\s+experi[eê]ncia|n[aã]o\s+requer\s+experi[eê]ncia|rec[eé]m[- ]licenciad[oa]s?|est[aá]gio\s+profissional|est[aá]gios?|trainees?|internships?|\binterns?\b|\b(?:recém[- ]graduad[oa]s?|recem[- ]graduad[oa]s?|recent\s+graduates?|fresh\s+graduates?|new\s+graduates?|graduate\s+program|graduate\s+scheme)\b)\b",
    re.IGNORECASE
)

# Advanced Seniority Experience Hard Disqualifier Pattern (3+, 4+, 5+, 8+ years, +5 years, minimum 3+ years, 8 or more years, a few years in, 3+ of experience)
ADVANCED_EXP_HARD_DISQUALIFIERS_PATTERN = re.compile(
    r"\b(?:a\s+few\s+years(?:\s+in|\s+of)?|several\s+years(?:\s+of)?|deep\s+experience|staff/principal|senior/principal|been\s+doing\s+this\s+a\s+long\s+time)\b|"
    r"\b(?:[3-9]|1[0-2])\+?\s*(?:years?|anos?)?\s*(?:of\s+|de\s+)?experi(?:ence|[eê]ncia)\b|"
    r"\bexperi(?:ence|[eê]ncia)\b[\w\s]{0,20}\b(?:[3-9]|1[0-2])\+?\s*(?:years?|anos?)?\b|"
    r"(?:(?:\+|\>|mais\s+de|superior\s+a|acima\s+de|pelo\s+menos|no\s+m[ií]nimo|m[ií]nimo\s+de|m[ií]nimo|more\s+than|over|at\s+least|minimum\s+of|minimum)\s*)?"
    r"(?<!\w)(?:\+|\>)?\s*(?:[3-9]|1[0-2]|three|four|five|six|seven|eight|nine|ten|twelve|tr[eê]s|quatro|cinco|seis|sete|oito|nove|dez|doze)"
    r"(?:\s*\+|\s+or\s+more|\s+ou\s+mais|\s+plus)?"
    r"(?:\s*(?:to|-|a)\s*(?:[3-9]|1[0-2]|three|four|five|six|seven|eight|nine|ten|twelve|tr[eê]s|quatro|cinco|seis|sete|oito|nove|dez|doze)(?:\s*\+|\s+or\s+more|\s+ou\s+mais)?)?"
    r"\s*(?:years?|anos?)"
    r"(?:\s+or\s+more|\s+ou\s+mais|\s+plus|\s+(?:of\s+|de\s+)?(?:[\w\s]{0,40})?experi(?:ence|[eê]ncia))?\b|"
    r"\bexperi(?:ence|[eê]ncia)\b[\w\s]{0,40}(?:(?:\+|\>|mais\s+de|superior\s+a|pelo\s+menos|no\s+m[ií]nimo|m[ií]nimo\s+de|more\s+than|over|at\s+least|minimum\s+of|minimum)\s*)?(?:[3-9]|1[0-2]|three|four|five|six|seven|eight|nine|ten|twelve|tr[eê]s|quatro|cinco|seis|sete|oito|nove|dez|doze)\s*(?:\+|\s+or\s+more|\s+ou\s+mais)?\s*(?:years?|anos?)\b",
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

def clean_analysis_text(text: str) -> str:
    """Removes all emojis and repetitive prefix markers (e.g. 'Adequada (71%): Adequada:') returning clean natural text."""
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
    def __init__(
        self,
        profile: CandidateProfile,
        ai_evaluator: Optional[AIEvaluator] = None,
        enable_ai: Optional[bool] = None
    ):
        self.profile = profile
        should_enable = enable_ai if enable_ai is not None else config.enable_ai_evaluation
        if not should_enable:
            self.ai_evaluator = None
        elif ai_evaluator is not None:
            self.ai_evaluator = ai_evaluator
        else:
            self.ai_evaluator = AIEvaluator()

    def evaluate_job(self, job: Job) -> ScoredJob:
        text = COMPANY_HISTORY_PATTERN.sub(" ", f"{job.title} {job.location} {job.description}").lower()
        title_lower = job.title.lower()
        location_lower = job.location.lower()
        work_mode_lower = job.work_mode.lower()

        # -------------------------------------------------------------
        # HARD DISQUALIFICATION FILTERS (Score = 0.0)
        # -------------------------------------------------------------

        clean_desc = COMPANY_HISTORY_PATTERN.sub(" ", job.description).strip()
        clean_desc_lower = clean_desc.lower()
        incomplete_indicators = [
            "join or sign in to find your next job",
            "sign in to view", "sign in to apply", "log in to view", "faça login",
            "entre para ver", "registar para ver", "crie uma conta", "sign in to see more"
        ]
        
        if len(clean_desc) < 100 or any(ind in clean_desc_lower for ind in incomplete_indicators):
            return ScoredJob(job=job, score=0.0, matched_skills=[], missing_skills=[], seniority_status="Descrição Incompleta / Bloqueada", match_reason="Descrição indisponível", ai_reasoning="Filtro Automático: Descrição indisponível ou protegida por login")

        if any(exp_term in clean_desc_lower for exp_term in ["oferta expirada", "vaga expirada", "anúncio expirado", "job no longer available", "no longer accepting applications", "this job is no longer available"]):
            return ScoredJob(job=job, score=0.0, matched_skills=[], missing_skills=[], seniority_status="Oferta Expirada", match_reason="Anúncio marcado como expirado", ai_reasoning="Filtro Automático: Anúncio de vaga já expirado")

        today = datetime.date.today()
        job_date = parse_job_date(job.pub_date)
        if (today - job_date).days > 14:
            return ScoredJob(job=job, score=0.0, matched_skills=[], missing_skills=[], seniority_status="Vaga Antiga (> 14 dias)", match_reason="Oferta expirada (> 14 dias)", ai_reasoning="Filtro Automático: Publicada há mais de 14 dias")

        profile_locs = [l.lower() for l in getattr(self.profile, 'locations', []) if l.lower() not in ["remoto", "remote", "hybrid", "híbrido", "hibrido"]]
        allowed_locations = set(PORTUGAL_LOCATIONS + profile_locs)
        is_portugal = any(loc in location_lower for loc in allowed_locations) or ("portugal" in text) or any(loc in text for loc in profile_locs if len(loc) > 3)
        is_strictly_remote = (work_mode_lower == "remoto") or ("remoto" in location_lower) or ("remote" in location_lower) or ("teletrabalho" in location_lower)

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

        target_titles_lower = [t.lower() for t in self.profile.target_titles]
        tech_stack_lower = [t.lower() for t in self.profile.tech_stack]
        profile_languages = [l.lower() for l in self.profile.languages]
        speaks_spanish = any("espanhol" in l or "spanish" in l for l in profile_languages)

        for disq, pattern in IRRELEVANT_ROLE_PATTERNS:
            # If the candidate explicitly targets this domain (e.g. sysadmin, network, cloud for Rafael), do NOT disqualify it!
            if any(disq in tt for tt in target_titles_lower) or any(disq in ts for ts in tech_stack_lower):
                continue
            if pattern.search(title_lower):
                return ScoredJob(job=job, score=0.0, matched_skills=[], missing_skills=[], seniority_status="Cargo Irrelevante", match_reason=f"Título desqualificado por conter '{disq}'", ai_reasoning=f"Filtro Automático: Cargo irrelevante ({disq})")

        if any(k in text for k in ["crianças", "criancas", "adolescentes", "pós-letivo", "pos-letivo", "sharkcoders"]):
            return ScoredJob(job=job, score=0.0, matched_skills=[], missing_skills=[], seniority_status="Ensino Infantil", match_reason="Ensino de crianças/adolescentes", ai_reasoning="Filtro Automático: Ensino de crianças/adolescentes")

        # Dynamic Core Domain Check based on profile's target titles and tech stack
        has_target_title = any(tt in title_lower for tt in target_titles_lower)
        has_tech_in_title = any(ts in title_lower for ts in tech_stack_lower)
        
        # Build dynamic domain tokens from candidate's profile + general tech & junior entry-level roles
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

        # Protect against cross-profile leaks (e.g. Data Engineer job slipping into Cybersecurity/DevOps profile)
        data_domain_terms = [
            "data engineer", "data scientist", "cientista de dados", "bi analyst", "analista de bi", "data architect",
            "ai engineer", "engenheiro de ia", "machine learning", "computer vision", "nlp engineer"
        ]
        security_net_terms = [
            "cybersecurity", "cibersegurança", "network engineer", "soc analyst", "sysadmin", "analista de soc",
            "técnico de redes", "administrador de redes", "administrador de sistemas", "devops engineer", "secops"
        ]

        target_titles_str = " ".join(target_titles_lower)
        is_security_profile = any(s in target_titles_str for s in ["cybersecurity", "cibersegurança", "devops", "network", "redes", "soc", "segurança", "seguranca"])
        is_data_profile = any(d in target_titles_str for d in ["data scientist", "cientista de dados", "ai engineer", "engenheiro de ia", "machine learning", "data engineer"])

        if is_security_profile and not is_data_profile:
            if any(dt in title_lower for dt in data_domain_terms):
                return ScoredJob(job=job, score=0.0, matched_skills=[], missing_skills=[], seniority_status="Fora do Perfil", match_reason="Vaga de Engenharia/Ciência de Dados fora do perfil de Cibersegurança/DevOps", ai_reasoning="Filtro Automático: Cargo de Dados/IA fora do perfil de Cibersegurança")

        if is_data_profile and not is_security_profile:
            if any(st in title_lower for st in security_net_terms):
                return ScoredJob(job=job, score=0.0, matched_skills=[], missing_skills=[], seniority_status="Fora do Perfil", match_reason="Vaga de Cibersegurança/Redes fora do perfil de IA/Data", ai_reasoning="Filtro Automático: Cargo de Cibersegurança/Redes fora do perfil de IA/Data")

        if not has_domain_in_title and not has_target_title and not has_tech_in_title:
            return ScoredJob(job=job, score=0.0, matched_skills=[], missing_skills=[], seniority_status="Fora do Perfil", match_reason="Título não corresponde às funções ou tecnologias alvo do candidato", ai_reasoning="Filtro Automático: Título não corresponde às funções alvo do candidato")

        if PHD_REQUIREMENT_PATTERN.search(title_lower) or PHD_REQUIREMENT_PATTERN.search(text):
            return ScoredJob(job=job, score=0.0, matched_skills=[], missing_skills=[], seniority_status="Requer Doutoramento", match_reason="Exige PhD ou Doutoramento", ai_reasoning="Filtro Automático: Exige Doutoramento (PhD)")

        # Academic Degree Requirement Check: If offer requires Masters/Nível 7 and candidate has Licenciatura (Nível 6)
        candidate_degree = getattr(self.profile, 'degree', '').lower()
        has_masters = "mestrado" in candidate_degree or "master" in candidate_degree
        if not has_masters:
            masters_match = re.search(r"\b(?:habilita[cç][aã]o\s+base\s*:\s*mestrado|n[ií]vel\s+7\b|exige\s+mestrado|mestrado\s+(?:obrigat[oó]rio|completo|exigido))\b", text, re.IGNORECASE)
            if masters_match:
                return ScoredJob(job=job, score=0.0, matched_skills=[], missing_skills=[], seniority_status="Requer Mestrado", match_reason="Oferta exige Mestrado (Nível 7), incompatível com Licenciatura", ai_reasoning="Filtro Automático: Exige Mestrado (Nível 7)")

        # Language Disqualification (exempt Spanish if candidate speaks Spanish)
        lang_match = MANDATORY_OTHER_LANGUAGES_PATTERN.search(text)
        if lang_match:
            matched_str = lang_match.group(0).lower()
            is_spanish_match = any(sp in matched_str for sp in ["spanish", "español", "espanhol"])
            if not (speaks_spanish and is_spanish_match):
                return ScoredJob(job=job, score=0.0, matched_skills=[], missing_skills=[], seniority_status="Idioma Não Suportado", match_reason=f"Exige outro idioma ({matched_str})", ai_reasoning=f"Filtro Automático: Exige outro idioma ({matched_str})")

        foreign_post_match = FOREIGN_JOB_POST_PATTERN.search(text)
        if foreign_post_match:
            matched_post = foreign_post_match.group(0).lower()
            is_spanish_post = any(sp in matched_post for sp in ["sobre nosotros", "buscamos", "tus funciones", "tu perfil", "requisitos del puesto"])
            if not (speaks_spanish and is_spanish_post):
                return ScoredJob(job=job, score=0.0, matched_skills=[], missing_skills=[], seniority_status="Idioma Não Suportado", match_reason=f"Anúncio noutro idioma ({matched_post})", ai_reasoning=f"Filtro Automático: Anúncio noutro idioma ({matched_post})")

        is_explicit_junior = any(j_term in title_lower for j_term in ["junior", "jr", "estágio", "estagio", "trainee", "graduate program", "entry level", "intern"])
        is_explicit_zero_to_one = any(b in text for b in ["recém-licenciado", "recem licenciado", "recém licenciado", "0-1", "recent graduate", "fresh graduate", "recém-graduado", "recem-graduado", "0 a 1 ano", "0 to 1 year"])
        has_verified_junior_indicator = is_explicit_junior or job.iefp_mentioned or is_explicit_zero_to_one

        # Check if the job is explicitly targeted at 0-2 years / Entry-Level / Estágio / Recém-Licenciado / Júnior
        is_explicit_zero_exp = (
            bool(ZERO_EXP_INDICATOR_PATTERN.search(text))
            or job.iefp_mentioned
            or any(t in title_lower for t in ["estágio", "estagio", "trainee", "recém-licenciado", "recem-licenciado", "junior", "júnior", "entry level", "entry-level", "graduate", "bolsa", "fellowship"])
        )

        for disq, pattern in TITLE_SENIORITY_PATTERNS:
            if pattern.search(title_lower):
                return ScoredJob(job=job, score=0.0, matched_skills=[], missing_skills=[], seniority_status="Sénior / Liderança", match_reason=f"Título sénior ({disq})", ai_reasoning=f"Filtro Automático: Título sénior ({disq})")

        # Hard Disqualification: Any explicit 3+, 4+, 5+ years requirement is definitively senior / not junior
        adv_exp_match = ADVANCED_EXP_HARD_DISQUALIFIERS_PATTERN.search(text)
        if adv_exp_match:
            return ScoredJob(
                job=job, score=0.0, matched_skills=[], missing_skills=[],
                seniority_status="Requer Experiência (>0 anos)",
                match_reason=f"Exige experiência sénior ({adv_exp_match.group(0).strip()})",
                ai_reasoning=f"Filtro Automático: Exige experiência sénior ({adv_exp_match.group(0).strip()})"
            )

        # If not explicitly marked as a 0-experience / internship position, check for other experience requirements
        if not is_explicit_zero_exp:
            for disq, pattern in TEXT_SENIORITY_PATTERNS:
                if pattern.search(text):
                    return ScoredJob(job=job, score=0.0, matched_skills=[], missing_skills=[], seniority_status="Requer Experiência (>0 anos)", match_reason=f"Exige experiência prévia ({disq})", ai_reasoning=f"Filtro Automático: Exige experiência prévia ({disq})")
                    
            exp_match = YEARS_OF_EXP_PATTERN.search(text)
            if exp_match:
                return ScoredJob(job=job, score=0.0, matched_skills=[], missing_skills=[], seniority_status="Requer Experiência (>0 anos)", match_reason=f"Exige experiência prévia ({exp_match.group(0).strip()})", ai_reasoning=f"Filtro Automático: Exige experiência prévia ({exp_match.group(0).strip()})")


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

                    clean_reason = clean_analysis_text(ai_res.reasoning)
                    
                    # If AI explicitly marked the job as unsuitable, 0 fit score, or non-junior/senior
                    if not ai_res.is_suitable or ai_res.fit_score == 0 or is_clearly_senior or is_demanding_3plus_years:
                        sj.score = 0.0
                        sj.seniority_status = f"Rejeitada por IA ({ai_res.seniority_detected or 'Inadequada'})"
                        sj.match_reason = clean_reason
                        sj.ai_reasoning = f"Rejeitada por IA: {clean_reason}"
                        ai_rejected += 1
                        if include_disqualified:
                            final_scored_jobs.append(sj)
                        continue

                    # Only jobs verified as suitable by AI are accepted
                    blended_score = round(0.5 * sj.score + 0.5 * ai_res.fit_score, 1)
                    if blended_score < 50.0:
                        sj.score = 0.0
                        sj.seniority_status = "Score Insuficiente"
                        sj.match_reason = clean_reason
                        sj.ai_reasoning = f"Score Insuficiente ({blended_score}%): {clean_reason}"
                        ai_rejected += 1
                        if include_disqualified:
                            final_scored_jobs.append(sj)
                        continue

                    sj.score = blended_score
                    sj.ai_evaluated = True
                    sj.ai_reasoning = clean_reason if clean_reason else f"Vaga alinhada com perfil júnior ({', '.join(sj.matched_skills[:3]) if sj.matched_skills else 'Target Role'})."
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
