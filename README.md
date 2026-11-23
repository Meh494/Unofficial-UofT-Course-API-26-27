# Unofficial UofT Course API (2026–2027)

Search **6,497 University of Toronto courses** by code or title across eight faculty calendars. This independent project has no affiliation with or endorsement from the University of Toronto. Consult the official faculty calendar for academic decisions.

The public dataset in `public_catalog/catalog.json` contains factual metadata only. It includes course codes, titles, faculty memberships, numeric credits where published, and links to the official listings. Descriptions, prerequisites, corequisites, exclusions, and calendar notes are omitted. The full private snapshot stays local. The API loads the selected file once per worker at startup and serves requests offline.

## Install and try the API

Use Python 3.10 or later. From the repository root, these PowerShell commands start the API with the public catalog.

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
$env:COURSE_CATALOG_PATH = "public_catalog/catalog.json"
.\.venv\Scripts\python.exe -m uvicorn api:app --host 127.0.0.1 --port 8000
```

On Linux or macOS, use a POSIX shell.

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
COURSE_CATALOG_PATH=public_catalog/catalog.json python -m uvicorn api:app --port 8000
```

Check that `/health` reports `ready: true` and `courses: 6497`. The six-course handwritten fixture remains available at `tests/fixtures/catalog.json` for development and automated tests. [Swagger UI](http://127.0.0.1:8000/docs) · [Example lookup](http://127.0.0.1:8000/courses/csc207h1) · [Health](http://127.0.0.1:8000/health)

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

The API applies the faculty filter first. Exact codes rank first, followed by code prefixes, title substrings, and interior code substrings. Each course appears once at its highest rank. Ties and unfiltered listings sort by course code. The public catalog supports code and title searches. Other snapshots with populated descriptions can also return description matches at the lowest rank.

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
| `code`, `title` | Calendar identifier and published course title. |
| `faculty`, `faculties` | Primary faculty display name and all associated faculty IDs. |
| `credits` | Explicit numeric credit or JSON `null` when a single numeric value is unavailable. |
| `description`, `prerequisites`, `corequisites`, `exclusions` | Always `""` in the public dataset. Consult the official source for the narrative and requirements. |
| `source_url`, `source_urls` | Primary official source and all contributing listing URLs. Where a heading has no detail link, the URL identifies the listing page containing the course at capture time. |
| `source_fields` | Always `{}` in the public dataset. |

## Calendar coverage and data quality

The public export preserves the November 2026 snapshot's course identities, academic year, generation timestamp, and faculty counts. The running service reports metadata for the selected file.

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

The export contains 863 numeric credit values. For the other 5,634 courses, including courses with variable credit ranges, the public `credits` field is `null`. An empty requirement field gives no information about eligibility.

Coverage is limited to the eight listed calendars. Class times, live enrolment, and the separate UTM and UTSC catalogs are outside this snapshot. Official listing page numbers and content can change after capture.

## Run the tests

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

On Linux or macOS, run `python -m unittest discover -s tests -v` in the activated environment. The suite uses the six-course fixture, mocked scraper responses, temporary loopback servers, and the public export. It covers the public routes, ranking, pagination, duplicate handling, file failures, interrupted scrapes, and the public data format. GitHub Actions runs it on pushes and pull requests.

Maintainers with the November snapshot at `data/courses.json` and its original `data/courses-complete-backup.json` can also run `python -m unittest discover -s tests -p local_release.py -v` to check all original course identities and faculty counts.

## Regenerate the public catalog locally

From the repository root in an activated Python environment, run the exporter against the private `data/courses.json` snapshot.

```sh
python -m catalog.export_public
```

The command writes `public_catalog/catalog.json` using an explicit list of permitted fields, preserves the source timestamp and faculty coverage, and validates the result with `Catalog.load()` before replacing the previous export. It only reads the private input. The generated public file is the only catalog needed by a deployed service.

### Refresh the private input

The scraper is a separate command and requires internet access. By default it visits all eight calendars and writes a candidate to `data/courses-next.json`. The scraper is configured for the 2026–2027 calendars. Verify the edition at the sources before building a future academic year.

```powershell
.\.venv\Scripts\python.exe -m catalog.scrape --out data/courses-next.json
.\.venv\Scripts\python.exe -c "from pathlib import Path; from catalog.store import Catalog; print(Catalog.load(Path('data/courses-next.json')).metadata.model_dump_json(indent=2))"
```

Use `--snapshots data/raw_html` to retain the HTML for review, or `--faculties nursing,information --out data/subset.json` for a subset. The scraper follows the calendars' page numbering while a next-page link exists, retries transient failures, and waits between pages. An HTTP failure, empty result page, repeated page, or exceeded `--max-pages` guard ends the run before it can replace the destination. A successful run validates the candidate with the API's loader and writes it atomically.

Compare the candidate's coverage, course identities, and representative fields before exporting it. This PowerShell command selects the candidate as the export input.

```powershell
.\.venv\Scripts\python.exe -m catalog.export_public --input data/courses-next.json
```

Git ignores the entire `data/` directory, including private snapshots, backups, captured HTML, and optional PDF downloads. The API's existing local default with `COURSE_CATALOG_PATH` unset is `data/courses.json`. For public serving, select the public export explicitly.

## Deploy on Render

Deploy a revision containing `public_catalog/catalog.json` to the Git-connected Python web service. Use the repository root as the working directory. [Render's FastAPI guide](https://render.com/docs/deploy-fastapi)

| Service setting | Value |
| --- | --- |
| Build command | `python -m pip install -r requirements.txt` |
| Start command | `python -m uvicorn api:app --host 0.0.0.0 --port $PORT` |
| Environment variable | `COURSE_CATALOG_PATH=public_catalog/catalog.json` |
| Health check path | `/health` |

Select the snapshot in the service's **Environment** settings for the deployment containing the public file. The build installs dependencies and the worker reads the tracked export on startup. After deployment, verify `/health` reports 6,497 courses, `/metadata` lists eight faculties in `coverage`, and `/courses/CSC207H1` returns *Software Design* with empty narrative fields. A worker still serving the fixture reports six courses. A missing or invalid snapshot yields HTTP 503 and a loading error in the server log. [Render environment variables](https://render.com/docs/configure-environment-variables)

## License

The MIT license covers this project's code, documentation, and original test fixtures. University calendar content is outside the scope of that license. [MIT license](LICENSE)
