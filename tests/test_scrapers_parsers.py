import unittest
import json
import datetime
from unittest.mock import patch, MagicMock
from bs4 import BeautifulSoup

from scrapers.base import Job
from scrapers.linkedin import LinkedInScraper
from scrapers.itjobs import ITJobsScraper
from scrapers.landingjobs import LandingJobsScraper
from scrapers.teamlyzer import TeamlyzerScraper
from scrapers.netempregos import NetEmpregosScraper
from scrapers.sapo import SapoScraper
from scrapers.iefp import IEFPScraper
from scrapers.cargadetrabalhos import CargaDeTrabalhosScraper
from scrapers.euraxess import EuraxessScraper
from scrapers.arbeitnow import ArbeitnowScraper
from scrapers.remoteok import RemoteOKScraper
from scrapers.jobicy import JobicyScraper
from scrapers.remotive import RemotiveScraper
from scrapers.jobspresso import JobspressoScraper


class TestScrapersParsers(unittest.TestCase):
    """Unit tests validating HTML, JSON, and RSS parsing logic across all scrapers with mock payloads."""

    def test_teamlyzer_html_parser(self):
        """Validates Teamlyzer HTML card extraction for title, company, salary, and regime."""
        html = """
        <div class="jobcard">
            <div class="jobcard__title-row">
                <a href="/companies/get-job/123-abc">Junior AI Engineer</a>
            </div>
            <div class="jobcard__meta">Smart Consulting</div>
            <div class="jobcard__tags">
                <span class="tag">Remoto</span>
                <span class="tag">1.400€ - 1.800€</span>
            </div>
            <div class="jobcard__desc">Desenvolvimento de modelos LLM e Python em regime remoto.</div>
        </div>
        """
        scraper = TeamlyzerScraper()
        jobs = scraper._parse_page(html)
        self.assertEqual(len(jobs), 1)
        j = jobs[0]
        self.assertEqual(j.title, "Junior AI Engineer")
        self.assertEqual(j.company, "Smart Consulting")
        self.assertEqual(j.source, "Teamlyzer")
        self.assertIn("123-abc", j.link)
        self.assertEqual(j.work_mode, "Remoto")

    def test_sapo_vue_component_json_parser(self):
        """Validates Sapo Emprego embedded Vue search-results-component :offers JSON parser."""
        offers_payload = [
            {
                "id": "abc-456",
                "offer_name": "Junior Data Scientist",
                "company_name": "Telecom PT",
                "job_district": "Lisboa",
                "job_country": "Portugal",
                "remote": False,
                "job_description": "Vaga presencial para estágio IEFP em Python e Machine Learning.",
                "publication_date": "2026-08-26"
            }
        ]
        html = f'<search-results-component :offers=\'{json.dumps(offers_payload)}\'></search-results-component>'
        scraper = SapoScraper()
        jobs = scraper._parse_sapo_page(html)
        self.assertEqual(len(jobs), 1)
        j = jobs[0]
        self.assertEqual(j.title, "Junior Data Scientist")
        self.assertEqual(j.company, "Telecom PT")
        self.assertEqual(j.location, "Lisboa, Portugal")
        self.assertEqual(j.source, "Sapo Emprego")

    def test_landingjobs_json_parser(self):
        """Validates Landing.jobs REST API response parsing."""
        api_response = json.dumps([
            {
                "id": 999,
                "title": "Junior Python Developer",
                "url": "https://landing.jobs/at/techcorp/junior-python-developer",
                "company_name": "TechCorp",
                "city": "Lisbon",
                "remote": True,
                "role_description": "Building RAG pipelines and REST APIs with FastAPI.",
                "published_at": "2026-08-26T10:00:00Z"
            }
        ])
        scraper = LandingJobsScraper()
        with patch("requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.text = api_response
            mock_get.return_value = mock_resp
            jobs = scraper.fetch()

        self.assertGreaterEqual(len(jobs), 1)
        j = jobs[0]
        self.assertEqual(j.title, "Junior Python Developer")
        self.assertEqual(j.company, "TechCorp")
        self.assertEqual(j.work_mode, "Remoto")
        self.assertEqual(j.source, "Landing.jobs")

    def test_netempregos_rss_parser(self):
        """Validates Net-Empregos RSS XML feed parsing."""
        rss_content = """<?xml version="1.0" encoding="utf-8"?>
        <rss version="2.0">
            <channel>
                <title>Net-Empregos</title>
                <item>
                    <title>Engenheiro de Inteligência Artificial Júnior (M/F) - Lisboa</title>
                    <link>https://www.net-empregos.com/1234567/ia-junior/</link>
                    <description>Empresa de TI recruta recém-licenciado para estágio profissional IEFP em Python e PyTorch.</description>
                    <pubDate>Wed, 26 Aug 2026 12:00:00 GMT</pubDate>
                </item>
            </channel>
        </rss>
        """
        session_mock = MagicMock()
        session_mock.get.return_value = MagicMock(status_code=404, text="")

        scraper = NetEmpregosScraper(session=session_mock)
        with patch("scrapers.netempregos.safe_fetch") as mock_fetch:
            mock_fetch.return_value = (200, rss_content, rss_content.encode("utf-8"))
            jobs = scraper.fetch()

        self.assertGreaterEqual(len(jobs), 1)
        j = jobs[0]
        self.assertIn("Inteligência Artificial", j.title)
        self.assertEqual(j.source, "Net-Empregos")
        self.assertTrue(j.iefp_mentioned)

    def test_itjobs_html_parser(self):
        """Validates ITJobs.pt search card and detail page parsing."""
        search_html = """
        <div class="list">
            <div class="info">
                <a class="title" href="/oferta/98765/junior-data-analyst">Junior Data Analyst</a>
                <a class="company" href="/empresa/data-labs">Data Labs PT</a>
                <span class="location">Porto</span>
            </div>
        </div>
        """
        detail_html = """
        <html>
            <head><title>Junior Data Analyst - Data Labs PT - ITJobs</title></head>
            <body>
                <p>Requisitos: Conhecimentos em SQL, PowerBI e Python para análise de dados.</p>
            </body>
        </html>
        """
        session_mock = MagicMock()
        r1 = MagicMock(status_code=200, text=search_html)
        r2 = MagicMock(status_code=200, text=detail_html)
        session_mock.get.side_effect = [r1, r2]

        scraper = ITJobsScraper(session=session_mock)
        cards = scraper._fetch_search_url_cards("https://www.itjobs.pt/emprego?q=data")
        self.assertEqual(len(cards), 1)
        job = scraper._fetch_detail_body(cards[0])
        self.assertEqual(job.title, "Junior Data Analyst")
        self.assertEqual(job.company, "Data Labs PT")
        self.assertEqual(job.location, "Porto")

    def test_arbeitnow_json_parser(self):
        """Validates Arbeitnow API JSON parsing."""
        api_data = {
            "data": [
                {
                    "slug": "junior-backend-engineer",
                    "title": "Junior Backend Engineer",
                    "company_name": "Fintech EU",
                    "location": "Berlin / Remote",
                    "remote": True,
                    "url": "https://www.arbeitnow.com/view/junior-backend-engineer",
                    "description": "<p>Looking for a junior developer with Python and FastAPI.</p>",
                    "created_at": 1724680000
                }
            ],
            "links": {"next": None}
        }
        scraper = ArbeitnowScraper()
        with patch.object(scraper.session, "get") as mock_get:
            mock_get.return_value = MagicMock(status_code=200, json=lambda: api_data)
            jobs = scraper.fetch()

        self.assertGreaterEqual(len(jobs), 1)
        j = jobs[0]
        self.assertEqual(j.title, "Junior Backend Engineer")
        self.assertEqual(j.company, "Fintech EU")
        self.assertEqual(j.source, "Arbeitnow")
        self.assertEqual(j.work_mode, "Remoto")

    def test_remoteok_json_parser(self):
        """Validates RemoteOK API JSON response parsing."""
        api_data = [
            {"legal": "Notice"},
            {
                "id": "112233",
                "position": "Junior Machine Learning Engineer",
                "company": "AI Global",
                "location": "Worldwide",
                "url": "https://remoteok.com/remote-jobs/112233",
                "description": "Work with PyTorch, transformers, and vector databases 100% remote.",
                "date": "2026-08-26T00:00:00+00:00"
            }
        ]
        scraper = RemoteOKScraper()
        with patch.object(scraper.session, "get") as mock_get:
            mock_get.return_value = MagicMock(status_code=200, json=lambda: api_data)
            jobs = scraper.fetch()

        self.assertGreaterEqual(len(jobs), 1)
        j = jobs[0]
        self.assertEqual(j.title, "Junior Machine Learning Engineer")
        self.assertEqual(j.company, "AI Global")
        self.assertEqual(j.source, "RemoteOK")
        self.assertEqual(j.work_mode, "Remoto")

    def test_jobicy_json_parser(self):
        """Validates Jobicy API JSON parsing."""
        api_data = {
            "jobs": [
                {
                    "id": 5544,
                    "jobTitle": "Junior Data Engineer",
                    "companyName": "CloudData Corp",
                    "jobGeo": "Europe",
                    "url": "https://jobicy.com/jobs/5544-junior-data-engineer",
                    "jobDescription": "Build ETL pipelines with SQL, Spark, and Python.",
                    "pubDate": "2026-08-26 08:00:00"
                }
            ]
        }
        scraper = JobicyScraper()
        with patch.object(scraper.session, "get") as mock_get:
            mock_get.return_value = MagicMock(status_code=200, json=lambda: api_data)
            jobs = scraper.fetch()

        self.assertEqual(len(jobs), 1)
        j = jobs[0]
        self.assertEqual(j.title, "Junior Data Engineer")
        self.assertEqual(j.company, "CloudData Corp")
        self.assertEqual(j.source, "Jobicy")

    def test_remotive_json_parser(self):
        """Validates Remotive API JSON parsing."""
        api_data = {
            "jobs": [
                {
                    "id": 8877,
                    "title": "Junior Python / AI Developer",
                    "company_name": "DeepTech",
                    "candidate_required_location": "Europe",
                    "url": "https://remotive.com/remote-jobs/software-dev/8877",
                    "description": "<p>Develop AI agents and LangChain integrations.</p>",
                    "publication_date": "2026-08-26T09:00:00"
                }
            ]
        }
        scraper = RemotiveScraper()
        with patch.object(scraper.session, "get") as mock_get:
            mock_get.return_value = MagicMock(status_code=200, json=lambda: api_data)
            jobs = scraper.fetch()

        self.assertEqual(len(jobs), 1)
        j = jobs[0]
        self.assertEqual(j.title, "Junior Python / AI Developer")
        self.assertEqual(j.company, "DeepTech")
        self.assertEqual(j.source, "Remotive")

    def test_jobspresso_html_parser(self):
        """Validates Jobspresso HTML listing and detail parsing."""
        listing_html = """
        <html>
            <body>
                <ul class="job_listings">
                    <li class="job_listing">
                        <a href="https://jobspresso.co/job/junior-fullstack/">
                            <div class="position"><h3>Junior Fullstack Engineer</h3></div>
                            <div class="company"><strong>RemoteTech</strong></div>
                            <div class="location">Remote</div>
                        </a>
                    </li>
                </ul>
            </body>
        </html>
        """
        detail_html = """
        <html>
            <body>
                <div class="job_listing-description">
                    <p>Junior Fullstack Engineer role working with Python and React in full remote mode.</p>
                </div>
            </body>
        </html>
        """
        session_mock = MagicMock()
        r1 = MagicMock(status_code=200, text=listing_html)
        r2 = MagicMock(status_code=200, text=detail_html)
        session_mock.get.side_effect = [r1, r2, MagicMock(status_code=404), MagicMock(status_code=404)]

        scraper = JobspressoScraper(session=session_mock)
        card = {
            "title": "Junior Fullstack Engineer",
            "link": "https://jobspresso.co/job/junior-fullstack/",
            "company": "RemoteTech",
            "location": "Remote",
            "summary": "Junior Fullstack Engineer"
        }
        job = scraper._fetch_detail_page(card)
        self.assertEqual(job.title, "Junior Fullstack Engineer")
        self.assertEqual(job.company, "RemoteTech")
        self.assertEqual(job.work_mode, "Remoto")

    def test_cargadetrabalhos_html_parser(self):
        """Validates Carga de Trabalhos HTML article card parsing."""
        articles_html = """
        <html>
            <body>
                <article>
                    <a href="https://cargadetrabalhos.pt/ofertas/123/junior-software-developer">Junior Software Developer</a>
                    <div class="entry-summary">Empresa no Porto procura recém-licenciado em Engenharia Informática.</div>
                </article>
            </body>
        </html>
        """
        session_mock = MagicMock()
        session_mock.get.return_value = MagicMock(status_code=200, text=articles_html)

        scraper = CargaDeTrabalhosScraper(session=session_mock, queries=["developer"])
        cards = scraper._fetch_query_articles("developer", max_pages=1)
        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0]["title"], "Junior Software Developer")
        self.assertIn("123/junior-software-developer", cards[0]["link"])

    def test_euraxess_html_parser(self):
        """Validates Euraxess research fellowship job card parsing."""
        html = """
        <html>
            <body>
                <div class="view-content">
                    <div class="views-row teaser">
                        <a href="/jobs/654321">Bolsa de Investigação para Mestre em Inteligência Artificial</a>
                        <div>Universidade do Porto | Faculdade de Engenharia | Lisboa, Portugal</div>
                    </div>
                </div>
            </body>
        </html>
        """
        session_mock = MagicMock()
        session_mock.get.return_value = MagicMock(status_code=200, text=html)

        scraper = EuraxessScraper(session=session_mock, queries=["AI"])
        jobs = scraper.fetch()
        self.assertEqual(len(jobs), 1)
        j = jobs[0]
        self.assertIn("Bolsa de Investigação", j.title)
        self.assertEqual(j.source, "Euraxess / Ergas (Bolsas ID)")
        self.assertIn("654321", j.link)

    def test_iefp_html_parser(self):
        """Validates IEFP HTML results table card parsing."""
        html = """
        <html>
            <body>
                <div class="results-table">
                    <div class="row card">
                        <h5>Técnico de Inteligência Artificial Júnior</h5>
                        <strong>Lisboa</strong>
                        <a href="detalheOfertas.do?id=12345">Ver Detalhe</a>
                        <p>Oferta de estágio profissional ATIVAR.PT para recém-licenciados.</p>
                    </div>
                </div>
            </body>
        </html>
        """
        session_mock = MagicMock()
        session_mock.get.return_value = MagicMock(status_code=200, text="")
        session_mock.post.return_value = MagicMock(status_code=200, text=html)

        scraper = IEFPScraper(session=session_mock)
        jobs = scraper._search_offers("inteligencia artificial", "OFERTA_ESTAGIO", seen_links=set())
        self.assertEqual(len(jobs), 1)
        j = jobs[0]
        self.assertEqual(j.title, "Técnico de Inteligência Artificial Júnior")
        self.assertEqual(j.source, "IEFP Portal (Estágio)")
        self.assertEqual(j.location, "Lisboa")


if __name__ == "__main__":
    unittest.main()

