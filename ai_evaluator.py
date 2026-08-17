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
        self.gemini_model_name = config.ai_model_name or "gemini-3.6-flash"
        
        self._groq_client = None
        self._gemini_client = None
        self._gemini_cooldown_until: float = 0.0
        self._groq_cooldown_until: float = 0.0
        
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
        for attempt in range(1, 4):
            now = time.time()
            gemini_ready = self._gemini_client is not None and now >= self._gemini_cooldown_until
            groq_ready = self._groq_client is not None and now >= self._groq_cooldown_until

            # If both engines are currently in rate-limit cooldown, pause until the earliest resets
            if not gemini_ready and not groq_ready and (self._gemini_client or self._groq_client):
                wait_sec = 20.0
                if self._gemini_client and self._groq_client:
                    wait_sec = max(5.0, min(self._gemini_cooldown_until - now, self._groq_cooldown_until - now))
                elif self._gemini_client:
                    wait_sec = max(5.0, self._gemini_cooldown_until - now)
                elif self._groq_client:
                    wait_sec = max(5.0, self._groq_cooldown_until - now)
                
                logger.info(f"⏳ Both AI engines (Gemini/Groq) in rate-limit cooldown. Pausing {int(wait_sec)}s before next evaluation...")
                time.sleep(wait_sec)
                now = time.time()
                gemini_ready = self._gemini_client is not None and now >= self._gemini_cooldown_until
                groq_ready = self._groq_client is not None and now >= self._groq_cooldown_until

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
        groq_candidates = list(dict.fromkeys([
            self.groq_model_name,
            "openai/gpt-oss-120b",
            "openai/gpt-oss-20b",
            "qwen/qwen-3.6-27b"
        ]))

        for model in groq_candidates:
            try:
                time.sleep(1.0)  # Polite delay between calls
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
                    return parsed
            except Exception as e:
                err_str = str(e).lower()
                if "rate_limit" in err_str or "429" in err_str:
                    logger.warning(f"⏳ Groq rate limited (429). Setting Groq cooldown for 60s...")
                    self._groq_cooldown_until = time.time() + 60.0
                    return {}
                else:
                    logger.warning(f"Groq model '{model}' issue ({e}). Trying next Groq model...")
                    continue

        return {}

    def _evaluate_batch_with_gemini(self, batch: List[Job], profile: CandidateProfile) -> Dict[str, AIEvaluationResult]:
        prompt = self._build_batch_prompt(batch, profile)
        gemini_candidates = list(dict.fromkeys([
            self.gemini_model_name,
            "gemini-3.6-flash"
        ]))

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
                    return parsed
            except Exception as e:
                err_str = str(e).lower()
                if "429" in err_str or "resource_exhausted" in err_str or "quota" in err_str:
                    logger.warning(f"⏳ Gemini quota limit reached (429). Setting Gemini cooldown for 60s...")
                    self._gemini_cooldown_until = time.time() + 60.0
                    return {}
                else:
                    logger.warning(f"⚠️ Gemini model '{model}' issue ({e}). Trying next candidate...")
                    continue

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
                    if len(words) > 11:
                        raw_reason = " ".join(words[:10]) + "..."

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
1. Nível de Senioridade: O candidato é Júnior / Recém-licenciado (0 a 1 ano de experiência). Em Portugal, muitas vagas de nível Júnior/Entrada indicam '1 a 2 anos' ou 'experiência valorizada' como preferência, mas contratam e entrevistam recém-licenciados com base em projetos e formação. NÃO rejeites vagas júnior por mencionarem até 2 anos de experiência ou estágio. Apenas rejeita (`is_suitable: false`, `fit_score: 0`) se a vaga for claramente SÉNIOR / LIDERANÇA (3+ anos, 5+ anos, Lead, Principal, Gestor de Equipa).
2. Adequação da Área: A vaga deve ser técnica (IA, Machine Learning, Data Science, Data Engineering, Python Developer, Software Engineer). Rejeita apenas vagas puramente de negócio/administrativas (ex: Vendas, Marketing, Recursos Humanos, Contabilidade) que não envolvam desenvolvimento ou análise de dados (`is_suitable: false`).
3. Competências Técnicas: Avalia a sobreposição com a stack do candidato ({tech_stack_str}). Dá pontuação alta (70-95%) se a vaga usar Python, SQL, ML, IA, Docker ou FastAPI. Se a vaga pedir ferramentas adicionais como nice-to-have, pondera a pontuação sem rejeitar imediatamente.
4. Línguas: Exigência de Alemão/Francês/Holandês nativo ou fluente é eliminatória (`is_suitable: false`). Inglês e Português são suportados.
5. Localização/Residência: O candidato reside em Portugal. Se a vaga for presencial noutro país ou tiver restrição geográfica exclusiva para residentes nos EUA/UK, rejeita (`is_suitable: false`).
6. Atribui uma pontuação de adequação (`fit_score`) de 0 a 100%. Vagas adequadas para júnior devem ter pontuação entre 60% e 95%.

Responde APENAS em formato JSON válido contendo um objeto com uma lista "evaluations", onde cada elemento corresponde ao `job_index`:
{{
  "evaluations": [
    {{
      "job_index": 0,
      "is_suitable": boolean,
      "fit_score": number,
      "seniority_detected": string (ex: "Júnior", "Recém-licenciado", "Mid-Senior", "Sénior"),
      "reasoning": string (frase extremamente curta com no máximo 10 palavras em Português a justificar a adequação),

      "pros": array de strings,
      "cons": array de strings
    }}, ...
  ]
}}
"""
