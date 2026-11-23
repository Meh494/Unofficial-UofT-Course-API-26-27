"""Scrape official U of T calendar course-search pages into a JSON snapshot.

Usage: python -m catalog.scrape --out data/courses-next.json
You must have internet access to the official University of Toronto sites.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import tempfile
import time
from urllib.parse import urlencode

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .merge import merge_courses
from .parse import parse_course_page
from .sources import SOURCES, SOURCE_BY_SLUG
from .store import Catalog


def session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": "Unofficial-UofT-Course-API/1.0 (+https://github.com/Meh494/Unofficial-UofT-Course-API-26-27)",
                      "Accept": "text/html,application/xhtml+xml"})
    retry = Retry(total=3, backoff_factor=1.0, status_forcelist=[429, 500, 502, 503, 504],
                  respect_retry_after_header=True)
    s.mount("https://", HTTPAdapter(max_retries=retry))
    return s


def scrape_source(s: requests.Session, source, max_pages: int, delay: float, snapshot_dir: Path | None) -> list[dict]:
    result: dict[str, dict] = {}
    for page in range(max_pages):
        url = source.url if page == 0 else f"{source.url}?{urlencode({'page': page})}"
        try:
            r = s.get(url, timeout=(10, 45))
            r.raise_for_status()
        except requests.RequestException as exc:
            raise RuntimeError(f"Failed to load {source.slug}: {url}: {exc}") from exc
        if snapshot_dir:
            output = snapshot_dir / source.slug / f"page-{page:04d}.html"
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(r.text, encoding="utf-8")
        parsed, has_next = parse_course_page(r.text, source, r.url)
        if not parsed:
            raise RuntimeError(f"No courses parsed on {url}; inspect source HTML, selectors or access controls.")
        new_codes = 0
        for item in parsed:
            code = item["code"]
            if code not in result:
                result[code] = item
                new_codes += 1
            else:
                result[code] = merge_courses(result[code], item)
        if new_codes == 0:
            raise RuntimeError(f"Pagination returned only repeated courses at {url}")
        print(f"  {source.slug}: page={page} items={len(parsed)} unique-so-far={len(result)}", flush=True)
        if not has_next:
            return list(result.values())
        time.sleep(delay)
    raise RuntimeError(f"{source.slug} has more pages than --max-pages={max_pages}")


def write_snapshot(output: Path, result: dict) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    f = tempfile.NamedTemporaryFile(dir=output.parent, mode="w", encoding="utf-8", delete=False)
    temporary = Path(f.name)
    try:
        with f:
            json.dump(result, f, ensure_ascii=False, indent=2, allow_nan=False)
        Catalog.load(temporary)
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)


def main(argv=None):
    p = argparse.ArgumentParser(description="Build a course catalog from UofT academic calendars")
    p.add_argument("--out", default="data/courses-next.json")
    p.add_argument("--faculties", help="Comma-separated source slugs; default all eight")
    p.add_argument("--max-pages", type=int, default=500, help="Pagination guard; increase if needed")
    p.add_argument("--delay", type=float, default=0.4, help="Seconds between requests; be polite")
    p.add_argument("--snapshots", help="Optional directory to retain downloaded HTML pages")
    args = p.parse_args(argv)
    slugs = (args.faculties.split(",") if args.faculties else [s.slug for s in SOURCES])
    invalid = set(slugs) - set(SOURCE_BY_SLUG)
    if invalid:
        p.error(f"Unknown faculties: {', '.join(sorted(invalid))}")
    if not math.isfinite(args.delay) or args.delay < .2:
        p.error("Use a delay >=0.2 seconds to avoid hammering calendar sites")
    if args.max_pages < 1:
        p.error("--max-pages must be positive")
    catalog: dict[str, dict] = {}
    coverage: dict[str, int] = {}
    with session() as s:
        for slug in slugs:
            source = SOURCE_BY_SLUG[slug]
            print(f"Fetching {source.name}: {source.url}", flush=True)
            try:
                courses = scrape_source(s, source, args.max_pages, args.delay,
                                        Path(args.snapshots) if args.snapshots else None)
            except RuntimeError as exc:
                p.exit(1, f"{exc}\n")
            coverage[slug] = len(courses)
            for course in courses:
                code = course["code"]
                if code in catalog:
                    catalog[code] = merge_courses(catalog[code], course)
                else:
                    course.setdefault("source_urls", [course["source_url"]])
                    catalog[code] = course

    result = {
        "academic_year": "2026-2027",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "source": "Public official University of Toronto academic calendars (not ACORN enrolment/timetable)",
        "coverage": coverage,
        "errors": [],
        "courses": sorted(catalog.values(), key=lambda c: c["code"]),
    }
    output = Path(args.out)
    write_snapshot(output, result)
    print(f"Wrote {len(catalog)} unique courses -> {output}")
    print("Coverage:", coverage)


if __name__ == "__main__":
    main()
