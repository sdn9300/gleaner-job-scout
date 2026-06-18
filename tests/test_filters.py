import unittest
from filters import dedupe, filter_by_role, filter_by_location

class TestFilters(unittest.TestCase):
    def test_dedupe(self):
        jobs = [
            {"title": "Software Engineer", "company": "Google", "location": "Bangalore"},
            {"title": "software engineer", "company": " Google ", "location": "Remote"},  # duplicate
            {"title": "Data Scientist", "company": "Google", "location": "Bangalore"},     # different title
            {"title": "Software Engineer", "company": "Microsoft", "location": "Bangalore"} # different company
        ]
        result = dedupe(jobs)
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0]["location"], "Bangalore") # First one kept
        self.assertEqual(result[1]["title"], "Data Scientist")
        self.assertEqual(result[2]["company"], "Microsoft")

    def test_filter_by_role(self):
        jobs = [
            {"title": "Python Developer", "description": "Write code"},
            {"title": "Java Developer", "description": "Python scripts"},
            {"title": "C++ Specialist", "description": "High performance computing"}
        ]
        result = filter_by_role(jobs, "python")
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["title"], "Python Developer")
        self.assertEqual(result[1]["title"], "Java Developer")

        # Multi-word role matching (any keyword)
        result_multi = filter_by_role(jobs, "java specialist")
        self.assertEqual(len(result_multi), 2)
        self.assertEqual(result_multi[0]["title"], "Java Developer")
        self.assertEqual(result_multi[1]["title"], "C++ Specialist")

    def test_filter_by_location(self):
        jobs = [
            {"location": "Bangalore, India"},
            {"location": "Remote"},
            {"location": "Pune, India"},
            {"location": "New York"}
        ]
        result = filter_by_location(jobs, "bangalore")
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["location"], "Bangalore, India")
        self.assertEqual(result[1]["location"], "Remote") # Remote kept regardless of location query

