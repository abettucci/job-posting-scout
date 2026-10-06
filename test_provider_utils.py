import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).parent / "aws" / "lambdas" / "scraper"))

from providers._utils import location_match  # noqa: E402


class LocationMatchTests(unittest.TestCase):
    def test_worldwide_accepts_only_unrestricted_remote_labels(self):
        self.assertTrue(location_match("Remote", "Argentina, Worldwide"))
        self.assertTrue(location_match("Fully remote", "Worldwide"))
        self.assertTrue(location_match("Worldwide / Remote", "Worldwide"))
        self.assertFalse(location_match("Remote (United States)", "Worldwide"))
        self.assertFalse(location_match("Remote Poland", "Worldwide"))
        self.assertFalse(location_match("Remote — EMEA", "Worldwide"))

    def test_explicit_location_still_matches_an_alternative(self):
        self.assertTrue(location_match("Remote (Buenos Aires, Argentina)", "Argentina, Worldwide"))
        self.assertFalse(location_match("Berlin, Germany", "Argentina, Worldwide"))


if __name__ == "__main__":
    unittest.main()
