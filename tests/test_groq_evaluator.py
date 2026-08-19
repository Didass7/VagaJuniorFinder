import unittest
from ai_evaluator import AIEvaluator, AIEvaluationResult
from config import CandidateProfile, config
from scraper import Job

class TestGroqEvaluator(unittest.TestCase):
    def setUp(self):
        self.profile = CandidateProfile()

    def test_evaluator_provider_detection(self):
        evaluator = AIEvaluator(groq_api_key="mock_groq_key", gemini_api_key="")
        self.assertTrue(evaluator.is_available)
        self.assertIn("Groq", evaluator.active_provider)

    def test_fallback_provider_detection(self):
        evaluator = AIEvaluator(groq_api_key="", gemini_api_key="mock_gemini_key")
        self.assertTrue(evaluator.is_available)
        self.assertIn("Gemini", evaluator.active_provider)

    def test_empty_keys(self):
        evaluator = AIEvaluator(groq_api_key="", gemini_api_key="")
        self.assertFalse(evaluator.is_available)

if __name__ == "__main__":
    unittest.main()
