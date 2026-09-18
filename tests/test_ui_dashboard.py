import unittest
from ui.dashboard import esc, safe_href


class TestDashboardEscaping(unittest.TestCase):
    """Scraped values are rendered with unsafe_allow_html, so they must be escaped first."""

    def test_esc_neutralizes_markup(self):
        self.assertEqual(esc('<img src=x onerror="alert(1)">'), "&lt;img src=x onerror=&quot;alert(1)&quot;&gt;")
        self.assertEqual(esc("R&D Engineer"), "R&amp;D Engineer")
        self.assertEqual(esc(None), "")

    def test_safe_href_only_allows_http_links(self):
        self.assertEqual(safe_href("https://example.com/job?a=1&b=2"), "https://example.com/job?a=1&amp;b=2")
        self.assertEqual(safe_href('https://example.com/"onmouseover="x'), "https://example.com/&quot;onmouseover=&quot;x")
        self.assertEqual(safe_href("javascript:alert(1)"), "#")
        self.assertEqual(safe_href(None), "#")


if __name__ == "__main__":
    unittest.main()
