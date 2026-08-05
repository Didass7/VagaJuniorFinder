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
from report_builder import ReportBuilder


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
        self.assertTrue("IEFP" in scored.seniority_status or "Junior" in scored.seniority_status)

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


class TestReportBuilderModule(unittest.TestCase):
    """Unit tests for Markdown and HTML report generation."""

    def setUp(self):
        self.builder = ReportBuilder(profile=config.candidate)
        self.matcher = JobMatcher(profile=config.candidate)

    def test_markdown_report_building(self):
        job = Job(
            title="Junior Data Analyst",
            company="Analytics Ltd",
            location="Porto",
            work_mode="Híbrido",
            link="https://example.com/analyst",
            description="Procuramos Junior Data Analyst com conhecimento em Python, SQL e Pandas. Estágio IEFP para recém-licenciados com mais de 120 caracteres de texto.",
            source="Test",
            pub_date="2026-08-05"
        )
        scored_jobs = self.matcher.process_jobs([job])
        md_content = self.builder.build_markdown(scored_jobs=scored_jobs, seen_jobs=[])
        
        self.assertIn("Relatório Diário de Vagas", md_content)
        self.assertIn("Diogo Oliveira", md_content)
        self.assertIn("Junior Data Analyst", md_content)

    def test_telegram_html_building(self):
        job = Job(
            title="Junior AI Developer",
            company="AI Startup",
            location="Lisboa",
            work_mode="Remoto",
            link="https://example.com/ai-dev",
            description="Oportunidade em Python e LangChain para desenvolvimento de pipelines RAG com mais de 120 caracteres de descrição completa de vaga de emprego.",
            source="Test",
            pub_date="2026-08-05"
        )
        scored_jobs = self.matcher.process_jobs([job])
        html_content = self.builder.build_telegram_html(scored_jobs=scored_jobs, seen_jobs=[])
        
from excel_builder import ExcelReportBuilder

class TestExcelBuilderModule(unittest.TestCase):
    """Unit tests for Excel report generation and master database tracking."""

    def setUp(self):
        self.excel_builder = ExcelReportBuilder(profile=config.candidate)
        self.matcher = JobMatcher(profile=config.candidate)

    def test_excel_daily_report_generation(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            job = Job(
                title="Junior AI Engineer",
                company="Innovate AI",
                location="Lisboa",
                work_mode="Híbrido",
                link="https://example.com/ai-excel",
                description="Desenvolvimento RAG com Python, LangChain, FastAPI e DuckDB. Elegível para estágio IEFP com mais de 120 caracteres.",
                source="Test",
                pub_date="2026-08-05"
            )
            scored_jobs = self.matcher.process_jobs([job])
            report_path = self.excel_builder.build_daily_report(scored_jobs, output_dir=tmp_dir)
            
            self.assertTrue(os.path.exists(report_path))
            self.assertTrue(report_path.endswith(".xlsx"))
            
            # Load created workbook to verify sheets
            wb = openpyxl.load_workbook(report_path)
            self.assertIn("🎯 Top Vagas (≥75%)", wb.sheetnames)
            self.assertIn("💡 Vagas Promissoras (55-74%)", wb.sheetnames)
            self.assertIn("🗂️ Todas as Vagas Evaluated", wb.sheetnames)

    def test_excel_master_database_update(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            master_path = os.path.join(tmp_dir, "test_database.xlsx")
            job = Job(
                title="Data Scientist",
                company="Data Co",
                location="Porto",
                work_mode="Remoto",
                link="https://example.com/ds-excel",
                description="Data Science com Python, SQL, Pandas e Scikit-learn com mais de 120 caracteres de texto.",
                source="Test",
                pub_date="2026-08-05"
            )
            scored_jobs = self.matcher.process_jobs([job])
            saved_path = self.excel_builder.update_master_database(scored_jobs, master_filepath=master_path)
            
            self.assertTrue(os.path.exists(saved_path))
            wb = openpyxl.load_workbook(saved_path)
            self.assertIn("🗃️ Base de Dados Master", wb.sheetnames)


if __name__ == "__main__":
    unittest.main()

