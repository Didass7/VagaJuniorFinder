import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import datetime
import tempfile
import unittest
from config import config, CandidateProfile
from scraper import (
    Job, is_valid_job_offer,
    LinkedInScraper, ITJobsScraper, IndeedScraper, LandingJobsScraper, RemotiveScraper,
    ArbeitnowScraper, RemoteOKScraper, CargaDeTrabalhosScraper,
    JobicyScraper, NetEmpregosScraper,
    JobspressoScraper, EuraxessScraper,
    IEFPScraper, JobIngestionPipeline
)
from matcher import JobMatcher
from seen_store import SeenStore


class TestScraperModule(unittest.TestCase):
    """Unit tests for job validation, Job model instantiation, and scrapers."""

    def test_is_valid_job_offer(self):
        # Blog/doc links should be rejected
        self.assertFalse(is_valid_job_offer("https://medium.com/article-123", "Introduction to Python"))
        self.assertFalse(is_valid_job_offer("https://aws.amazon.com/what-is-ai", "What is Machine Learning"))
        
        # Non-tech administrative / sales noise should be rejected
        self.assertFalse(is_valid_job_offer("https://company.com/job/1", "Assistente de Marketing e Redes Sociais"))
        self.assertFalse(is_valid_job_offer("https://company.com/job/2", "Técnico Administrativo e Contabilidade"))
        
        # Valid tech job offers should pass
        self.assertTrue(is_valid_job_offer("https://company.com/job/3", "Junior AI Engineer"))
        self.assertTrue(is_valid_job_offer("https://company.com/job/4", "Estágio Data Scientist - IEFP"))
        self.assertTrue(is_valid_job_offer("https://company.com/job/5", "Junior Frontend React Developer"))
        self.assertTrue(is_valid_job_offer("https://company.com/job/6", "Junior DevOps & Cloud Engineer"))

    def test_job_dataclass_hash_and_iefp(self):
        job1 = Job(
            title="Junior Data Scientist",
            company="Tech Corp",
            location="Lisboa",
            work_mode="Presencial",
            link="https://example.com/job1",
            description="Vaga para recém-licenciado com bolsa de estágio profissional IEFP em Python e SQL com mais de 120 caracteres de detalhe de descrição exigida pelo matcher.",
            source="Test",
            pub_date=datetime.date.today().isoformat()
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
            pub_date=datetime.date.today().isoformat()
        )
        self.assertEqual(job2.work_mode, "Remoto")

    def test_scrapers_instantiation(self):
        """Verifies that all 15 active scrapers can be instantiated without errors."""
        from scraper import SapoScraper, TeamlyzerScraper
        scrapers = [
            LinkedInScraper(), ITJobsScraper(), IndeedScraper(), SapoScraper(), TeamlyzerScraper(),
            LandingJobsScraper(), RemotiveScraper(), ArbeitnowScraper(),
            RemoteOKScraper(), CargaDeTrabalhosScraper(), JobicyScraper(),
            NetEmpregosScraper(),
            JobspressoScraper(), EuraxessScraper(),
            IEFPScraper()
        ]
        self.assertEqual(len(scrapers), 15)
        for s in scrapers:
            self.assertTrue(hasattr(s, "fetch"))

    def test_indeed_html_parser(self):
        """Verifies that IndeedScraper parses job cards, links, companies, and work modes correctly."""
        scraper = IndeedScraper()
        html = '''
        <div class="job_seen_beacon">
            <h2 class="jobTitle"><a class="jcs-JobTitle" href="/viewjob?jk=indeed123"><span>Junior AI Engineer (Remote)</span></a></h2>
            <span data-testid="company-name">DataTech Solutions</span>
            <div data-testid="text-location">Lisboa, Portugal</div>
            <div class="job-snippet">Desenvolvimento de modelos com Python e Machine Learning 100% remoto.</div>
        </div>
        '''
        jobs = scraper._parse_indeed_html(html)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].title, "Junior AI Engineer (Remote)")
        self.assertEqual(jobs[0].company, "DataTech Solutions")
        self.assertEqual(jobs[0].location, "Lisboa, Portugal")
        self.assertEqual(jobs[0].work_mode, "Remoto")
        self.assertEqual(jobs[0].link, "https://pt.indeed.com/viewjob?jk=indeed123")
        self.assertEqual(jobs[0].source, "Indeed")

    def test_scrapers_package_modular_exports(self):
        """Verifies direct imports from the scrapers/ package and BaseScraper inheritance."""
        import scrapers
        from scrapers.base import BaseScraper
        from scrapers.pipeline import JobIngestionPipeline
        from scrapers.itjobs import ITJobsScraper as DirectITJobsScraper

        self.assertTrue(issubclass(DirectITJobsScraper, BaseScraper))
        self.assertTrue(hasattr(scrapers, "JobIngestionPipeline"))
        self.assertTrue(hasattr(scrapers, "Job"))
        self.assertTrue(hasattr(scrapers, "clean_job_description"))


