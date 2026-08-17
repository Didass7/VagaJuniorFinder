import json
import re
import time
import logging
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from config import CandidateProfile, config
from scraper import Job

logger = logging.getLogger(__name__)

@dataclass
class AIEvaluationResult:
    is_suitable: bool
    fit_score: float
    seniority_detected: str
    reasoning: str
    pros: List[str] = field(default_factory=list)
    cons: List[str] = field(default_factory=list)

class AIEvaluator:
    """Evaluates job suitability using Groq LLM API (primary) or Gemini LLM API (fallback) with batching support."""

    def __init__(self, groq_api_key: Optional[str] = None, gemini_api_key: Optional[str] = None):
        self.groq_api_key = groq_api_key if groq_api_key is not None else config.groq_api_key
        self.groq_model_name = config.groq_model_name or "openai/gpt-oss-120b"
        
        self.gemini_api_key = gemini_api_key if gemini_api_key is not None else config.gemini_api_key
        self.gemini_model_name = config.ai_model_name or "gemini-3.5-flash-lite"
        
        self._groq_client = None
        self._gemini_client = None
        self._gemini_cooldown_until: float = 0.0
        self._groq_cooldown_until: float = 0.0
        self._invalid_groq_models = set()
        self._invalid_gemini_models = set()
        
        if self.groq_api_key:
            try:
                from groq import Groq
                self._groq_client = Groq(api_key=self.groq_api_key)
                logger.info(f"🤖 Initialized Groq AI Evaluator with model '{self.groq_model_name}'")
            except Exception as e:
                logger.warning(f"Failed to initialize Groq Client: {e}")

        if self.gemini_api_key:
            try:
                from google import genai
                self._gemini_client = genai.Client(api_key=self.gemini_api_key)
                logger.info(f"🤖 Initialized Gemini AI Evaluator with model '{self.gemini_model_name}'")
            except Exception as e:
                logger.warning(f"Failed to initialize Gemini Client: {e}")

    @property
    def is_available(self) -> bool:
        return self._groq_client is not None or self._gemini_client is not None

    @property
    def active_provider(self) -> str:
        if self._gemini_client and time.time() >= self._gemini_cooldown_until:
            return f"Gemini ({self.gemini_model_name})"
        elif self._groq_client and time.time() >= self._groq_cooldown_until:
            return f"Groq ({self.groq_model_name})"
        elif self._gemini_client:
            return f"Gemini ({self.gemini_model_name})"
        elif self._groq_client:
            return f"Groq ({self.groq_model_name})"
        return "None"

    def evaluate_job(self, job: Job, profile: CandidateProfile) -> Optional[AIEvaluationResult]:
        """Evaluates a single job description (wraps batch evaluation of 1 job)."""
        res = self.evaluate_jobs_batch([job], profile, batch_size=1)
        return res.get(job.job_id)

    def evaluate_jobs_batch(
        self, jobs: List[Job], profile: CandidateProfile, batch_size: int = 4
    ) -> Dict[str, AIEvaluationResult]:
        """Evaluates a list of jobs in small batches (e.g. 4 jobs per LLM call) for maximum speed and token efficiency."""
        if not self.is_available or not jobs:
            return {}

        results: Dict[str, AIEvaluationResult] = {}
        total_batches = (len(jobs) + batch_size - 1) // batch_size
        logger.info(f"🤖 Starting AI batch evaluation: {len(jobs)} jobs across {total_batches} batches via {self.active_provider}...")
        
        # Split jobs into chunks of batch_size
        for batch_num, i in enumerate(range(0, len(jobs), batch_size), 1):
            chunk = jobs[i : i + batch_size]
            chunk_results = self._process_single_batch(chunk, profile)
            results.update(chunk_results)
            logger.info(f"🤖 Evaluated batch {batch_num}/{total_batches} ({len(chunk_results)}/{len(chunk)} jobs processed).")

        return results

    def _process_single_batch(self, batch: List[Job], profile: CandidateProfile) -> Dict[str, AIEvaluationResult]:
        now = time.time()
        gemini_ready = self._gemini_client is not None and now >= self._gemini_cooldown_until
        groq_ready = self._groq_client is not None and now >= self._groq_cooldown_until

        if not gemini_ready and not groq_ready:
            if not self._gemini_client and not self._groq_client:
                return {}
            min_cooldown = min(
                self._gemini_cooldown_until - now if self._gemini_client else 9999,
                self._groq_cooldown_until - now if self._groq_client else 9999
            )
            if 0 < min_cooldown <= 5.0:
                logger.info(f"⏳ Pausing {int(min_cooldown + 1)}s for AI rate-limit reset...")
                time.sleep(min_cooldown + 1.0)
                now = time.time()
                gemini_ready = self._gemini_client is not None and now >= self._gemini_cooldown_until
                groq_ready = self._groq_client is not None and now >= self._groq_cooldown_until
            else:
                logger.info("⏳ Both AI engines (Gemini/Groq) in rate-limit cooldown. Using Stage 1 Heuristic Scoring for this batch.")
                return {}

        # 1. Prefer Gemini if ready
        if gemini_ready:
            res = self._evaluate_batch_with_gemini(batch, profile)
            if res:
                return res
            if self._groq_client and time.time() >= self._groq_cooldown_until:
                res_g = self._evaluate_batch_with_groq(batch, profile)
                if res_g:
                    return res_g

        # 2. Otherwise use Groq
        elif groq_ready:
            res = self._evaluate_batch_with_groq(batch, profile)
            if res:
                return res
            if self._gemini_client and time.time() >= self._gemini_cooldown_until:
                res_m = self._evaluate_batch_with_gemini(batch, profile)
                if res_m:
                    return res_m

        return {}

    def _clean_and_extract_json(self, raw_text: str) -> str:
        """Strips markdown code blocks, trims surrounding spaces, and extracts JSON content safely."""
        if not raw_text:
            return ""
        text = raw_text.strip()
        # Remove markdown code blocks if present (```json ... ``` or ``` ...)
        if text.startswith("```"):
            lines = text.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip().startswith("```"):
                lines = lines[:-1]
            text = "\n".join(lines).strip()

        # Regex to locate the outermost JSON object or array if extra text exists
        match = re.search(r"(\{.*\}|\[.*\])", text, re.DOTALL)
        if match:
            text = match.group(1).strip()

        # Replace trailing commas before closing braces/brackets (common LLM JSON error)
        text = re.sub(r",\s*([\}\]])", r"\1", text)
        return text

    def _evaluate_batch_with_groq(self, batch: List[Job], profile: CandidateProfile) -> Dict[str, AIEvaluationResult]:
        prompt = self._build_batch_prompt(batch, profile)
        groq_candidates = [
            m for m in dict.fromkeys([
                self.groq_model_name,
                "openai/gpt-oss-120b",
                "openai/gpt-oss-20b",
                "gemma2-9b-it",
                "deepseek-r1-distill-llama-70b",
            ]) if m not in self._invalid_groq_models
        ]

        for model in groq_candidates:
            try:
                time.sleep(0.6)  # Polite delay between calls
                response = self._groq_client.chat.completions.create(
                    model=model,
                    messages=[
                        {
                            "role": "system",
                            "content": "És um assistente especialista em recrutamento tecnológico e inteligência artificial. Respondes obrigatoriamente e apenas em formato JSON estrito."
                        },
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.2,
                    max_completion_tokens=2500
                )

                content = response.choices[0].message.content
                if not content:
                    continue

                parsed = self._parse_batch_json_response(content, batch)
                if parsed:
                    self.groq_model_name = model
                    self._groq_cooldown_until = 0.0
                    return parsed
            except Exception as e:
                err_str = str(e).lower()
                if "model_decommissioned" in err_str or "decommissioned" in err_str or "not_found" in err_str or "does not exist" in err_str:
                    logger.warning(f"⚠️ Groq model '{model}' is decommissioned/unavailable ({e}). Pruning from candidates...")
                    self._invalid_groq_models.add(model)
                    continue
                elif "rate_limit" in err_str or "429" in err_str:
                    logger.warning(f"⏳ Groq model '{model}' rate limited (429). Trying next candidate model...")
                    continue
                else:
                    logger.warning(f"Groq model '{model}' issue ({e}). Trying next Groq model...")
                    continue

        logger.warning("⏳ All Groq candidate models exhausted / rate limited. Setting Groq cooldown for 60s...")
        self._groq_cooldown_until = time.time() + 60.0
        return {}

    def _evaluate_batch_with_gemini(self, batch: List[Job], profile: CandidateProfile) -> Dict[str, AIEvaluationResult]:
        prompt = self._build_batch_prompt(batch, profile)
        gemini_candidates = [
            m for m in dict.fromkeys([
                self.gemini_model_name,
                "gemini-3.5-flash-lite",
                "gemini-3.6-flash",
                "gemini-3.5-flash",
                "gemini-3.7-flash",
            ]) if m not in self._invalid_gemini_models
        ]

        from google.genai import types

        for model in gemini_candidates:
            try:
                time.sleep(0.5)
                response = self._gemini_client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        temperature=0.2,
                        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
                    )
                )
                
                if not response.text:
                    continue

                parsed = self._parse_batch_json_response(response.text, batch)
                if parsed:
                    self.gemini_model_name = model
                    self._gemini_cooldown_until = 0.0
                    return parsed
            except Exception as e:
                err_str = str(e).lower()
                if "not_found" in err_str or "not found" in err_str or "is not supported" in err_str or "invalid_argument" in err_str:
                    logger.warning(f"⚠️ Gemini model '{model}' is unavailable/deprecated ({e}). Pruning from candidates...")
                    self._invalid_gemini_models.add(model)
                    continue
                elif "429" in err_str or "resource_exhausted" in err_str or "quota" in err_str:
                    logger.warning(f"⏳ Gemini model '{model}' quota/rate limit reached (429). Trying next candidate model...")
                    continue
                else:
                    logger.warning(f"⚠️ Gemini model '{model}' issue ({e}). Trying next candidate...")
                    continue

        logger.warning("⏳ All Gemini candidate models exhausted / rate limited. Setting Gemini cooldown for 60s...")
        self._gemini_cooldown_until = time.time() + 60.0
        return {}

    def _parse_batch_json_response(self, raw_json: str, batch: List[Job]) -> Dict[str, AIEvaluationResult]:
        results: Dict[str, AIEvaluationResult] = {}
        if not raw_json:
            return results

        data = None
        cleaned_json = self._clean_and_extract_json(raw_json)
        try:
            data = json.loads(cleaned_json)
        except Exception as e1:
            # Fallback 1: Attempt balancing open brackets and braces
            try:
                open_braces = cleaned_json.count("{") - cleaned_json.count("}")
                open_brackets = cleaned_json.count("[") - cleaned_json.count("]")
                fixed_json = cleaned_json + ("]" * max(0, open_brackets)) + ("}" * max(0, open_braces))
                data = json.loads(fixed_json)
            except Exception:
                # Fallback 2: Regex extraction of individual job evaluation objects
                eval_blocks = re.findall(r"\{\s*\"job_index\"[^\{\}]+\}", raw_json, re.DOTALL)
                evals_list = []
                for b in eval_blocks:
                    try:
                        evals_list.append(json.loads(b))
                    except Exception:
                        pass
                if evals_list:
                    data = {"evaluations": evals_list}
                else:
                    logger.error(f"Failed to parse batch AI JSON response: {e1}")
                    return results

        try:
            evals = data.get("evaluations", []) if isinstance(data, dict) else data
            
            if not isinstance(evals, list):
                evals = []

            for item in evals:
                if not isinstance(item, dict):
                    continue
                idx = item.get("job_index")
                if idx is not None and 0 <= idx < len(batch):
                    target_job = batch[idx]
                    raw_reason = str(item.get("reasoning", "")).strip()
                    words = raw_reason.split()
                    if len(words) > 25:
                        raw_reason = " ".join(words[:24]) + "..."

                    results[target_job.job_id] = AIEvaluationResult(
                        is_suitable=bool(item.get("is_suitable", False)),
                        fit_score=float(item.get("fit_score", 0.0)),
                        seniority_detected=str(item.get("seniority_detected", "Desconhecido")),
                        reasoning=raw_reason,
                        pros=list(item.get("pros", [])),
                        cons=list(item.get("cons", []))
                    )

        except Exception as e:
            logger.error(f"Failed processing AI evaluations data: {e}")

        return results

    def _build_batch_prompt(self, batch: List[Job], profile: CandidateProfile) -> str:
        tech_stack_str = ", ".join(profile.tech_stack)
        languages_str = ", ".join(profile.languages)

        jobs_text_list = []
        for idx, job in enumerate(batch):
            jobs_text_list.append(f"""
[VAGA INDEX: {idx}]
- Título: {job.title}
- Empresa: {job.company}
- Localização: {job.location}
- Fonte: {job.source}
- Descrição:
\"\"\"
{job.description[:1200]}
\"\"\"
""")


        all_jobs_str = "\n---\n".join(jobs_text_list)

        return f"""
És especialista em recrutamento em Tecnologia (IA, Data Science, Engenharia de Dados e Software).
Avalia as seguintes {len(batch)} vagas no lote em relação ao perfil do candidato.

PERFIL DO CANDIDATO:
- Nome: {profile.name}
- Formação: {profile.degree}
- Nível de Experiência: Júnior / Recém-licenciado (0 a 1 ano de experiência)
- Elegível para Estágio IEFP / ATIVAR.pt: {"Sim" if profile.iefp_eligible else "Não"}
- Idiomas: {languages_str}
- Stack Técnica & Competências: {tech_stack_str}

VAGAS NO LOTE A AVALIAR:
{all_jobs_str}

REGRAS DE AVALIAÇÃO PARA CADA VAGA:
1. Nível de Senioridade e Experiência:
   - O candidato é Júnior / Recém-licenciado com sólida formação e projetos práticos (0 a 1 ano de experiência profissional).
   - Em Portugal e no setor tecnológico, termos como "experienced", "proven experience", "experiência em desenvolvimento", "conhecimento prático" ou "1 a 2 anos" referem-se a projetos académicos ou estágio inicial. NÃO rejeites vagas júnior apenas por usarem a palavra "experienced" ou por pedirem até 2 anos de experiência.
   - REJEIÇÃO OBRIGATÓRIA DE SÉNIOR (+3 / +5 / 8+ ANOS): Se a vaga exigir expressamente 3+ anos, 4+ anos, 5+ anos, 8+ anos, "8 or more years", "+5 years", ou cargos de liderança (Lead, Senior, Principal, Head, Gestor, Staff, redes freelancer sénior como Toptal), DEVES OBRIGATORIAMENTE REJEITÁ-LA (`is_suitable: false`, `fit_score: 0`, `seniority_detected: "Sénior"` ou `"Mid-Senior"`, `reasoning: "❌ Rejeitada por IA: Exige 8+ anos de experiência profissional"`).
   - ATENÇÃO A GRAUS ACADÉMICOS: A menção de "Degree / Master for graduates" refere-se apenas a formação universitária e NÃO torna uma vaga júnior se a mesma exigir simultaneamente anos de experiência prévia (+3 / +5 / +8 anos).
   - Se a vaga NÃO exigir 3+ ou 5+ ou 8+ anos e for de nível de entrada/júnior/pleno acessível, deves considerá-la ADEQUADA (`is_suitable: true`, `seniority_detected: "Júnior"` ou `"Recém-licenciado"`, `fit_score: 65% a 90%`).
2. Adequação da Área e Tipo de Oportunidade: A vaga deve ser um emprego formal ou estágio técnico (IA, Machine Learning, Data Science, Data Engineering, Python Developer). Rejeita OBRIGATORIAMENTE oportunidades de crowdsourcing/microtarefas/gravação doméstica (Toloka, Appen, Outlier, Remotasks, "not a job", "record daily routine"), cargos de gestão/liderança comercial, e posições com remuneração de nível Sénior/Staff ($120k–$250k+ USD) (`is_suitable: false`, `fit_score: 0`).
3. Alinhamento Obrigatório com a Stack do Candidato ({tech_stack_str}):
   - O candidato é especializado em PYTHON, IA GENERATIVA / LLMs / RAG, MACHINE LEARNING, DATA SCIENCE e DATA ENGINEERING.
   - REJEIÇÃO OBRIGATÓRIA DE OUTRAS STACKS TECNOLÓGICAS: Se a vaga de desenvolvimento exigir primariamente outras linguagens (ex: Go/Golang, Ruby/Rails, PHP, C#/.NET, Java/Spring, Swift/iOS, Kotlin/Android, Rust, C++, ou Frontend puro React/Vue/Angular) e NÃO incluir Python nem componente de IA/Dados, DEVES OBRIGATORIAMENTE REJEITÁ-LA (`is_suitable: false`, `fit_score: 0`, `reasoning: "❌ Rejeitada por IA: Stack incompatível sem foco em Python/IA/Dados"`). NUNCA inventes que uma vaga de Go/TypeScript tem 'forte base em Python' se Python não constar do anúncio!
   - Se a vaga tiver sobreposição real com a stack do candidato (Python, SQL, ML, IA, FastAPI, Docker), atribui pontuação de 65% a 95%.
4. Línguas: O candidato domina Português (Nativo) e Inglês (Fluente/C2), mas NÃO domina Alemão (nível básico A2) nem Francês/Holandês/Espanhol. Se a vaga exigir expressamente Alemão fluente/profissional/nativo (ex: "verhandlungssicher auf Deutsch", "Deutsch C1/B2", "fließende Deutschkenntnisse", "in Wort und Schrift", termos como Praktikant/Werkstudent/(m/w/d) em empresas da Alemanha sem opção 100% em inglês) ou Francês/Holandês, deves OBRIGATORIAMENTE REJEITÁ-LA (`is_suitable: false`, `fit_score: 0`, `reasoning: "❌ Rejeitada por IA: Exige Alemão fluente/profissional (C1) obrigatório"`).
5. Localização/Residência: O candidato reside em Portugal. Se a vaga for presencial noutro país ou tiver restrição geográfica remota exclusiva para residentes noutros países/regiões (ex: EUA, Reino Unido, LATAM, Brasil, México, Peru, Chile, Canadá, Índia, APAC, fuso horário EST/PST sem opção para Portugal/Europa), deves OBRIGATORIAMENTE REJEITÁ-LA (`is_suitable: false`, `fit_score: 0`, `reasoning: "❌ Rejeitada por IA: Vaga remota com restrição geográfica a outros países"`).
6. Atribui uma pontuação de adequação (`fit_score`) de 0 a 100%. Vagas adequadas para júnior devem ter pontuação entre 60% e 95%.
7. Justificação (reasoning):
   - Se for ADEQUADA (`is_suitable: true`): explica de forma concisa em Português o motivo do bom alinhamento (ex: "Forte sobreposição em Python e GenAI para nível júnior").
   - Se for DESQUALIFICADA (`is_suitable: false`): explica OBRIGATORIAMENTE e de forma CONCRETA o obstáculo factual que levou à rejeição (ex: "Exige 5+ anos de experiência e liderança de equipa", "Função de Vendas/Comercial sem componente técnica", "Exige Alemão fluente obrigatório", "Restrição geográfica exclusiva para residentes em LATAM / EUA").

Responde APENAS em formato JSON válido contendo um objeto com uma lista "evaluations", onde cada elemento corresponde ao `job_index`:
{{
  "evaluations": [
    {{
      "job_index": 0,
      "is_suitable": boolean,
      "fit_score": number,
      "seniority_detected": string (ex: "Júnior", "Recém-licenciado", "Mid-Senior", "Sénior"),
      "reasoning": string (frase concisa em Português com 10 a 20 palavras a justificar a adequação ou o motivo factual concreto da rejeição),

      "pros": array de strings,
      "cons": array de strings
    }}, ...
  ]
}}
"""
