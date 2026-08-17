import unittest
from config import CandidateProfile, config
from scraper import Job
from ai_evaluator import AIEvaluator, AIEvaluationResult
from matcher import JobMatcher, ScoredJob

class TestAIEvaluator(unittest.TestCase):
    def setUp(self):
        self.profile = config.candidate
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
            pub_date="2026-08-05"
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
            pub_date="2026-08-05"
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
            pub_date="2026-08-05"
        )
        
        with patch('time.sleep', return_value=None):
            res = evaluator._evaluate_batch_with_gemini([sample_job], self.profile)
            
        self.assertTrue(bool(res))
        self.assertIn("gemini-3.5-flash-lite", evaluator._invalid_gemini_models)
        self.assertEqual(evaluator._gemini_cooldown_until, 0.0)


if __name__ == "__main__":
    unittest.main()
