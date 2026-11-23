"""Optional checks for maintainers with the original 2026–2027 snapshot and backup."""

import json
import unittest

from api import DEFAULT_PATH
from catalog.export_public import PUBLIC_PATH
from catalog.store import Catalog


class TestLocalRelease(unittest.TestCase):
    def test_public_facts_match_private_snapshot(self):
        private = json.loads(DEFAULT_PATH.read_bytes())
        public = json.loads(PUBLIC_PATH.read_bytes())
        for field in ("academic_year", "generated_utc", "coverage"):
            self.assertEqual(public[field], private[field])
        fields = ("code", "title", "faculty", "faculties", "credits", "source_url", "source_urls")
        private_rows = {row["code"]: row for row in private["courses"]}
        self.assertEqual({row["code"] for row in public["courses"]}, private_rows.keys())
        for row in public["courses"]:
            source = private_rows[row["code"]]
            self.assertEqual({k: row[k] for k in fields}, {k: source[k] for k in fields}, row["code"])

    def test_preserves_all_original_courses(self):
        original = json.loads(DEFAULT_PATH.with_name("courses-complete-backup.json").read_bytes())
        current = json.loads(DEFAULT_PATH.read_bytes())
        catalog = Catalog.load(DEFAULT_PATH)
        self.assertEqual(len(current["courses"]), 6497)
        self.assertEqual(catalog.metadata.courses, 6497)
        self.assertEqual(catalog.metadata.multi_faculty_courses, 44)
        self.assertEqual(catalog.metadata.coverage, dict(
            artsci=5368, engineering=557, architecture=124, music=327,
            kinesiology=107, information=22, medicine=21, nursing=16,
        ))
        expected = {c["code"]: (c["title"], c["faculties"]) for c in original["courses"]}
        self.assertEqual({code: (c.title, c.faculties) for code, c in catalog.by_code.items()}, expected)

    def test_representative_courses(self):
        catalog = Catalog.load(DEFAULT_PATH)
        course = catalog.by_code["CSC207H1"]
        self.assertEqual(course.title, "Software Design")
        self.assertIn("CSC148H1", course.prerequisites)
        self.assertIn("CSC207H5", course.exclusions)
        self.assertNotIn("24L/24T", course.description)
        self.assertEqual(catalog.by_code["ANS310Y"].faculty, "Medicine (MD)")
        self.assertEqual(catalog.by_code["EMU254H1"].credits, .17)
