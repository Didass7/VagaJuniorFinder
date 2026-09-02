import json
import re
import os
from typing import List, Tuple

RULES_PATH = os.path.join(os.path.dirname(__file__), 'rules.json')
with open(RULES_PATH, 'r', encoding='utf-8') as f:
    _rules_data = json.load(f)

IRRELEVANT_ROLE_DISQUALIFIERS = _rules_data.get('IRRELEVANT_ROLE_DISQUALIFIERS', [])
TITLE_SENIORITY_DISQUALIFIERS = _rules_data.get('TITLE_SENIORITY_DISQUALIFIERS', [])
TEXT_SENIORITY_DISQUALIFIERS = _rules_data.get('TEXT_SENIORITY_DISQUALIFIERS', [])
PORTUGAL_LOCATIONS = _rules_data.get('PORTUGAL_LOCATIONS', [])

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
    r"\b(?:über\s+uns|wir\s+suchen|deine\s+aufgaben|dein\s+profil|das\s+bringst\s+du\s+mit|unsere\s+anforderungen|in\s+deutschland|du\s+bist|unser\s+team|wir\s+bieten|bewirb\s+dich|standort|vollzeit|teilzeit|mehrparteienhäuser|mehrfamilienhäuser|du\s+kommunizierst|mindestens\s+c1|mindestens\s+b2)\b|"
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
    r"\b(?:0\s*(?:a|to|-)\s*1\s*(?:ano|anos|year|years)|0\s*(?:anos|years)|sem\s+experi[eê]ncia|n[aã]o\s+[eé]\s+necess[aá]ria\s+experi[eê]ncia|n[aã]o\s+requer\s+experi[eê]ncia|rec[eé]m[- ]licenciad[oa]s?|est[aá]gio\s+profissional|est[aá]gio\s+curricular|est[aá]gio\s+iefp|est[aá]gio\s+ativar|programa\s+de\s+est[aá]gios?|estagi[aá]ri[oa]s?|trainees?|internships?|\binterns?\b|\b(?:recém[- ]graduad[oa]s?|recem[- ]graduad[oa]s?|recent\s+graduates?|fresh\s+graduates?|new\s+graduates?|graduate\s+program|graduate\s+scheme)\b)\b",
    re.IGNORECASE
)

# Advanced Seniority Experience Hard Disqualifier Pattern (2+ years of required professional experience, 3+, 4+, 5+, 8+ years, +5 years, minimum 2+/3+ years, 8 or more years, a few years in, 3+ of experience, pleno-senior, etc.)
ADVANCED_EXP_HARD_DISQUALIFIERS_PATTERN = re.compile(
    r"\b(?:a\s+few\s+years(?:\s+in|\s+of)?|several\s+years(?:\s+of)?|deep\s+experience|staff/principal|senior/principal|been\s+doing\s+this\s+a\s+long\s+time)\b|"
    r"\b(?:pleno[- ]s[eê]nior|mid[- ]senior|n[ií]vel\s+de\s+experi[eê]ncia\s*:\s*pleno[- ]s[eê]nior)\b|"
    r"\b(?:between\s+|entre\s+)?(?:[2-9]|1[0-2]|two|three|four|five|dois|duas|tr[eê]s|quatro|cinco)\s*(?:and|e|to|-|a)\s*(?:[3-9]|1[0-2]|three|four|five|six|seven|eight|nine|ten|tr[eê]s|quatro|cinco|seis|sete|oito|nove|dez)\s*(?:years?|anos?)\b|"
    r"\b(?:experi[eê]ncia\s+(?:profissional\s+|relevante\s+|comprovada\s+|pr[eé]via\s+)?)?(?:pelo\s+menos|no\s+m[ií]nimo|m[ií]nimo\s+de|m[ií]nima\s+de|mais\s+de|superior\s+a|acima\s+de|at\s+least|minimum\s+of|minimum|more\s+than|over)\s*(?:2|dois|duas|two|[3-9]|1[0-2]|three|four|five|six|seven|eight|nine|ten|tr[eê]s|quatro|cinco)\s*(?:years?|anos?)(?:\s+(?:de\s+|of\s+)?experi[eê]ncia(?:\s+profissional)?)?\b|"
    r"\b(?:experi[eê]ncia\s+profissional\s+m[ií]nima\s+de\s+(?:2|dois|duas|two|[3-9]|1[0-2]|three|four|five|tr[eê]s|quatro|cinco)\s+(?:anos|years))\b|"
    r"\b(?:[2-9]|1[0-2]|dois|duas|two|three|four|five|tr[eê]s|quatro|cinco)\+?\s*(?:years?|anos?)\s*(?:of\s+|de\s+)?experi(?:ence|[eê]ncia)(?:\s+profissional)?\b|"
    r"\bexperi(?:ence|[eê]ncia)(?:\s+profissional)?\b[\w\s]{0,20}\b(?:[2-9]|1[0-2]|dois|duas|two|three|four|five|tr[eê]s|quatro|cinco)\+?\s*(?:years?|anos?)?\b|"
    r"(?:(?:\+|\>|mais\s+de|superior\s+a|acima\s+de|pelo\s+menos|no\s+m[ií]nimo|m[ií]nimo\s+de|m[ií]nima\s+de|m[ií]nimo|more\s+than|over|at\s+least|minimum\s+of|minimum)\s*)?"
    r"(?<!\w)(?:\+|\>)?\s*(?:[2-9]|1[0-2]|two|three|four|five|six|seven|eight|nine|ten|twelve|dois|duas|tr[eê]s|quatro|cinco|seis|sete|oito|nove|dez|doze)"
    r"(?:\s*\+|\s+or\s+more|\s+ou\s+mais|\s+plus)?"
    r"(?:\s*(?:to|-|a)\s*(?:[3-9]|1[0-2]|three|four|five|six|seven|eight|nine|ten|twelve|tr[eê]s|quatro|cinco|seis|sete|oito|nove|dez|doze)(?:\s*\+|\s+or\s+more|\s+ou\s+mais)?)?"
    r"\s*(?:years?|anos?)"
    r"(?:\s+or\s+more|\s+ou\s+mais|\s+plus|\s+(?:of\s+|de\s+)?(?:[\w\s]{0,40})?experi(?:ence|[eê]ncia))?\b|"
    r"\bexperi(?:ence|[eê]ncia)\b[\w\s]{0,40}(?:(?:\+|\>|mais\s+de|superior\s+a|pelo\s+menos|no\s+m[ií]nimo|m[ií]nimo\s+de|more\s+than|over|at\s+least|minimum\s+of|minimum)\s*)?(?:[2-9]|1[0-2]|two|three|four|five|six|seven|eight|nine|ten|twelve|dois|duas|tr[eê]s|quatro|cinco|seis|sete|oito|nove|dez|doze)\s*(?:\+|\s+or\s+more|\s+ou\s+mais)?\s*(?:years?|anos?)\b",
    re.IGNORECASE
)

import datetime
import email.utils

def parse_job_date(date_str: str) -> datetime.date:
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
