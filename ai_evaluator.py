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
        self.groq_model_name = config.groq_model_name or "llama-3.1-8b-instant"
        
        self.gemini_api_key = gemini_api_key if gemini_api_key is not None else config.gemini_api_key
        self.gemini_model_name = config.ai_model_name or "gemini-2.5-flash"
        
        self._groq_client = None
        self._gemini_client = None
        
        if self.groq_api_key:
            try:
                from groq import Groq
                self._groq_client = Groq(api_key=self.groq_api_key)
                logger.info(f"🤖 Initialized Groq AI Evaluator with model '{self.groq_model_name}'")
            except Exception as e:
                logger.warning(f"Failed to initialize Groq Client: {e}")

        if not self._groq_client and self.gemini_api_key:
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
        if self._groq_client:
            return f"Groq ({self.groq_model_name})"
        elif self._gemini_client:
            return f"Gemini ({self.gemini_model_name})"
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
        
        # Split jobs into chunks of batch_size
        for i in range(0, len(jobs), batch_size):
            chunk = jobs[i : i + batch_size]
            chunk_results = self._process_single_batch(chunk, profile)
            results.update(chunk_results)

        return results

    def _process_single_batch(self, batch: List[Job], profile: CandidateProfile) -> Dict[str, AIEvaluationResult]:
        if self._groq_client:
            return self._evaluate_batch_with_groq(batch, profile)
        elif self._gemini_client:
            return self._evaluate_batch_with_gemini(batch, profile)
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

        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            time.sleep(5.0)  # Pacing delay between batch calls to stay strictly below 6000 TPM limit
            try:
                response = self._groq_client.chat.completions.create(
                    model=self.groq_model_name,
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
                    max_completion_tokens=2000
                )

                content = response.choices[0].message.content
                if not content:
                    return {}

                return self._parse_batch_json_response(content, batch)

            except Exception as e:
                err_str = str(e).lower()
                if "rate_limit" in err_str or "429" in err_str:
                    if self._gemini_client:
                        logger.warning("⏳ Groq 429 rate limit hit. Falling back immediately to Gemini API...")
                        return self._evaluate_batch_with_gemini(batch, profile)
                    backoff = 6 * attempt
                    logger.warning(f"⏳ Groq rate limit hit (attempt {attempt}/{max_attempts}). Waiting {backoff}s before retry...")
                    time.sleep(backoff)
                    continue

                logger.error(f"Error calling Groq Batch AI Evaluator: {e}")
                if self._gemini_client:
                    logger.info("Attempting batch fallback to Gemini API...")
                    return self._evaluate_batch_with_gemini(batch, profile)
                return {}

        return {}


    def _evaluate_batch_with_gemini(self, batch: List[Job], profile: CandidateProfile) -> Dict[str, AIEvaluationResult]:
        prompt = self._build_batch_prompt(batch, profile)
        try:
            from google.genai import types
            
            response = self._gemini_client.models.generate_content(
                model=self.gemini_model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.2,
                )
            )
            
            if not response.text:
                return {}

            return self._parse_batch_json_response(response.text, batch)

        except Exception as e:
            logger.error(f"Error calling Gemini Batch AI Evaluator: {e}")
            return {}

    def _parse_batch_json_response(self, raw_json: str, batch: List[Job]) -> Dict[str, AIEvaluationResult]:
        results: Dict[str, AIEvaluationResult] = {}
        try:
            cleaned_json = self._clean_and_extract_json(raw_json)
            data = json.loads(cleaned_json)
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
            logger.error(f"Failed to parse batch AI JSON response: {e}")

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
{job.description[:4000]}
\"\"\"
""")


        all_jobs_str = "\n---\n".join(jobs_text_list)

        return f"""
Es especialista em recrutamento em Tecnologia (IA, Data Science, Engenharia de Dados e Software).
Avalia as seguintes {len(batch)} vagas no lote em relação ao perfil do candidato.

PERFIL DO CANDIDATO:
- Nome: {profile.name}
- Formação: {profile.degree}
- Anos de Experiência: 0 a 1 ano (Recém-licenciado / Júnior)
- Elegível para Estágio IEFP / ATIVAR.pt: {"Sim" if profile.iefp_eligible else "Não"}
- Idiomas: {languages_str}
- Stack Técnica & Competências: {tech_stack_str}

VAGAS NO LOTE A AVALIAR:
{all_jobs_str}

REGRAS DE AVALIAÇÃO PARA CADA VAGA:
1. Nível de Senioridade: O candidato tem 0 anos de experiência profissional (é júnior / recém-licenciado). Se a descrição da vaga exigir experiência profissional prévia num cargo (ex: "Experience in data engineering role", "Demonstrated experience building...", "Experiência comprovada em..."), MESMO QUE não especifique o número de anos, a vaga NÃO é adequada (`is_suitable: false`, `fit_score: 0`). A vaga só é adequada se for explicitamente para posições Entry-Level, Estágio, Trainee, ou se aceitar recém-licenciados sem experiência profissional prévia.
2. Adequação da Área: A vaga deve ser estritamente técnica, focada em IA/ML, Engenharia de Dados ou Data Analytics. Vagas funcionais ou de negócio (Recursos Humanos/HR, Marketing, Vendas, Analista de Negócios) que não requeiram programação (Python, SQL) NÃO servem (`is_suitable: false`, `fit_score: 0`).
3. Línguas: Exigência de Alemão/Francês fluente é eliminatória (`is_suitable: false`, `fit_score: 0`).
4. Atribui uma pontuação de adequação (`fit_score`) de 0 a 100%. Se a vaga exigir experiência prévia, o `fit_score` deve ser ZERO.

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
