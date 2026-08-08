import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import tempfile
import unittest
import openpyxl
from config import config, CandidateProfile
from scraper import (
    Job, is_valid_job_offer,
    LinkedInScraper, ITJobsScraper, LandingJobsScraper, RemotiveScraper,
    ArbeitnowScraper, WeWorkRemotelyScraper, RemoteOKScraper, CargaDeTrabalhosScraper,
    JobicyScraper, HimalayasScraper, NetEmpregosScraper, TeamlyzerScraper,
    JobspressoScraper, EuraxessScraper, JobIngestionPipeline
)
from matcher import JobMatcher
from seen_store import SeenStore


class TestScraperModule(unittest.TestCase):
    """Unit tests for job validation, Job model instantiation, and scrapers."""

    def test_is_valid_job_offer(self):
        # Blog/doc links should be rejected
        self.assertFalse(is_valid_job_offer("https://medium.com/article-123", "Introduction to Python"))
        self.assertFalse(is_valid_job_offer("https://aws.amazon.com/what-is-ai", "What is Machine Learning"))
        
        # Non-AI/Data titles should be rejected
        self.assertFalse(is_valid_job_offer("https://company.com/job/1", "Senior Frontend React Developer"))
        self.assertFalse(is_valid_job_offer("https://company.com/job/2", "QA Tester & Automation"))
        
        # Valid AI/Data job offers should pass
        self.assertTrue(is_valid_job_offer("https://company.com/job/3", "Junior AI Engineer"))
        self.assertTrue(is_valid_job_offer("https://company.com/job/4", "Estágio Data Scientist - IEFP"))

    def test_job_dataclass_hash_and_iefp(self):
        job1 = Job(
            title="Junior Data Scientist",
            company="Tech Corp",
            location="Lisboa",
            work_mode="Presencial",
            link="https://example.com/job1",
            description="Vaga para recém-licenciado com bolsa de estágio profissional IEFP em Python e SQL com mais de 120 caracteres de detalhe de descrição exigida pelo matcher.",
            source="Test",
            pub_date="2026-08-05"
        )
        # Check automatic job_id SHA-256 hash generation
        self.assertTrue(len(job1.job_id) == 16)
        
        # Check IEFP detection logic
        self.assertTrue(job1.iefp_mentioned)

        # Check work_mode fallback inference
        job2 = Job(
            title="AI Developer",
            company="Remote Inc",
            location="Unknown",
            work_mode="",
            link="https://example.com/job2",
            description="Trabalho 100% remoto em qualquer parte do mundo com pelo menos 120 caracteres de descrição completa para ser uma vaga válida.",
            source="Test",
            pub_date="2026-08-05"
        )
        self.assertEqual(job2.work_mode, "Remoto")

    def test_scrapers_instantiation(self):
        """Verifies that all 14 scrapers can be instantiated without errors."""
        scrapers = [
            LinkedInScraper(), ITJobsScraper(), LandingJobsScraper(),
            RemotiveScraper(), ArbeitnowScraper(), WeWorkRemotelyScraper(),
            RemoteOKScraper(), CargaDeTrabalhosScraper(), JobicyScraper(),
            HimalayasScraper(), NetEmpregosScraper(), TeamlyzerScraper(),
            JobspressoScraper(), EuraxessScraper()
        ]
        self.assertEqual(len(scrapers), 14)
        for s in scrapers:
            self.assertTrue(hasattr(s, "fetch"))


