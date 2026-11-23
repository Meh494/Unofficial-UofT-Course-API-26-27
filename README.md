# Unofficial UofT Course API (2026–2027)

Search University of Toronto courses by code, title, or description across eight faculty calendars. This independent project has no affiliation with or endorsement from the University of Toronto. Consult the official faculty calendar for academic decisions.

The API reads a local JSON snapshot once per worker at startup. The public repository includes the scraper and a six-course handwritten fixture. The complete scraped snapshot stays local pending confirmation of redistribution permissions. Calendar requests occur only when you run the scraper.

## Install and try the API

Use Python 3.10 or later. From the project directory, these PowerShell commands start the API with the included fixture.

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
$env:COURSE_CATALOG_PATH = (Resolve-Path tests/fixtures/catalog.json).Path
.\.venv\Scripts\python.exe -m uvicorn api:app --host 127.0.0.1 --port 8000
```

On Linux or macOS, use the same fixture with a POSIX shell.

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
COURSE_CATALOG_PATH=tests/fixtures/catalog.json python -m uvicorn api:app --port 8000
```

Open the interactive documentation or try a case-insensitive lookup. The fixture's descriptions, requirements, and credits are examples for development. To serve a local catalog, follow the scraper instructions below. [Swagger UI](http://127.0.0.1:8000/docs) · [Example lookup](http://127.0.0.1:8000/courses/csc207h1) · [Health](http://127.0.0.1:8000/health)

## HTTP endpoints

| GET path | Response |
| --- | --- |
| `/courses/{code}` | One course for a complete, case-insensitive code such as `CSC207H1` or `ANS310Y`. |
| `/courses` | Object with `total`, `page`, `page_size`, and a `courses` array. |
| `/faculties` | Eight objects with `id`, display `name`, official calendar `url`, and unique course `count`. |
| `/metadata` | Academic year, UTC generation time, source description, unique course count, per-faculty `coverage`, and number of cross-listed courses. |
| `/health` | Readiness, status, course count, academic year, and snapshot generation time. |
| `/docs`, `/redoc`, `/openapi.json` | Interactive API documentation, reference documentation, and the machine-readable OpenAPI schema. |

### Search and pagination

| Parameter on `/courses` | Behavior |
| --- | --- |
| `q` | Optional literal substring, up to 200 characters. Ignores case and normalizes whitespace. A blank query lists all matching courses. |
| `faculty` | Optional faculty ID from `/faculties`, case-insensitive. Matches any of a course's faculty memberships. |
| `page` | One-based integer. Default 1. |
| `page_size` | Integer from 1 to 100. Default 20. |

The API applies the faculty filter first. Exact codes rank first, followed by code prefixes, title substrings, interior code substrings, and description substrings. Each course appears once at its highest rank. Ties and unfiltered listings sort by course code. Searches cover the narrative description, while prerequisites and other structured metadata are available on the returned course.

`total` counts all matches before pagination. No matches and pages beyond the end return HTTP 200 with an empty array. A well-formed, unknown course code returns 404. Malformed codes, unknown faculty IDs, oversized queries, and invalid pagination return 422. Write methods return 405.

### Consume the API over HTTP

This example requests the first five Arts & Science matches for `CSC207`, then retrieves the full first result by code.

```python
import requests

base = "http://127.0.0.1:8000"
response = requests.get(f"{base}/courses", params={
    "q": "CSC207", "faculty": "artsci", "page": 1, "page_size": 5
}, timeout=5)
response.raise_for_status()
matches = response.json()["courses"]
if matches:
    detail = requests.get(f"{base}/courses/{matches[0]['code']}", timeout=5)
    detail.raise_for_status()
    course = detail.json()
    print(course["code"], course["title"])  # CSC207H1 Software Design
```

The list and lookup endpoints return the same course representation.

| Fields | Meaning |
| --- | --- |
| `code`, `title`, `description` | Calendar identifier, heading, and narrative. Missing descriptions use an empty string. |
| `faculty`, `faculties` | Primary faculty display name and all associated faculty IDs. |
| `credits` | Explicit numeric credit or JSON `null`. Variable credit ranges, when published, are retained in `source_fields.variable_credit`. |
| `prerequisites`, `corequisites`, `exclusions` | Published requirement text, including grades, alternatives, and permission clauses. An empty string means no value was extracted. |
| `source_url`, `source_urls` | Primary official source and all contributing listing URLs. Where a heading has no detail link, the URL identifies the listing page containing the course at capture time. |
| `source_fields` | Additional labeled calendar text, such as hours, breadth requirements, fixed credit, and recommended preparation. |

## Calendar coverage and data quality

The November 2026 local snapshot contained **6,497 distinct courses**. Counts below describe that capture. The running service reports counts for whichever snapshot you load.