class TestMatcherModule(unittest.TestCase):
    """Unit tests for candidate profile matching and scoring logic."""

    def setUp(self):
        self.matcher = JobMatcher(profile=config.candidate, enable_ai=False)

    def test_junior_ai_job_scoring(self):
        job = Job(
            title="Junior AI Engineer",
            company="Innovate AI",
            location="Lisboa",
            work_mode="Híbrido",
            link="https://example.com/ai-jr",
            description="Procuramos Junior AI Engineer para desenvolver pipelines RAG com Python, LangChain, FastAPI e DuckDB. Elegível para estágio profissional IEFP e recém-licenciado.",
            source="Test",
            pub_date=datetime.date.today().isoformat()
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
            pub_date=datetime.date.today().isoformat()
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
            pub_date=datetime.date.today().isoformat()
        )
        scored_jobs = self.matcher.process_jobs([job])
        self.assertEqual(len(scored_jobs), 0)

    def test_itsector_2_years_exp_disqualification(self):
        """Verifies that AI Engineer requiring minimum 2 years of professional experience is disqualified when experience is set to 0."""
        job = Job(
            title="AI Engineer",
            company="ITSector",
            location="Castelo Branco, Castelo Branco, Portugal",
            work_mode="Presencial / Híbrido",
            link="https://pt.linkedin.com/jobs/view/ai-engineer-at-itsector-4448529944",
            description="Degree in Computer Engineering, Artificial Intelligence or similar; Minimum 2 years of professional experience developing AI-based solutions; Hands-on experience with state-of-the-art LLMs such as GPT.",
            source="LinkedIn",
            pub_date=datetime.date.today().isoformat()
        )
        scored_jobs = self.matcher.process_jobs([job])
        self.assertEqual(len(scored_jobs), 0)

    def test_volkswagen_5_years_exp_disqualification(self):
        """Verifies that Data Engineer demanding +5 years of hands-on experience is strictly disqualified even if graduates are mentioned."""
        job = Job(
            title="Data Engineer (AWS)",
            company="Volkswagen Group Digital Solutions",
            location="Lisboa, Portugal",
            work_mode="Presencial / Híbrido",
            link="https://pt.linkedin.com/jobs/view/data-engineer-aws-at-volkswagen-group-digital-solutions-portugal-4432266264",
            description="University Degree / Master for graduates in Computer Science, Informatics, or related fields. +5 years of hands-on experience as a Data Engineer or Software Engineer working on big-data environments. Strong skills in Python, SQL, AWS.",
            source="LinkedIn",
            pub_date="2026-08-14"
        )
        scored_jobs = self.matcher.process_jobs([job])
        self.assertEqual(len(scored_jobs), 0)

    def test_toptal_8_or_more_years_disqualification(self):
        """Verifies that senior freelance roles demanding 8 or more years of experience are strictly disqualified."""
        job = Job(
            title="Python Backend Development Talent with RAG and Agentic AI Experience",
            company="Toptal",
            location="Remoto",
            work_mode="Remoto",
            link="https://remoteok.com/remote-jobs/toptal-python-backend-development-talent",
            description="Toptal is looking for Python Backend Development Talent. Required: 8 or more years of professional Python backend development experience. Strong skills in Python, FastAPI, RAG, LangChain.",
            source="RemoteOK",
            pub_date=datetime.date.today().isoformat()
        )
        scored_jobs = self.matcher.process_jobs([job])
        self.assertEqual(len(scored_jobs), 0)

    def test_jobicy_latam_remote_disqualification(self):
        """Verifies that remote roles restricted to Latin America/Brazil/Mexico/USA are disqualified for Portugal candidate."""
        job = Job(
            title="GenAI Engineer",
            company="NTT DATA",
            location="Remoto (Latam)",
            work_mode="Remoto",
            link="https://jobicy.com/jobs/145940-genai-engineer",
            description="Location Preference: 100% remote in Mexico, Brasil, Peru, Chile working EST Time Zone OR onsite in Washington, D.C. Python, LLMs, GenAI.",
            source="Jobicy",
            pub_date="2026-08-16"
        )
        scored_jobs = self.matcher.process_jobs([job])
        self.assertEqual(len(scored_jobs), 0)

    def test_datamundi_diagram_creator_crowdsourcing_disqualification(self):
        """Verifies that crowdsourcing/dataset annotation gigs (e.g. DATAmundi Digital Design Diagram Creators) are disqualified."""
        job = Job(
            title="Digital Design Diagram Creators",
            company="Summa Linguae Technologies",
            location="Remoto",
            work_mode="Remoto",
            link="https://example.com/listings/summa-linguae-technologies-digital-design-diagram-creators",
            description="DATAmundi.ai is preparing for an upcoming large-scale dataset project. We expect to onboard approximately 50–100 experts within a short timeframe. The project involves creating a dataset of diagram images paired with Verilog/SystemVerilog HDL code. Estimated hourly rate: ~20 USD/h. Ideal profile: recent graduates.",
            source="RemoteOK",
            pub_date=datetime.date.today().isoformat()
        )
        scored_jobs = self.matcher.process_jobs([job])
        self.assertEqual(len(scored_jobs), 0)

    def test_primeit_linkedin_mid_senior_criteria_disqualification(self):
        """Verifies that LinkedIn roles marked with Seniority level: Mid-Senior level or 4+ years are disqualified."""
        job = Job(
            title="AI Engineer",
            company="PrimeIT",
            location="Lisboa, Portugal",
            work_mode="Presencial / Híbrido",
            link="https://pt.linkedin.com/jobs/view/ai-engineer-at-primeit-4448011394",
            description="AI Engineer - Seniority level: Mid-Senior level | Employment type: Full-time - Imagine working for a company where your growth is monitored every day. We are looking for an AI Engineer with experience in AI/ML, Python, LLMs.",
            source="LinkedIn",
            pub_date=datetime.date.today().isoformat()
        )
        scored_jobs = self.matcher.process_jobs([job])
        self.assertEqual(len(scored_jobs), 0)

    def test_germany_restricted_remote_disqualification(self):
        """Verifies that remote positions restricted to Germany (e.g. Work from anywhere in Germany, Berlin office) are disqualified for Portugal candidate."""
        job = Job(
            title="Junior AI/ML Engineer, Data and Evaluation",
            company="RedMimicry GmbH",
            location="Europe / Remote",
            work_mode="Remoto",
            link="https://www.arbeitnow.com/jobs/companies/redmimicry-gmbh/junior-ai-ml-engineer-data-and-evaluation-berlin-438979",
            description="As an AI/ML Engineer at RedMimicry, you will build datasets. Requirements: Python, PyTorch. Benefits: Work from anywhere in Germany, and use our Berlin office as often as you like. Company-paid Deutschlandticket.",
            source="Arbeitnow",
            pub_date=datetime.date.today().isoformat()
        )
        scored_jobs = self.matcher.process_jobs([job])
        self.assertEqual(len(scored_jobs), 0)

    def test_dojo_ai_experience_levels_disqualification(self):
        """Verifies that non-hierarchical/leveled postings starting at mid-level (e.g. A few years in) are disqualified."""
        job = Job(
            title="Data Engineer",
            company="DOJO AI",
            location="Lisboa, Portugal",
            work_mode="Presencial / Híbrido",
            link="https://pt.linkedin.com/jobs/view/data-engineer-at-dojo-ai-4452237785",
            description="Experience Levels: A few years in (mid-level) - You’re building pipelines. Deep experience (senior-level) - You own the platform. Been doing this a long time (staff/principal-level) - You define the architecture. Tech: Python, SQL.",
            source="LinkedIn",
            pub_date=datetime.date.today().isoformat()
        )
        scored_jobs = self.matcher.process_jobs([job])
        self.assertEqual(len(scored_jobs), 0)

    def test_jta_3_plus_of_experience_disqualification(self):
        """Verifies that postings demanding 3+ of experience (even with disclaimers like competence matters more than years) are disqualified."""
        job = Job(
            title="Data Engineer",
            company="JTA: The Data Scientists",
            location="Lisboa, Portugal",
            work_mode="Presencial / Híbrido",
            link="https://pt.linkedin.com/jobs/view/data-engineer-at-jta-the-data-scientists-4450274685",
            description="- 3+ of experience in data engineering (a reference point: at JTA, competence matters more than years). Technologies: Python, SQL, Cloud.",
            source="LinkedIn",
            pub_date=datetime.date.today().isoformat()
        )
        scored_jobs = self.matcher.process_jobs([job])
        self.assertEqual(len(scored_jobs), 0)

    def test_iefp_mestrado_nivel_7_disqualification(self):
        """Verifies that IEFP internship offers requiring Mestrado / Nível 7 are disqualified for Licenciatura candidate."""
        job = Job(
            title="Programador de Software (M/F)",
            company="Empresa via IEFP",
            location="BRAGA",
            work_mode="Presencial / Híbrido",
            link="https://iefponline.iefp.pt/IEFP/pesquisas/detalheOfertasEstagio.do?idOferta=1086235",
            description="Programador de Software (M/F) - Oferta IEFP. Condições Requeridas: Habilitações Escolares e Profissionais: Habilitação Base: Mestrado | Área de Formação: Informática | Nível 7 | Contrato de Estágio: Duração: 6 (meses)",
            source="IEFP Portal (Estágio)",
            pub_date=datetime.date.today().isoformat()
        )
        scored_jobs = self.matcher.process_jobs([job])
        self.assertEqual(len(scored_jobs), 0)

    def test_adentis_5_anos_exp_disqualification(self):
        """Verifies that AI Engineer demanding Mais de 5 anos de experiência profissional is strictly disqualified."""
        job = Job(
            title="AI Engineer",
            company="Adentis",
            location="Lisboa, Portugal",
            work_mode="Presencial / Híbrido",
            link="https://pt.linkedin.com/jobs/view/ai-engineer-at-adentis-portugal-4442023763",
            description="Requisitos: • Mais de 5 anos de experiência profissional com Machine Learning • Mais de 5 anos de experiência profissional com Generative AI • Mais de 5 anos de experiência profissional com Python.",
            source="LinkedIn",
            pub_date="2026-08-14"
        )
        scored_jobs = self.matcher.process_jobs([job])
        self.assertEqual(len(scored_jobs), 0)

    def test_toloka_crowdsourcing_microtasks_disqualification(self):
        """Verifies that crowdsourcing / video recording gigs (e.g. Toloka) are strictly disqualified."""
        job = Job(
            title="Record Your Daily Routine & Get Paid - AI Training",
            company="Toloka AI",
            location="Remoto",
            work_mode="Remoto",
            link="https://himalayas.app/companies/toloka-ai/jobs/record-your-daily-routine-get-paid-ai-training-8754786082",
            description="This is a project-based opportunity on an AI training platform — not a job. We're looking for people to record point-of-view videos of everyday household activities.",
            source="Himalayas",
            pub_date="2026-08-16"
        )
        scored_jobs = self.matcher.process_jobs([job])
        self.assertEqual(len(scored_jobs), 0)

    def test_stickermule_senior_compensation_and_stack_disqualification(self):
        """Verifies that senior full-stack roles with $150k-$250k USD salary and non-Python stack (Go/TypeScript) are strictly disqualified."""
        job = Job(
            title="Software engineer",
            company="Sticker Mule",
            location="Remoto",
            work_mode="Remoto",
            link="https://jobicy.com/jobs/150846-software-engineer-3",
            description="Sticker Mule is building commerce tools. We use Go, TypeScript, React, Expo, GraphQL, Postgres. You are an exceptional full-stack software engineer. Salary: $150,000–$250,000 USD, $20,000 signing bonus.",
            source="Jobicy",
            pub_date="2026-08-16"
        )
        scored_jobs = self.matcher.process_jobs([job])
        self.assertEqual(len(scored_jobs), 0)

    def test_support_sysadmin_dba_disqualification(self):
        """Verifies that Cloud Support Analyst, Sysadmin, and Database Engineer roles are strictly disqualified."""
        jobs = [
            Job(title="Cloud Support Analyst", company="Doxis", location="Lisboa", work_mode="Presencial", link="https://example.com/1", description="Suporte técnico cloud", source="ITJobs", pub_date="2026-08-17"),
            Job(title="Administradores de sistemas - ai driven", company="Olisipo", location="Portugal", work_mode="Remoto", link="https://example.com/2", description="Administração de sistemas e redes", source="Teamlyzer", pub_date="2026-08-15"),
            Job(title="Database Engineer", company="Ruby Labs", location="Remoto", work_mode="Remoto", link="https://example.com/3", description="Database DBA maintenance", source="Jobicy", pub_date="2026-08-17")
        ]
        scored_jobs = self.matcher.process_jobs(jobs)
        self.assertEqual(len(scored_jobs), 0)

    def test_german_language_c1_disqualification(self):
        """Verifies that jobs requiring German fluency (e.g. C1 / verhandlungssicher auf Deutsch / Praktikant) are disqualified."""
        job = Job(
            title="Praktikant AI Engineer (m/w/d)",
            company="energized& Company GmbH",
            location="Munich, Germany / Remote",
            work_mode="Remoto",
            link="https://www.arbeitnow.com/jobs/companies/energized-company-gmbh/praktikant-ai-engineer-munich-370373",
            description="Du kommunizierst verhandlungssicher auf Deutsch in Wort und Schrift (mindestens C1). We build AI agents with Python.",
            source="Arbeitnow",
            pub_date="2026-08-17"
        )
        scored_jobs = self.matcher.process_jobs([job])
        self.assertEqual(len(scored_jobs), 0)

    def test_cross_portal_deduplication_keys(self):
        """Verifies that jobs posted across different portals with company suffix differences produce matching dedup keys and are filtered."""
        from scraper import get_job_dedup_key
        
        # Test Neotalent
        key1 = get_job_dedup_key("Data Analyst", "Neotalent Conclusion")
        key2 = get_job_dedup_key("Data Analyst", "Neotalent")
        key3 = get_job_dedup_key("Data Analyst", "Neotalent Portugal")
        self.assertEqual(key1, key2)
        self.assertEqual(key2, key3)
        
        # Test Fyld
        key_f1 = get_job_dedup_key("Data Engineer (Azure)", "Fyld")
        key_f2 = get_job_dedup_key("Data Engineer - Azure", "FYLD - Consulting")
        key_f3 = get_job_dedup_key("Data Engineer (Azure)", "FYLD Portugal")
        self.assertEqual(key_f1, key_f2)
        self.assertEqual(key_f2, key_f3)

    def test_rafael_cybersecurity_and_sysadmin_matching(self):
        """Verifies that Rafael's cybersecurity and sysadmin target jobs match properly and don't get disqualified by global filters."""
        import json
        with open("profiles/rafael.json", "r", encoding="utf-8") as f:
            rafael_data = json.load(f)["candidate"]
        rafael_prof = CandidateProfile(**rafael_data)
        matcher_rafael = JobMatcher(profile=rafael_prof, enable_ai=False)

        job_cyber = Job(
            title="Junior Cybersecurity Analyst",
            company="Sonae",
            location="Porto, Portugal",
            work_mode="Híbrido",
            link="https://example.com/cyber1",
            description="Sonae procura Junior Cybersecurity Analyst para monitorização de alertas SIEM, análise de vulnerabilidades, redes e firewalls Fortinet com Linux e Wireshark.",
            source="LinkedIn",
            pub_date="2026-08-18"
        )
        scored = matcher_rafael.evaluate_job(job_cyber)
        self.assertGreaterEqual(scored.score, 60.0)

        job_sysadmin = Job(
            title="Administrador de Sistemas e Redes",
            company="Inovação SA",
            location="Lisboa, Portugal",
            work_mode="Presencial",
            link="https://example.com/sysadmin1",
            description="Procura-se Administrador de Sistemas e Redes Júnior para configuração e manutenção de servidores Windows Server e Linux, redes e firewalls.",
            source="ITJobs",
            pub_date="2026-08-18"
        )
        scored_sys = matcher_rafael.evaluate_job(job_sysadmin)
        self.assertGreaterEqual(scored_sys.score, 55.0)

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
            pub_date=datetime.date.today().isoformat()
        )
        scored_jobs = self.matcher.process_jobs([job])
        self.assertEqual(len(scored_jobs), 0)

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

    def test_proven_experience_accepted_as_junior_potential(self):
        """Verifies that jobs with generic experience phrasing (e.g. Rumos Machine Learning Engineer) are evaluated as junior potential rather than discarded."""
        job = Job(
            title="Machine Learning Engineer",
            company="Rumos Consulting",
            location="Lisboa",
            work_mode="Presencial / Híbrido",
            link="https://www.net-empregos.com/15316798/machine-learning-engineer/",
            description="Formação superior em TI. Experiência profissional comprovada na automação de infraestrutura de Machine Learning e workloads de Generative AI com mais de 120 caracteres de texto.",
            source="Net-Empregos",
            pub_date=datetime.date.today().isoformat()
        )

        scored_jobs = self.matcher.process_jobs([job])
        self.assertEqual(len(scored_jobs), 1)
        self.assertGreater(scored_jobs[0].score, 50.0)


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
                source="Test", pub_date=datetime.date.today().isoformat()
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

    def setUp(self):
        self.profile = CandidateProfile(
            name="Diogo Oliveira",
            email="diogo@example.com",
            degree="Mestrado em Engenharia Informática",
            iefp_eligible=True,
            languages=["português", "inglês"],
            search_queries=["Junior AI", "Data Science"],
            target_titles=["Junior Data Scientist", "AI Engineer"],
            tech_stack=["python", "pytorch", "scikit-learn", "sql"],
            junior_boosters=["estágio", "junior", "trainee"],
            locations=["Lisboa", "Porto", "Coimbra", "Leiria", "Pombal", "Remoto"]
        )

    def test_clean_job_description(self):
        html_input = "<div><h1>Title</h1><script>var x=1;</script><p>Text with <b>HTML</b> tags.</p></div>"
        cleaned = clean_job_description(html_input)
        self.assertNotIn("<script>", cleaned)
        self.assertNotIn("<b>", cleaned)
        self.assertIn("Title Text with HTML tags.", cleaned)

    def test_clean_and_extract_json(self):
        evaluator = AIEvaluator(groq_api_key="", gemini_api_key="")
        raw_markdown = '```json\n{\n  "evaluations": [\n    {"job_index": 0, "is_suitable": true, "fit_score": 85}\n  ]\n}\n```'
        cleaned = evaluator._clean_and_extract_json(raw_markdown)
        self.assertTrue(cleaned.startswith("{"))
        self.assertTrue(cleaned.endswith("}"))

    def test_is_seen_candidate_hash(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
            temp_path = tf.name

        try:
            store = SeenStore(filepath=temp_path)
            title = "Junior Data Scientist"
            company = "Tech Corp"
            link = "https://example.com/job1"
            # Not seen yet
            self.assertFalse(store.is_seen(
                Job(title=title, company=company, location="Lisboa",
                    work_mode="Presencial", link=link,
                    description="Python, Machine Learning", source="Test",
                    pub_date=datetime.date.today().isoformat()).job_id
            ))
            
            # Create job and mark as seen via the real dedup flow
            j = Job(
                title=title, company=company, location="Lisboa",
                work_mode="Presencial", link=link,
                description="Python, Machine Learning", source="Test",
                pub_date=datetime.date.today().isoformat()
            )
            store.mark_seen([j.job_id])
            # Same job (same link) should now be seen
            self.assertTrue(store.is_seen(j.job_id))
            # Same title+company but different link should NOT collide
            j2 = Job(
                title=title, company=company, location="Lisboa",
                work_mode="Presencial", link="https://example.com/job2",
                description="Python, Machine Learning", source="Test",
                pub_date=datetime.date.today().isoformat()
            )
            self.assertFalse(store.is_seen(j2.job_id))
            # filter_new should only return j2 (j is already seen)
            new = store.filter_new([j, j2])
            self.assertEqual(len(new), 1)
            self.assertEqual(new[0].job_id, j2.job_id)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_dynamic_location_matching(self):
        matcher = JobMatcher(profile=self.profile, enable_ai=False)
        # Test Portuguese municipality that is not in the old hardcoded 8 cities (e.g. Pombal, Cascais, Guimarães)
        job_pombal = Job(
            title="Junior Data Scientist", company="Tech SA", location="Pombal, Portugal",
            work_mode="Presencial", link="https://example.com/p1",
            description="Requisitos: Licenciatura em Engenharia Informática, conhecimentos de Python, SQL e Machine Learning.",
            source="Test", pub_date=datetime.date.today().isoformat()
        )
        scored = matcher.evaluate_job(job_pombal)
        self.assertNotEqual(scored.seniority_status, "Fora do Âmbito Geográfico")
        self.assertGreater(scored.score, 0)

        # Foreign location presencial should be rejected
        job_madrid = Job(
            title="Junior Data Scientist", company="Tech SA", location="Madrid, Spain",
            work_mode="Presencial", link="https://example.com/m1",
            description="Requisitos: Licenciatura em Engenharia Informática, conhecimentos de Python, SQL e Machine Learning.",
            source="Test", pub_date=datetime.date.today().isoformat()
        )
        scored_madrid = matcher.evaluate_job(job_madrid)
        self.assertEqual(scored_madrid.seniority_status, "Fora do Âmbito Geográfico")

    def test_ai_evaluator_resilience_partial_json(self):
        evaluator = AIEvaluator(groq_api_key="", gemini_api_key="")
        dummy_job = Job(
            title="Junior Python", company="AI Corp", location="Lisboa",
            work_mode="Presencial", link="https://example.com/1",
            description="Python & ML", source="Test", pub_date=datetime.date.today().isoformat()
        )
        # Unclosed JSON (e.g. truncated)
        partial_json = '{"evaluations": [{"job_index": 0, "is_suitable": true, "fit_score": 90, "seniority_detected": "Junior", "reasoning": "Ótimo fit", "pros": ["Python"], "cons": []}'
        res = evaluator._parse_batch_json_response(partial_json, [dummy_job])
        self.assertIn(dummy_job.job_id, res)
        self.assertEqual(res[dummy_job.job_id].fit_score, 90)

    def test_company_extractor_caching(self):
        from company_extractor import extract_company_from_link, _COMPANY_CACHE
        test_url = "https://www.linkedin.com/jobs/view/data-scientist-at-super-ai-labs-12345678"
        comp = extract_company_from_link(test_url)
        self.assertEqual(comp, "Super Ai Labs")
        self.assertIn(test_url, _COMPANY_CACHE)
        self.assertEqual(_COMPANY_CACHE[test_url], "Super Ai Labs")

    def test_clean_analysis_text_emojis_and_prefixes(self):
        from matcher import clean_analysis_text
        dirty_samples = [
            ("✅ Adequada (71.0%): ✅ Adequada: Posição de Especialista em IA.", "Posição de Especialista em IA."),
            ("✅ ✅ Adequada: Alinhamento perfeito com IA Engineer.", "Alinhamento perfeito com IA Engineer."),
            ("✅ Boa oportunidade de Data Scientist na área de finanças.", "Boa oportunidade de Data Scientist na área de finanças."),
            ("❌ Rejeitada por IA: Exige 8+ anos de experiência.", "Exige 8+ anos de experiência."),
            ("Filtro Automático: Exige Doutoramento", "Exige Doutoramento")
        ]
        for dirty, expected in dirty_samples:
            self.assertEqual(clean_analysis_text(dirty), expected)

    def test_tiago_profile_matching(self):
        from config import load_config
        cfg = load_config("tiago")
        self.assertEqual(cfg.candidate.name, "Tiago Alves")
        self.assertEqual(cfg.notion_database_id, "3c24e649adbe806aa60edbacc063d60d")
        self.assertTrue(cfg.candidate.iefp_eligible)
        
        matcher = JobMatcher(profile=cfg.candidate, enable_ai=False)
        
        # Test Cloud / DevOps / Data / Web matching
        job_cloud = Job(
            title="Junior Cloud Engineer",
            company="CloudTech",
            location="Castelo Branco, Portugal",
            work_mode="Presencial",
            link="https://example.com/tiago-cloud",
            description="Recém-licenciado com conhecimentos em AWS, Terraform e Docker. Elegível para estágio IEFP com mais de 120 caracteres de descrição.",
            source="Test",
            pub_date=datetime.date.today().isoformat()
        )
        scored_cloud = matcher.evaluate_job(job_cloud)
        self.assertGreaterEqual(scored_cloud.score, 75.0)
        self.assertIn("aws", scored_cloud.matched_skills)
        
        # Test Laravel / PHP matching
        job_laravel = Job(
            title="Junior Laravel Developer",
            company="WebStudio",
            location="Lisboa, Portugal",
            work_mode="Híbrido",
            link="https://example.com/tiago-web",
            description="Desenvolvedor júnior PHP e Laravel com MySQL e Git para desenvolvimento web com mais de 120 caracteres de descrição.",
            source="Test",
            pub_date=datetime.date.today().isoformat()
        )
        scored_laravel = matcher.evaluate_job(job_laravel)
        self.assertGreaterEqual(scored_laravel.score, 75.0)
        self.assertIn("laravel", scored_laravel.matched_skills)

        # Test Alentejo / Évora preferred location bonus
        job_alentejo = Job(
            title="Junior Web Developer",
            company="AlentejoTech",
            location="Évora, Alentejo, Portugal",
            work_mode="Presencial",
            link="https://example.com/tiago-alentejo",
            description="Desenvolvedor Web júnior com conhecimentos sólidos em PHP e MySQL para estágio profissional IEFP em Évora, Alentejo, com foco em desenvolvimento web.",
            source="Test",
            pub_date=datetime.date.today().isoformat()
        )
        scored_alentejo = matcher.evaluate_job(job_alentejo)
        self.assertGreaterEqual(scored_alentejo.score, 85.0)
        self.assertIn("Localização Preferencial", scored_alentejo.match_reason)



if __name__ == "__main__":
    unittest.main()



