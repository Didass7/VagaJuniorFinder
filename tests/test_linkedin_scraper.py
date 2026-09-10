import unittest
from unittest.mock import patch, MagicMock
from scrapers.linkedin import LinkedInScraper
from scrapers.base import decode_response_content, safe_fetch, Job


class TestLinkedInAndEncoding(unittest.TestCase):
    """Tests LinkedIn detail fetching and HTTP response charset decoding."""

    def test_linkedin_fetch_detail_seen_job_no_nameerror(self):
        """Verifies that is_seen_func receives clean_link and returns a fast stub without NameError."""
        called_args = []

        def mock_is_seen(title: str, company: str, link: str = ""):
            called_args.append((title, company, link))
            return True

        scraper = LinkedInScraper(is_seen_func=mock_is_seen)
        card_info = {
            "title": "Junior Data Scientist",
            "clean_link": "https://www.linkedin.com/jobs/view/1234567890",
            "company": "Tech Corp",
            "location": "Lisboa, Portugal",
            "pub_date": "2026-09-10"
        }

        job = scraper._fetch_detail_job(card_info)
        self.assertIsInstance(job, Job)
        self.assertEqual(job.title, "Junior Data Scientist")
        self.assertEqual(job.company, "Tech Corp")
        self.assertEqual(job.link, "https://www.linkedin.com/jobs/view/1234567890")
        self.assertIn("Oferta de emprego registada no LinkedIn", job.description)
        self.assertEqual(len(called_args), 1)
        self.assertEqual(called_args[0], ("Junior Data Scientist", "Tech Corp", "https://www.linkedin.com/jobs/view/1234567890"))

    def test_linkedin_fetch_detail_unseen_job_no_nameerror(self):
        """Verifies that unseen jobs proceed without NameError and build a valid Job object."""
        scraper = LinkedInScraper(is_seen_func=lambda t, c, link="": False)
        card_info = {
            "title": "Junior AI Engineer",
            "clean_link": "https://www.linkedin.com/jobs/view/9876543210",
            "company": "AI Labs",
            "location": "Porto, Portugal",
            "pub_date": "2026-09-10"
        }

        # Mock guest API and direct page calls
        session_mock = MagicMock()
        session_mock.get.return_value = MagicMock(status_code=404, text="")
        scraper.session = session_mock

        job = scraper._fetch_detail_job(card_info)
        self.assertIsInstance(job, Job)
        self.assertEqual(job.title, "Junior AI Engineer")
        self.assertEqual(job.company, "AI Labs")
        self.assertIn("LinkedIn Jobs Portugal", job.description)

    def test_decode_response_content_windows_1252_meta_tag(self):
        """Verifies that HTML declaring ISO-8859-1 is decoded cleanly as Windows-1252 without replacement characters."""
        raw_html = (
            b'<!DOCTYPE html><html><head>'
            b'<meta http-equiv="Content-Type" content="text/html; charset=ISO-8859-1" />'
            b'</head><body>'
            b'<h1>Analista de Dados - Financiamento Autom\xf3vel</h1>'
            b'<p>Especialista em IA \x96 2 vagas - Ref\xaa ESP-IA/2026</p>'
            b'</body></html>'
        )

        decoded = decode_response_content(raw_html)
        self.assertNotIn("\ufffd", decoded)
        self.assertIn("Automóvel", decoded)
        self.assertIn("– 2 vagas", decoded)
        self.assertIn("Refª", decoded)

    def test_decode_response_content_utf8_meta_tag(self):
        """Verifies that UTF-8 content is preserved exactly."""
        raw_html = (
            '<!DOCTYPE html><html><head>'
            '<meta charset="utf-8" />'
            '</head><body>'
            '<h1>Engenheiro de Software Júnior</h1>'
            '<p>Inteligência Artificial e Aprendizagem Automática</p>'
            '</body></html>'
        ).encode("utf-8")

        decoded = decode_response_content(raw_html)
        self.assertNotIn("\ufffd", decoded)
        self.assertIn("Engenheiro de Software Júnior", decoded)
        self.assertIn("Inteligência Artificial", decoded)

    def test_decode_response_content_content_type_header(self):
        """Verifies that charset from Content-Type header takes priority."""
        raw_html = b'Autom\xf3vel'
        headers = {"content-type": "text/html; charset=iso-8859-1"}

        decoded = decode_response_content(raw_html, headers=headers)
        self.assertEqual(decoded, "Automóvel")
        self.assertNotIn("\ufffd", decoded)


if __name__ == "__main__":
    unittest.main()
