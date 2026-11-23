from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
import socket
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import requests
import uvicorn

from api import create_app
from catalog.sources import SOURCE_BY_SLUG
from catalog.store import Catalog

FIXTURE = Path(__file__).parent / "fixtures" / "catalog.json"


def record(code, title="Example", faculty="artsci", **kwargs):
    source = SOURCE_BY_SLUG[faculty]
    return dict(code=code, title=title, faculties=[faculty], faculty=source.name,
                source_url=source.url, **kwargs)


def snapshot(courses):
    memberships = {(slug, c["code"].strip().upper()) for c in courses for slug in c["faculties"]}
    coverage = {}
    for slug, _ in memberships:
        coverage[slug] = coverage.get(slug, 0) + 1
    return {"academic_year": "2026-2027", "generated_utc": "2026-10-01T12:00:00Z",
            "source": "Official UofT calendars", "errors": [], "coverage": coverage,
            "courses": courses}


@contextmanager
def serve(path):
    """Exercise the normal ASGI lifespan and HTTP stack on an ephemeral loopback port."""
    server = uvicorn.Server(uvicorn.Config(create_app(path), log_level="error", access_log=False))
    with socket.socket() as sock, requests.Session() as client:
        client.trust_env = False
        sock.bind(("127.0.0.1", 0))
        origin = f"http://127.0.0.1:{sock.getsockname()[1]}"
        worker = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
        worker.start()
        try:
            deadline = time.monotonic() + 10
            while not server.started:
                if not worker.is_alive() or time.monotonic() >= deadline:
                    raise RuntimeError("Test server did not start")
                time.sleep(.01)
            yield lambda method, route, **kw: client.request(method, origin + route, timeout=5, **kw)
        finally:
            server.should_exit = True
            worker.join(timeout=10)
            if worker.is_alive():
                raise RuntimeError("Test server did not stop")


class TestCatalogAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        server = serve(FIXTURE)
        cls.request = staticmethod(server.__enter__())
        cls.addClassCleanup(server.__exit__, None, None, None)

    def get(self, route, **params):
        response = self.request("GET", route, params=params)
        self.assertEqual(response.status_code, 200, response.text[:200])
        return response.json()

    def test_list_preserves_all_course_identities(self):
        rows = json.loads(FIXTURE.read_bytes())["courses"]
        expected = {c["code"]: (c["title"], c["faculties"]) for c in rows}
        result = self.get("/courses")
        self.assertEqual(result["total"], len(rows))
        self.assertEqual({c["code"]: (c["title"], c["faculties"]) for c in result["courses"]}, expected)

    def test_health_metadata_and_faculty_counts(self):
        health = self.get("/health")
        meta = self.get("/metadata")
        faculties = self.get("/faculties")
        self.assertTrue(health["ready"])
        self.assertEqual((health["status"], health["courses"]), ("ok", 6))
        self.assertEqual(health["courses"], meta["courses"])
        self.assertEqual(health["generated_utc"], meta["generated_utc"])
        self.assertEqual(meta["academic_year"], "2026-2027")
        self.assertEqual(meta["multi_faculty_courses"], 1)
        self.assertEqual(meta["coverage"], dict(artsci=3, engineering=2, music=1, medicine=1))
        self.assertEqual({f["id"] for f in faculties}, set(SOURCE_BY_SLUG))
        for f in faculties:
            self.assertEqual(f["count"], meta["coverage"].get(f["id"], 0))
            self.assertEqual(self.get("/courses", faculty=f["id"], page_size=1)["total"], f["count"])

    def test_lookup_course_and_requirements(self):
        course = self.get("/courses/cSc207h1")
        self.assertEqual((course["title"], course["faculties"]), ("Software Design", ["artsci"]))
        self.assertEqual(course["prerequisites"], "Example prerequisite text.")
        self.assertEqual(course["exclusions"], "Example exclusion text.")
        self.assertIsNone(course["credits"])
        self.assertIn(course["source_url"], course["source_urls"])
        self.assertEqual(self.get("/courses/DEM310Y")["faculty"], "Medicine (MD)")
        self.assertEqual(self.get("/courses/DEM254H1")["credits"], .17)

    def test_searches_and_faculty_filter(self):
        for q, code in [("  MaT237  ", "MAT237Y1"), ("cSc207", "CSC207H1")]:
            results = self.get("/courses", q=q, faculty=" ARTSCI ", page_size=100)["courses"]
            self.assertIn(code, [c["code"] for c in results])
            self.assertTrue(all("artsci" in c["faculties"] for c in results))
            self.assertEqual(results[0]["code"], code)
        titles = self.get("/courses", q="  software   design  ", faculty="artsci")["courses"]
        self.assertIn("CSC207H1", [c["code"] for c in titles])
        self.assertEqual(self.get("/courses", faculty="nursing", q="CSC207")["total"], 0)
        self.assertEqual(self.get("/courses", q="no-such-course-xyz")["courses"], [])

    def test_pagination(self):
        first = self.get("/courses", page_size=3)
        second = self.get("/courses", page=2, page_size=3)
        six = self.get("/courses", page_size=6)
        self.assertEqual((first["page"], second["page"], second["page_size"]), (1, 2, 3))
        self.assertEqual(first["total"], second["total"])
        self.assertEqual(first["courses"] + second["courses"], six["courses"])
        codes = [c["code"] for c in six["courses"]]
        self.assertEqual(codes, sorted(set(codes)))
        self.assertEqual(self.get("/courses", page=10000)["courses"], [])

    def test_invalid_requests_and_missing_courses(self):
        for params in [dict(page=0), dict(page="bad"), dict(page_size=-1), dict(page_size=101),
                       dict(faculty="made-up"), dict(q="a" * 201)]:
            with self.subTest(params=params):
                self.assertEqual(self.request("GET", "/courses", params=params).status_code, 422)
        self.assertEqual(self.request("GET", "/courses/ZZZ999H1").status_code, 404)
        self.assertEqual(self.request("GET", "/courses/!").status_code, 422)
        for method in ["POST", "DELETE", "PATCH", "PUT"]:
            self.assertEqual(self.request(method, "/courses/CSC207H1").status_code, 405)

    def test_openapi_and_documentation(self):
        schema = self.get("/openapi.json")
        self.assertEqual(schema["info"]["title"], "Unofficial UofT Course API (2026–2027)")
        self.assertEqual(set(schema["paths"]),
                         {"/courses", "/courses/{code}", "/faculties", "/metadata", "/health"})
        for route in ["/docs", "/redoc"]:
            self.assertEqual(self.request("GET", route).status_code, 200)


