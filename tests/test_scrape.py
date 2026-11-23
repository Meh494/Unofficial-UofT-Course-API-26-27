from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from requests import ConnectionError, Response

from catalog import scrape
from catalog.sources import SOURCE_BY_SLUG


def page(code, number=0, has_next=False):
    listing = SOURCE_BY_SLUG["artsci"].url
    result = Response()
    result.status_code = 200
    result.url = listing if not number else f"{listing}?page={number}"
    next_link = f'<a rel="next" href="?page={number + 1}">Next</a>' if has_next else ""
    result._content = (f'<div class="views-row"><h3>{code} - Example</h3><p>A description.</p>'
                       f'</div>{next_link}').encode()
    return result


class TestScrape(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.path = Path(folder.name) / "candidate.json"
        self.path.write_text("previous contents", encoding="utf-8")

    def build(self, responses, *args):
        with patch.object(scrape, "session") as session, patch.object(scrape.time, "sleep"), \
                redirect_stdout(io.StringIO()):
            session.return_value.__enter__.return_value.get.side_effect = responses
            scrape.main(["--faculties", "artsci", "--out", str(self.path), *args])

    def test_two_pages_keep_listing_urls_and_coverage(self):
        self.build([page("MAT100H1", has_next=True), page("MAT200H1", 1)])
        data = json.loads(self.path.read_bytes())
        self.assertEqual(data["coverage"], {"artsci": 2})
        self.assertEqual(data["courses"][1]["source_url"], SOURCE_BY_SLUG["artsci"].url + "?page=1")
        self.assertEqual(data["errors"], [])

    def test_incomplete_runs_preserve_previous_file(self):
        first = page("MAT100H1", has_next=True)
        for responses, args in [
            ([first, ConnectionError("connection interrupted")], []),
            ([first, page("MAT100H1", 1)], []),
            ([first, page("Unexpected heading", 1)], []),
            ([first], ["--max-pages", "1"]),
        ]:
            with self.subTest(args=args, responses=responses):
                with self.assertRaises(SystemExit) as error:
                    self.build(responses, *args)
                self.assertEqual(error.exception.code, 1)
                self.assertEqual(self.path.read_text(encoding="utf-8"), "previous contents")

    def test_serialization_failure_preserves_previous_file(self):
        with self.assertRaises(TypeError):
            scrape.write_snapshot(self.path, {"unexpected": object()})
        self.assertEqual(self.path.read_text(encoding="utf-8"), "previous contents")
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    def test_invalid_snapshot_preserves_previous_file(self):
        with self.assertRaises(ValueError):
            scrape.write_snapshot(self.path, {"courses": []})
        self.assertEqual(self.path.read_text(encoding="utf-8"), "previous contents")
