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


if __name__ == "__main__":
    unittest.main()
