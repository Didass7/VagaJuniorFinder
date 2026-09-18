import os
import json
import unittest
import datetime
from core.config import CandidateProfile, config
from scrapers import Job
from core.ai_evaluator import AIEvaluator, AIEvaluationResult
from core.matcher import JobMatcher, ScoredJob

FIXTURE_PROFILE = os.path.join(os.path.dirname(__file__), "fixtures", "ai_data_profile.json")

class TestAIEvaluator(unittest.TestCase):
    def setUp(self):
        # Fixed AI & Data test profile, independent of the real profiles/ (which change over time)
        with open(FIXTURE_PROFILE, "r", encoding="utf-8") as f:
            self.profile = CandidateProfile(**json.load(f)["candidate"])
        self.matcher = JobMatcher(self.profile)

    def test_mock_job_evaluation(self):
        sample_job = Job(
            title="Junior AI Engineer",
            company="TechCorp",
            location="Lisboa, Portugal",
            work_mode="Híbrido",
            description="Procuramos Junior AI Engineer recém-licenciado com conhecimentos em Python, SQL e LangChain/RAG para integrar projeto de GenAI. Estágio IEFP elegível.",
            link="https://example.com/job1",
            source="Test",
            pub_date=datetime.date.today().isoformat()
        )
        
        # Test Stage 1 Heuristic Evaluation
        scored = self.matcher.evaluate_job(sample_job)
        self.assertGreaterEqual(scored.score, 55.0)
        self.assertIn("python", scored.matched_skills)

    def test_ai_evaluator_availability(self):
        evaluator = AIEvaluator(groq_api_key="", gemini_api_key="")
        self.assertFalse(evaluator.is_available)

    def test_groq_decommissioned_model_pruning_and_429_cascade(self):
        """Verify that decommissioned Groq models are pruned and 429 cascades to the next candidate model."""
        from unittest.mock import MagicMock, patch
        evaluator = AIEvaluator(groq_api_key="mock_groq_key", gemini_api_key="")
        evaluator.groq_model_name = "llama-3.3-70b-versatile"

        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content='{"evaluations": [{"job_index": 0, "is_suitable": true, "fit_score": 85.0, "seniority_detected": "Júnior", "reasoning": "Perfil alinhado"}]}'))
        ]
        
        # 1st call: decommissioned error, 2nd call: 429 rate limit, 3rd call: success
        evaluator._groq_client.chat.completions.create = MagicMock(
            side_effect=[
                Exception("model_decommissioned: The model llama-3.3-70b-versatile is decommissioned"),
                Exception("429 rate_limit_exceeded: Rate limit reached for llama-3.1-8b-instant"),
                mock_response
            ]
        )
        
        sample_job = Job(
            title="Junior AI Engineer",
            company="TechCorp",
            location="Lisboa, Portugal",
            work_mode="Híbrido",
            description="Vaga para Júnior Python ML.",
            link="https://example.com/job1",
            source="Test",
            pub_date=datetime.date.today().isoformat()
        )
        
        with patch('time.sleep', return_value=None):
            res = evaluator._evaluate_batch_with_groq([sample_job], self.profile)
            
        self.assertTrue(bool(res))
        self.assertIn("llama-3.3-70b-versatile", evaluator._invalid_groq_models)
        self.assertEqual(evaluator._groq_cooldown_until, 0.0)

    def test_gemini_deprecated_model_pruning_and_429_cascade(self):
        """Verify that unavailable Gemini models are pruned and 429 cascades to the next candidate model."""
        from unittest.mock import MagicMock, patch
        evaluator = AIEvaluator(groq_api_key="", gemini_api_key="mock_gemini_key")
        
        mock_response = MagicMock()
        mock_response.text = '{"evaluations": [{"job_index": 0, "is_suitable": true, "fit_score": 90.0, "seniority_detected": "Júnior", "reasoning": "Perfil adequado"}]}'
        
        # 1st call: not found (deprecated/invalid), 2nd call: 429 quota, 3rd call: success
        evaluator._gemini_client.models.generate_content = MagicMock(
            side_effect=[
                Exception("404 models/gemini-old is not found for api version"),
                Exception("429 ResourceExhausted quota exceeded"),
                mock_response
            ]
        )
        
        sample_job = Job(
            title="Junior Data Engineer",
            company="DataCorp",
            location="Porto, Portugal",
            work_mode="Híbrido",
            description="Vaga para Júnior SQL e Python.",
            link="https://example.com/job2",
            source="Test",
            pub_date=datetime.date.today().isoformat()
        )
        
        with patch('time.sleep', return_value=None):
            res = evaluator._evaluate_batch_with_gemini([sample_job], self.profile)
            
        self.assertTrue(bool(res))
        self.assertIn("gemini-3.5-flash-lite", evaluator._invalid_gemini_models)
        self.assertEqual(evaluator._gemini_cooldown_until, 0.0)

    def test_gemini_preferred_over_groq_when_both_available(self):
        """Verify that Gemini is called first when both providers are available, and falls back to Groq if Gemini fails."""
        from unittest.mock import MagicMock, patch
        evaluator = AIEvaluator(groq_api_key="mock_groq", gemini_api_key="mock_gemini")

        sample_job = Job(
            title="Junior Data Engineer",
            company="DataCorp",
            location="Porto, Portugal",
            work_mode="Híbrido",
            description="Vaga para Júnior SQL e Python.",
            link="https://example.com/job3",
            source="Test",
            pub_date=datetime.date.today().isoformat()
        )

        # 1. When Gemini succeeds, Groq is not called
        mock_gemini_result = {
            sample_job.job_id: AIEvaluationResult(is_suitable=True, fit_score=88.0, seniority_detected="Júnior", reasoning="Match")
        }
        with patch.object(evaluator, '_evaluate_batch_with_gemini', return_value=mock_gemini_result) as mock_gem, \
             patch.object(evaluator, '_evaluate_batch_with_groq', return_value={}) as mock_groq:
            res = evaluator._process_single_batch([sample_job], self.profile)
            self.assertEqual(res, mock_gemini_result)
            mock_gem.assert_called_once()
            mock_groq.assert_not_called()

        # 2. When Gemini fails (returns empty), falls back to Groq
        mock_groq_result = {
            sample_job.job_id: AIEvaluationResult(is_suitable=True, fit_score=80.0, seniority_detected="Júnior", reasoning="Groq Match")
        }
        with patch.object(evaluator, '_evaluate_batch_with_gemini', return_value={}) as mock_gem, \
             patch.object(evaluator, '_evaluate_batch_with_groq', return_value=mock_groq_result) as mock_groq:
            res = evaluator._process_single_batch([sample_job], self.profile)
            self.assertEqual(res, mock_groq_result)
            mock_gem.assert_called_once()
            mock_groq.assert_called_once()

    def test_prompt_location_bonus_only_for_profiles_with_preferred_locations(self):
        """The preferred-location bonus rule uses the profile's own locations and is absent when it has none."""
        evaluator = AIEvaluator(groq_api_key="", gemini_api_key="")
        job = self._make_jobs(1)

        no_pref = CandidateProfile(name="Sem Preferência", target_titles=["SOC Analyst"])
        prompt = evaluator._build_batch_prompt(job, no_pref)
        self.assertNotIn("Alentejo", prompt)
        self.assertNotIn("zonas de preferência", prompt)
        self.assertNotIn("localização preferencial", prompt)

        with_pref = CandidateProfile(name="Com Preferência", target_titles=["Web Developer"], preferred_locations=["braga", "guimarães"])
        prompt = evaluator._build_batch_prompt(job, with_pref)
        self.assertIn("zonas de preferência do candidato (braga, guimarães)", prompt)
        self.assertNotIn("Alentejo", prompt)

    def test_malformed_evaluation_item_does_not_drop_rest_of_batch(self):
        """Scores as text ("85%"), string indexes and string booleans are parsed; a bad item only skips itself."""
        evaluator = AIEvaluator(groq_api_key="", gemini_api_key="")
        jobs = self._make_jobs(3)
        raw = json.dumps({"evaluations": [
            {"job_index": 0, "is_suitable": "false", "fit_score": "85%", "seniority_detected": "Júnior", "reasoning": "a"},
            {"job_index": 2, "is_suitable": True, "fit_score": "alto", "reasoning": "c"},
            {"job_index": "1", "is_suitable": True, "fit_score": 70, "reasoning": "b", "pros": "Python"},
        ]})

        results = evaluator._parse_batch_json_response(raw, jobs)

        self.assertEqual(set(results), {jobs[0].job_id, jobs[1].job_id})
        self.assertEqual(results[jobs[0].job_id].fit_score, 85.0)
        self.assertFalse(results[jobs[0].job_id].is_suitable)
        self.assertEqual(results[jobs[1].job_id].fit_score, 70.0)
        self.assertEqual(results[jobs[1].job_id].pros, ["Python"])

    def _make_jobs(self, n):
        return [
            Job(
                title=f"Junior AI Engineer {i}", company=f"Corp{i}", location="Lisboa, Portugal",
                work_mode="Híbrido", link=f"https://example.com/rl{i}",
                description="Vaga para Júnior Python ML.", source="Test",
                pub_date=datetime.date.today().isoformat()
            )
            for i in range(n)
        ]

    def test_rate_limit_waits_for_cooldown_instead_of_skipping_batches(self):
        """After both providers hit a rate limit, the next batch waits out the cooldown and is still evaluated by AI."""
        import time
        from unittest.mock import MagicMock, patch
        evaluator = AIEvaluator(groq_api_key="", gemini_api_key="")
        evaluator._gemini_client = MagicMock()
        evaluator._groq_client = MagicMock()
        calls = {"gemini": 0}

        def gemini(batch, profile):
            calls["gemini"] += 1
            if calls["gemini"] == 1:
                evaluator._gemini_cooldown_until = time.time() + 60.0
                return {}
            return {j.job_id: AIEvaluationResult(is_suitable=True, fit_score=80.0, seniority_detected="Júnior", reasoning="ok") for j in batch}

        def groq(batch, profile):
            evaluator._groq_cooldown_until = time.time() + 60.0
            return {}

        def fake_sleep(seconds):
            # Simulate the cooldown elapsing while we wait
            evaluator._gemini_cooldown_until = 0.0
            evaluator._groq_cooldown_until = 0.0

        with patch.object(evaluator, '_evaluate_batch_with_gemini', side_effect=gemini), \
             patch.object(evaluator, '_evaluate_batch_with_groq', side_effect=groq), \
             patch('time.sleep', side_effect=fake_sleep) as sleep_mock:
            results = evaluator.evaluate_jobs_batch(self._make_jobs(12), self.profile, batch_size=4)

        # Batch 1 failed; batches 2 and 3 waited for the cooldown and were evaluated
        self.assertEqual(len(results), 8)
        self.assertTrue(any(call.args[0] > 5.0 for call in sleep_mock.call_args_list))

    def test_consecutive_failed_batches_stop_ai_calls(self):
        """When the AI keeps failing (e.g. daily quota exhausted), evaluation stops after the circuit-breaker limit."""
        from unittest.mock import patch
        from core.ai_evaluator import MAX_CONSECUTIVE_FAILED_BATCHES
        evaluator = AIEvaluator(groq_api_key="", gemini_api_key="mock_gemini")

        with patch.object(evaluator, '_process_single_batch', return_value={}) as batch_mock:
            results = evaluator.evaluate_jobs_batch(self._make_jobs(40), self.profile, batch_size=4)

        self.assertEqual(results, {})
        self.assertEqual(batch_mock.call_count, MAX_CONSECUTIVE_FAILED_BATCHES)

    def test_jobs_without_ai_verdict_are_pending_not_heuristic_passes(self):
        """If AI is enabled but gives no verdict, jobs are returned as pending instead of passing on heuristics."""
        from unittest.mock import patch
        evaluator = AIEvaluator(groq_api_key="", gemini_api_key="mock_gemini")
        matcher = JobMatcher(self.profile, ai_evaluator=evaluator, enable_ai=True)
        job = Job(
            title="Junior AI Engineer", company="TechCorp", location="Lisboa, Portugal", work_mode="Híbrido",
            description="Procuramos Junior AI Engineer recém-licenciado com conhecimentos em Python, SQL e LangChain/RAG para integrar projeto de GenAI. Estágio IEFP elegível.",
            link="https://example.com/pending1", source="Test", pub_date=datetime.date.today().isoformat()
        )

        with patch.object(evaluator, 'evaluate_jobs_batch', return_value={}):
            res = matcher.process_jobs([job])

        self.assertEqual(len(res), 1)
        self.assertTrue(res[0].ai_pending)
        self.assertFalse(res[0].ai_evaluated)
        self.assertEqual(res[0].seniority_status, "Avaliação IA Pendente")


if __name__ == "__main__":
    unittest.main()
