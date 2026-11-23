import json
from pathlib import Path
import tempfile
import unittest

from catalog.export_public import PUBLIC_PATH, PUBLIC_SOURCE, export_public
from catalog.store import Catalog


FIXTURE = Path(__file__).parent / "fixtures" / "catalog.json"
FACTS = ("code", "title", "faculty", "faculties", "credits", "source_url", "source_urls")
EMPTY_FIELDS = {"description": "", "prerequisites": "", "corequisites": "",
                "exclusions": "", "source_fields": {}}


class TestPublicExporter(unittest.TestCase):
    def test_only_facts_survive_export(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "private.json"
            destination = Path(directory) / "public" / "catalog.json"
            snapshot = json.loads(FIXTURE.read_bytes())
            marker = "Private marker for export testing"
            snapshot["source"] = marker
            snapshot["private_notes"] = marker
            for course in snapshot["courses"]:
                course.update(description=marker, prerequisites=marker, exclusions=marker,
                              corequisites=marker, source_fields={"note": f"<p>{marker}</p>"},
                              new_calendar_field=marker)
            original = json.dumps(snapshot).encode()
            source.write_bytes(original)

            count = export_public(source, destination)
            encoded = destination.read_bytes()
            self.assertNotIn(marker.encode(), encoded)
            self.assertEqual(count, len(snapshot["courses"]))
            self.assertEqual(source.read_bytes(), original)
            public = json.loads(encoded)
            self.assertEqual(set(public), {"source", "academic_year", "generated_utc", "errors",
                                          "coverage", "courses"})
            self.assertIn("unofficial", public["source"].lower())
            self.assertEqual(public["coverage"], snapshot["coverage"])
            self.assertEqual(public["academic_year"], snapshot["academic_year"])
            private_catalog = Catalog.load(source)
            public_catalog = Catalog.load(destination)
            self.assertEqual(public_catalog.metadata.generated_utc, private_catalog.metadata.generated_utc)
            self.assertEqual(public_catalog.by_code.keys(), private_catalog.by_code.keys())
            for row in public["courses"]:
                expected = private_catalog.by_code[row["code"]]
                self.assertEqual(row, {**{key: getattr(expected, key) for key in FACTS}, **EMPTY_FIELDS})

    def test_failed_export_preserves_input_and_previous_output(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "private.json"
            destination = Path(directory) / "public.json"
            source.write_bytes(FIXTURE.read_bytes())
            with self.assertRaises(ValueError):
                export_public(source, source)
            self.assertEqual(source.read_bytes(), FIXTURE.read_bytes())
            export_public(source, destination)
            previous = destination.read_bytes()
            source.write_text("{}", encoding="utf-8")
            with self.assertRaises(ValueError):
                export_public(source, destination)
            self.assertEqual(destination.read_bytes(), previous)


class TestPublishedSnapshot(unittest.TestCase):
    def test_all_public_rows_and_faculty_counts(self):
        public = json.loads(PUBLIC_PATH.read_bytes())
        self.assertEqual(set(public), {"source", "academic_year", "generated_utc", "errors",
                                      "coverage", "courses"})
        self.assertEqual(public["source"], PUBLIC_SOURCE)
        rows = public["courses"]
        self.assertEqual(len(rows), 6497)
        self.assertEqual(len({row["code"] for row in rows}), 6497)
        keys = set(FACTS) | set(EMPTY_FIELDS)
        for row in rows:
            self.assertEqual(set(row), keys, row["code"])
            self.assertEqual({k: row[k] for k in EMPTY_FIELDS}, EMPTY_FIELDS, row["code"])
        catalog = Catalog.load(PUBLIC_PATH)
        self.assertEqual(catalog.metadata.coverage, dict(
            artsci=5368, engineering=557, architecture=124, music=327,
            kinesiology=107, information=22, medicine=21, nursing=16,
        ))
        self.assertEqual(catalog.metadata.multi_faculty_courses, 44)

    def test_lookup_search_filter_and_pagination(self):
        catalog = Catalog.load(PUBLIC_PATH)
        for code, title in [("CSC207H1", "Software Design"), ("MAT237Y1", "Multivariable Calculus with Proofs")]:
            self.assertEqual(catalog.by_code[code].title, title)
            self.assertEqual(catalog.search(code[:-2].lower(), "artsci", 1, 1).courses[0].code, code)
            matches = catalog.search(title.lower(), "artsci", 1, 100).courses
            self.assertIn(code, [course.code for course in matches])
        first = catalog.search("", "engineering", 1, 3)
        second = catalog.search("", "engineering", 2, 3)
        self.assertEqual(first.total, 557)
        six = first.courses + second.courses
        self.assertEqual(len({c.code for c in six}), 6)
        self.assertEqual(six, catalog.search("", "engineering", 1, 6).courses)
        self.assertTrue(all("engineering" in c.faculties for c in six))
