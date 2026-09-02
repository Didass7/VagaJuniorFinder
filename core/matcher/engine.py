from __future__ import annotations
import logging
from typing import List, Optional
import datetime

from scrapers import Job
from core.config import CandidateProfile, config
from core.ai_evaluator import AIEvaluator
from core.matcher.scoring import ScoredJob, clean_analysis_text, calculate_score
from core.matcher.filtering import check_hard_disqualifiers
from core.matcher.rules import COMPANY_HISTORY_PATTERN, PORTUGAL_LOCATIONS

logger = logging.getLogger("Matcher")

class JobMatcher:
    def __init__(
        self,
        profile: CandidateProfile,
        ai_evaluator: Optional[AIEvaluator] = None,
        enable_ai: Optional[bool] = None,
        promising_threshold: Optional[float] = None,
        min_blended_score: Optional[float] = None,
        ai_batch_size: Optional[int] = None
    ):
        self.profile = profile
        should_enable = enable_ai if enable_ai is not None else config.enable_ai_evaluation
        if not should_enable:
            self.ai_evaluator = None
        elif ai_evaluator is not None:
            self.ai_evaluator = ai_evaluator
        else:
            self.ai_evaluator = AIEvaluator()

        self.promising_threshold = promising_threshold if promising_threshold is not None else getattr(config, "promising_match_threshold", 55.0)
        self.min_blended_score = min_blended_score if min_blended_score is not None else getattr(config, "min_blended_score", 50.0)
        self.ai_batch_size = ai_batch_size if ai_batch_size is not None else getattr(config, "ai_batch_size", 4)

    def evaluate_job(self, job: Job) -> ScoredJob:
        text = COMPANY_HISTORY_PATTERN.sub(" ", f"{job.title} {job.location} {job.description}").lower()
        title_lower = job.title.lower()
        location_lower = job.location.lower()
        work_mode_lower = job.work_mode.lower()

        clean_desc = COMPANY_HISTORY_PATTERN.sub(" ", job.description).strip()
        clean_desc_lower = clean_desc.lower()
        
        profile_locs = [l.lower() for l in getattr(self.profile, 'locations', []) if l.lower() not in ["remoto", "remote", "hybrid", "híbrido", "hibrido"]]
        allowed_locations = set(PORTUGAL_LOCATIONS + profile_locs)
        is_portugal = any(loc in location_lower for loc in allowed_locations) or ("portugal" in text) or any(loc in text for loc in profile_locs if len(loc) > 3)
        has_onsite_override = any(term in f"{title_lower} {location_lower}".lower() for term in ["on-site", "onsite", "presencial", "in-office", "berlin", "germany", "madrid", "london", "paris"]) and not is_portugal
        is_strictly_remote = ((work_mode_lower == "remoto") or ("remoto" in location_lower) or ("remote" in location_lower) or ("teletrabalho" in location_lower)) and not has_onsite_override

        target_titles_lower = [t.lower() for t in self.profile.target_titles]
        tech_stack_lower = [t.lower() for t in self.profile.tech_stack]
        has_target_title = any(tt in title_lower for tt in target_titles_lower)
        has_tech_in_title = any(ts in title_lower for ts in tech_stack_lower)

        disqualified = check_hard_disqualifiers(job, self.profile, text, clean_desc_lower, title_lower, location_lower, work_mode_lower, is_portugal, is_strictly_remote, has_target_title, has_tech_in_title)
        if disqualified:
            return disqualified

        is_explicit_junior = any(j_term in title_lower for j_term in ["junior", "jr", "estágio", "estagio", "trainee", "graduate program", "entry level", "intern"])
        is_explicit_zero_to_one = any(b in text for b in ["recém-licenciado", "recem licenciado", "recém licenciado", "0-1", "recent graduate", "fresh graduate", "recém-graduado", "recem-graduado", "0 a 1 ano", "0 to 1 year"])
        has_verified_junior_indicator = is_explicit_junior or job.iefp_mentioned or is_explicit_zero_to_one

        score_comps = calculate_score(job, self.profile, text, title_lower, location_lower, work_mode_lower, is_portugal, is_strictly_remote, has_target_title, has_tech_in_title, is_explicit_junior, is_explicit_zero_to_one, has_verified_junior_indicator)

        raw_score = score_comps.title_score + score_comps.booster_score + score_comps.location_score + score_comps.tech_score
        
        if not has_verified_junior_indicator:
            final_score = min(65.0, raw_score)
        else:
            final_score = min(100.0, raw_score)

        reason_parts = []
        if score_comps.preferred_loc_match:
            bonus = getattr(self.profile, 'preferred_location_bonus', 15.0)
            reason_parts.append(f"Localização Preferencial ({score_comps.preferred_loc_name}) (+{bonus:.0f} pts)")
        if score_comps.matched_skills:
            reason_parts.append(f"Skills: {', '.join(score_comps.matched_skills)}")
        else:
            reason_parts.append("Skills: Nenhuma")

        return ScoredJob(
            job=job,
            score=round(final_score, 1),
            matched_skills=score_comps.matched_skills,
            missing_skills=[],
            seniority_status=score_comps.seniority_status,
            match_reason=f"Avaliação Heurística. {' | '.join(reason_parts)}."
        )

    def process_jobs(self, jobs: List[Job], include_disqualified: bool = False) -> List[ScoredJob]:
        heuristic_candidates: List[ScoredJob] = []
        disqualified_jobs: List[ScoredJob] = []
        for job in jobs:
            evaluated = self.evaluate_job(job)
            if evaluated.score >= self.promising_threshold:
                heuristic_candidates.append(evaluated)
            else:
                disqualified_jobs.append(evaluated)

        if not heuristic_candidates:
            return disqualified_jobs if include_disqualified else []

        if self.ai_evaluator and self.ai_evaluator.is_available:
            logger.info(f"🤖 Stage 2: AI Evaluator ACTIVE ({self.ai_evaluator.active_provider}). Evaluating {len(heuristic_candidates)} candidate jobs...")
            candidate_jobs = [sj.job for sj in heuristic_candidates]
            ai_results = self.ai_evaluator.evaluate_jobs_batch(candidate_jobs, self.profile, batch_size=self.ai_batch_size)

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
                    
                    if not ai_res.is_suitable or ai_res.fit_score == 0 or is_clearly_senior or is_demanding_3plus_years:
                        sj.score = 0.0
                        sj.seniority_status = f"Rejeitada por IA ({ai_res.seniority_detected or 'Inadequada'})"
                        sj.match_reason = clean_reason
                        sj.ai_reasoning = f"Rejeitada por IA: {clean_reason}"
                        ai_rejected += 1
                        if include_disqualified:
                            final_scored_jobs.append(sj)
                        continue

                    blended_score = round(0.5 * sj.score + 0.5 * ai_res.fit_score, 1)
                    if blended_score < self.min_blended_score:
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