| Faculty ID | Official calendar | Courses |
| --- | --- | ---: |
| `artsci` | [Arts & Science](https://artsci.calendar.utoronto.ca/search-courses) | 5,368 |
| `engineering` | [Engineering](https://engineering.calendar.utoronto.ca/search-courses) | 557 |
| `architecture` | [Daniels / Architecture](https://daniels.calendar.utoronto.ca/search-courses) | 124 |
| `music` | [Music](https://music.calendar.utoronto.ca/search-courses) | 327 |
| `kinesiology` | [Kinesiology](https://kpe.calendar.utoronto.ca/search-courses) | 107 |
| `information` | [Information](https://ischool.calendar.utoronto.ca/search-courses) | 22 |
| `medicine` | [Medicine (MD)](https://md.calendar.utoronto.ca/search-courses) | 21 |
| `nursing` | [Nursing](https://nursing.calendar.utoronto.ca/search-courses) | 16 |

These counts total 6,542 memberships. Of the 6,497 distinct courses, 43 appear in two faculties and one appears in three. For duplicate codes, the first listing supplies the primary record. Later listings fill missing fields and contribute their faculty IDs and URLs. Consult the contributing calendars for faculty-specific differences.

The scraper extracted structured requirements and credits from 221 official listing pages. It retains a course's published text and leaves missing values empty.

| Field in the November snapshot | Populated | Missing or without a single numeric value |
| --- | ---: | ---: |
| Description | 6,490 | 7 |
| Credits | 863 | 5,634 |
| Prerequisites | 4,585 | 1,912 |
| Corequisites | 251 | 6,246 |
| Exclusions | 2,095 | 4,402 |

Two Music courses have published variable credit ranges. A missing value conveys no conclusion about eligibility or credit weight. Text embedded by the university in a narrative can still include calendar notes. Kinesiology lists the same title and requirements under both `KPE433H` and `KPE433H1`. The snapshot retains the original full code `KPE433H1`. [Kinesiology listing](https://kpe.calendar.utoronto.ca/search-courses?page=2)

Coverage is limited to the eight listed calendars. Class times, live enrolment, and the separate UTM and UTSC catalogs are outside this snapshot. Official listing page numbers and content can change after capture.

## Run the tests

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

On Linux or macOS, run `python -m unittest discover -s tests -v` in the activated environment. The suite uses handwritten fixtures, mocked scraper responses, and temporary HTTP servers on loopback ports. It covers the public routes, ranking, pagination, duplicate handling, file failures, and interrupted scrapes. GitHub Actions runs it on pushes and pull requests.

Maintainers with the November snapshot at `data/courses.json` and its original `data/courses-complete-backup.json` can also run `python -m unittest discover -s tests -p local_release.py -v` to check all original course identities and faculty counts.

## Regenerate the snapshot

The scraper is a separate command and requires internet access. By default it visits all eight calendars and writes a candidate to `data/courses-next.json`. The scraper is configured for the 2026–2027 calendars. Verify the edition at the sources before building a future academic year.

```powershell
.\.venv\Scripts\python.exe -m catalog.scrape --out data/courses-next.json
.\.venv\Scripts\python.exe -c "from pathlib import Path; from catalog.store import Catalog; print(Catalog.load(Path('data/courses-next.json')).metadata.model_dump_json(indent=2))"
```

Use `--snapshots data/raw_html` to retain the HTML for review, or `--faculties nursing,information --out data/subset.json` for a subset. The scraper follows the calendars' page numbering while a next-page link exists, retries transient failures, and waits between pages. An HTTP failure, empty result page, repeated page, or exceeded `--max-pages` guard ends the run before it can replace the destination. A successful run validates the candidate with the API's loader and writes it atomically.

Compare coverage, course identities, and representative fields before selecting a candidate. To switch from the sample to the generated catalog, stop the local server, set its snapshot path, and restart it.

```powershell
$env:COURSE_CATALOG_PATH = (Resolve-Path data/courses-next.json).Path
.\.venv\Scripts\python.exe -m uvicorn api:app --host 127.0.0.1 --port 8000
```

In an activated POSIX environment, use `python -m catalog.scrape --out data/courses-next.json`, then `COURSE_CATALOG_PATH=data/courses-next.json python -m uvicorn api:app --port 8000`. With the environment variable unset, the API uses `data/courses.json`. Git ignores the entire `data/` directory, including snapshots, captured HTML, and optional PDF downloads from `download_official_pdfs.py`.

## Deployment configuration

Package `api.py`, `catalog/`, and `requirements.txt`. Install the dependencies and use `api:app` as the ASGI entry point. Supply the snapshot separately through a read-only mount and set `COURSE_CATALOG_PATH` to its absolute path.

For a future host that supplies a `PORT` environment variable, this POSIX start command runs one worker.

```sh
python -m uvicorn api:app --host 0.0.0.0 --port "${PORT:-8000}"
```

Use `GET /health` as the readiness probe. A missing, malformed, empty, or internally inconsistent snapshot returns HTTP 503 with `ready: false`. Data endpoints also return 503 and the server log records the loading error. Fix the file or path and restart the worker to rebuild its index. Each additional worker holds its own copy in memory.

## License

The MIT license covers this project's code, documentation, and original test fixtures. University calendar content is outside the scope of that license. [MIT license](LICENSE)