class TestMatcherModule(unittest.TestCase):
    """Unit tests for candidate profile matching and scoring logic."""

    def setUp(self):
        self.matcher = JobMatcher(profile=config.candidate)

    def test_junior_ai_job_scoring(self):
        job = Job(
            title="Junior AI Engineer",
            company="Innovate AI",
            location="Lisboa",
            work_mode="Híbrido",
            link="https://example.com/ai-jr",
            description="Procuramos Junior AI Engineer para desenvolver pipelines RAG com Python, LangChain, FastAPI e DuckDB. Elegível para estágio profissional IEFP e recém-licenciado.",
            source="Test",
            pub_date="2026-08-05"
        )
        scored_jobs = self.matcher.process_jobs([job])
        self.assertEqual(len(scored_jobs), 1)
        scored = scored_jobs[0]
        
        # Score should be positive due to title match and tech stack overlap
        self.assertGreater(scored.score, 50.0)
        self.assertIn("python", scored.matched_skills)
        self.assertTrue("IEFP" in scored.seniority_status or "Junior" in scored.seniority_status or "Recém-licenciado" in scored.seniority_status or "Júnior" in scored.seniority_status)


    def test_senior_disqualification(self):
        job = Job(
            title="Senior Lead Data Scientist (10+ years exp)",
            company="Big Corp",
            location="Porto",
            work_mode="Presencial",
            link="https://example.com/senior-ds",
            description="Requer 10 anos de experiência em gestão de equipas de Data Science com mais de 120 caracteres de descrição completa.",
            source="Test",
            pub_date="2026-08-05"
        )
        scored_jobs = self.matcher.process_jobs([job])
        self.assertEqual(len(scored_jobs), 0)

    def test_responsavel_5_anos_disqualification(self):
        """Verifies that management/lead roles (e.g. Responsável) requiring 5 years exp are strictly disqualified."""
        job = Job(
            title="Responsável pela Transformação Digital, Automação e Inteligência Artificial",
            company="Empresa via Net-Empregos",
            location="Portugal",
            work_mode="Presencial / Híbrido",
            link="https://www.net-empregos.com/15787371/responsavel-pela-transformacao-digital-automacao-e-inteligencia-artificial/",
            description="Responsável pela Transformação Digital, Automação e Inteligência Artificial. Experiência mínima de 5 anos em transformação digital de empresas.",
            source="Net-Empregos",
            pub_date="2026-08-05"
        )
        scored_jobs = self.matcher.process_jobs([job])
        self.assertEqual(len(scored_jobs), 0)

    def test_itsector_2_years_exp_disqualification(self):
        """Verifies that AI Engineer requiring minimum 2 years of professional experience is strictly disqualified."""
        job = Job(
            title="AI Engineer",
            company="ITSector",
            location="Castelo Branco, Castelo Branco, Portugal",
            work_mode="Presencial / Híbrido",
            link="https://pt.linkedin.com/jobs/view/ai-engineer-at-itsector-4448529944",
            description="Degree in Computer Engineering, Artificial Intelligence or similar; Minimum 2 years of professional experience developing AI-based solutions; Hands-on experience with state-of-the-art LLMs such as GPT.",
            source="LinkedIn",
            pub_date="2026-08-05"
        )
        scored_jobs = self.matcher.process_jobs([job])
        self.assertEqual(len(scored_jobs), 0)

    def test_teaching_formador_disqualification(self):
        """Verifies that Professor/Formador/Teaching roles are strictly disqualified."""
        job = Job(
            title="Recrutamos Formador(a) de Programming Fundamentals, Python & Machine Learning",
            company="Sharkcoders",
            location="Figueira da Foz",
            work_mode="Presencial",
            link="https://www.net-empregos.com/15034091/recrutamos-formador-a/",
            description="Procuramos um(a) Professor/a para dar aulas de programação, robótica e inteligência artificial a crianças e adolescentes com mais de 120 caracteres de texto.",
            source="Net-Empregos",
            pub_date="2026-08-05"
        )
    def test_generative_ai_video_specialist_disqualification(self):
        """Verifies that Generative AI Video Specialist / Multimedia roles are strictly disqualified."""
        job = Job(
            title="Generative AI Video Specialist",
            company="LOG OSCON LDA",
            location="Portugal",
            work_mode="100% Remoto",
            link="https://www.net-empregos.com/15792256/generative-ai-video-specialist/",
            description="Procuramos um Generative AI Video Specialist para criar prompts avançados de vídeo com IA usando ferramentas como Google Veo, Runway, Kling AI, Adobe After Effects e Premiere Pro com mais de 120 caracteres.",
            source="Net-Empregos",
            pub_date="2026-08-06"
        )
        scored_jobs = self.matcher.process_jobs([job])
        self.assertEqual(len(scored_jobs), 0)

    def test_proven_experience_disqualification(self):
        """Verifies that jobs requiring proven professional experience (e.g. Rumos Machine Learning Engineer) are strictly disqualified."""
        job = Job(
            title="Machine Learning Engineer",
            company="Rumos Consulting",
            location="Lisboa",
            work_mode="Presencial / Híbrido",
            link="https://www.net-empregos.com/15316798/machine-learning-engineer/",
            description="Formação superior em TI. Experiência profissional comprovada na automação de infraestrutura de Machine Learning e workloads de Generative AI com mais de 120 caracteres de texto.",
            source="Net-Empregos",
            pub_date="2026-08-06"
        )
        scored_jobs = self.matcher.process_jobs([job])
        self.assertEqual(len(scored_jobs), 0)


class TestSeenStoreModule(unittest.TestCase):
    """Unit tests for cache persistence and deduplication store."""

    def test_seen_store_filtering(self):
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w+", delete=False) as tmp:
            tmp.write("{}")
            tmp_path = tmp.name

        try:
            store = SeenStore(filepath=tmp_path)
            self.assertEqual(store.count, 0)

            job = Job(
                title="Python Developer", company="Test Co", location="Remote",
                work_mode="Remoto", link="https://test.com/1", description="Python SQL",
                source="Test", pub_date="2026-08-05"
            )
            
            # First time: job is new
            new_jobs = store.filter_new([job])
            self.assertEqual(len(new_jobs), 1)

            # Mark job as seen
            store.mark_seen([job.job_id])
            store.save()

            # Reload store from disk
            store_reloaded = SeenStore(filepath=tmp_path)
            self.assertTrue(store_reloaded.is_seen(job.job_id))
            
            # Second time: job is filtered out
            new_jobs_2 = store_reloaded.filter_new([job])
            self.assertEqual(len(new_jobs_2), 0)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)




from ai_evaluator import AIEvaluator
from notion_store import NotionStore
from scraper import clean_job_description

class TestRobustnessImprovements(unittest.TestCase):
    """Unit tests for robust JSON parsing, text truncation, and HTML cleaning."""

    def test_clean_job_description(self):
        html_input = "<div><h1>Title</h1><script>var x=1;</script><p>Text with <b>HTML</b> tags.</p></div>"
        cleaned = clean_job_description(html_input)
        self.assertNotIn("<script>", cleaned)
        self.assertNotIn("<b>", cleaned)
        self.assertIn("Title Text with HTML tags.", cleaned)

    def test_clean_and_extract_json(self):
        evaluator = AIEvaluator()
        raw_markdown = '```json\n{\n  "evaluations": [\n    {"job_index": 0, "is_suitable": true, "fit_score": 85}\n  ]\n}\n```'
        cleaned = evaluator._clean_and_extract_json(raw_markdown)
        self.assertTrue(cleaned.startswith("{"))
        self.assertTrue(cleaned.endswith("}"))

    def test_notion_truncate_text(self):
        long_str = "a" * 2500
        truncated = NotionStore._truncate_text(long_str, 1990)
        self.assertEqual(len(truncated), 1990)
        self.assertTrue(truncated.endswith("..."))


if __name__ == "__main__":
    unittest.main()

