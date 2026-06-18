import unittest
import os
import csv
from writers import write_csv, CANONICAL_FIELDS

class TestWriters(unittest.TestCase):
    def test_write_csv(self):
        test_path = "tests/test_output.csv"
        jobs = [
            {
                "source": "naukri",
                "title": "Software Engineer",
                "company": "Google",
                "location": "Bangalore",
                "link": "https://naukri.com/123",
                "posted_at": "1 day ago",
                "description": "Python developer role",
                "extra_field": "ignore me" # should be dropped by DictWriter
            }
        ]
        
        try:
            write_csv(jobs, test_path)
            self.assertTrue(os.path.exists(test_path))
            
            # Read CSV content and verify
            with open(test_path, "r", encoding="utf-8") as f:
                reader = csv.reader(f)
                rows = list(reader)
                
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0], CANONICAL_FIELDS)
            self.assertEqual(rows[1], ["naukri", "Software Engineer", "Google", "Bangalore", "https://naukri.com/123", "1 day ago", "Python developer role"])
        finally:
            if os.path.exists(test_path):
                os.remove(test_path)
