import unittest
from ui.profiles import merge_profile_form


class TestProfileForm(unittest.TestCase):
    """Tests the profile manager's save logic."""

    def test_save_keeps_fields_not_in_form(self):
        """Saving the form must not drop fields it doesn't edit (preferred locations, per-profile thresholds)."""
        stored = {
            "candidate": {
                "name": "Tiago Alves",
                "tech_stack": ["php"],
                "preferred_locations": ["alentejo", "évora"],
                "preferred_location_bonus": 15.0
            },
            "notion_database_id": "old-id",
            "promising_match_threshold": 60.0
        }
        form_fields = {"name": "Tiago A.", "tech_stack": ["php", "mysql"]}

        updated = merge_profile_form(stored, form_fields, "new-id")

        self.assertEqual(updated["candidate"]["name"], "Tiago A.")
        self.assertEqual(updated["candidate"]["tech_stack"], ["php", "mysql"])
        self.assertEqual(updated["candidate"]["preferred_locations"], ["alentejo", "évora"])
        self.assertEqual(updated["candidate"]["preferred_location_bonus"], 15.0)
        self.assertEqual(updated["promising_match_threshold"], 60.0)
        self.assertEqual(updated["notion_database_id"], "new-id")
        # The stored profile dict is not mutated
        self.assertEqual(stored["candidate"]["name"], "Tiago Alves")


if __name__ == "__main__":
    unittest.main()