class TestSnapshotHandling(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.path = Path(folder.name) / "courses.json"

    def save(self, data):
        self.path.write_text(json.dumps(data), encoding="utf-8")

    def test_ranking_ties_partial_codes_and_load_once(self):
        self.save(snapshot([
            record("ZZZ100H1", description="Mentions DEV123H"), record("ART220H1", "DEV123H seminar"),
            record("DEV123H2"), record("DEV123H"), record("DEV123H1"),
            record("ART210H1", "DEV123H practicum"),
        ]))
        with patch.object(Catalog, "load", wraps=Catalog.load) as load, serve(self.path) as request:
            self.path.unlink()
            result = request("GET", "/courses", params={"q": "dev123h"}).json()
            self.assertEqual([c["code"] for c in result["courses"]],
                             ["DEV123H", "DEV123H1", "DEV123H2", "ART210H1", "ART220H1", "ZZZ100H1"])
            self.assertEqual(request("GET", "/courses", params={"q": "v123", "page_size": 2,
                             "page": 2}).json()["courses"][0]["code"], "DEV123H")
            self.assertEqual(request("GET", "/courses/dev123h").status_code, 200)
            self.assertTrue(request("GET", "/health").json()["ready"])
            load.assert_called_once_with(self.path)

    def test_duplicate_rows_merge_before_counting_or_filtering(self):
        self.save(snapshot([record("DEV123H1", title="First title", credits=0),
                            record("dev123h1", faculty="engineering", title="Other title",
                                   description="Second listing", credits=1, prerequisites="Permission")]))
        with serve(self.path) as request:
            for slug in ["artsci", "engineering"]:
                result = request("GET", "/courses", params={"faculty": slug}).json()
                self.assertEqual(result["total"], 1)
                course, = result["courses"]
                self.assertEqual(course["faculties"], ["artsci", "engineering"])
                self.assertEqual(len(course["source_urls"]), 2)
                self.assertEqual((course["title"], course["credits"]), ("First title", 0))
                self.assertEqual((course["description"], course["prerequisites"]),
                                 ("Second listing", "Permission"))
            self.assertEqual(request("GET", "/metadata").json()["courses"], 1)

    def test_missing_and_malformed_snapshot_http_responses(self):
        for contents in [None, b"{", b"\xff", b"[]"]:
            with self.subTest(contents=contents):
                if contents is not None:
                    self.path.write_bytes(contents)
                with self.assertLogs("api", level="ERROR"), serve(self.path) as request:
                    for route in ["/health", "/courses", "/courses/CSC207H1", "/metadata", "/faculties"]:
                        response = request("GET", route)
                        self.assertEqual(response.status_code, 503)
                        if route == "/health":
                            self.assertFalse(response.json()["ready"])
                        self.assertNotIn(str(self.path), response.text)

    def test_reject_invalid_data_before_serving_any_rows(self):
        sample = record("MAT237Y1")
        good = snapshot([sample])
        for change in [dict(courses=[]), dict(courses={}), dict(courses=[None]),
                       dict(coverage={"artsci": 2}), dict(errors=["timeout"]),
                       dict(generated_utc="unknown"), dict(courses=[dict(sample, faculties=[])]),
                       dict(courses=[dict(sample, title=" ")]), dict(courses=[dict(sample, code="!")]),
                       dict(courses=[dict(sample, faculties=["unknown"])]),
                       dict(courses=[dict(sample, credits="0.5")]), dict(courses=[dict(sample, credits=-1)]),
                       dict(courses=[dict(sample, credits=float("nan"))]),
                       dict(courses=[dict(sample, source_url="https://example.org")])]:
            with self.subTest(change=change):
                self.save({**good, **change})
                with self.assertRaises(ValueError):
                    Catalog.load(self.path)
