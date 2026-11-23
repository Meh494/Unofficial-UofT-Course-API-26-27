"""Read-only HTTP access to a local UofT course snapshot."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime
import logging
import os
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from pydantic import BaseModel

from catalog.sources import SOURCE_BY_SLUG, SOURCES
from catalog.store import Catalog, Course, CourseCode, CoursePage, Metadata

DEFAULT_PATH = Path(__file__).resolve().parent / "data" / "courses.json"
UNAVAILABLE = {503: {"description": "The local snapshot could not be loaded."}}


class Health(BaseModel):
    status: str
    ready: bool
    courses: int
    generated_utc: datetime | None = None
    academic_year: str | None = None


class Faculty(BaseModel):
    id: str
    name: str
    url: str
    count: int


def require_catalog(request: Request) -> Catalog:
    catalog = request.app.state.catalog
    if catalog is None:
        raise HTTPException(503, detail="Course snapshot unavailable")
    return catalog


LoadedCatalog = Annotated[Catalog, Depends(require_catalog)]


def create_app(catalog_path: Path | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        path = catalog_path or Path(os.environ.get("COURSE_CATALOG_PATH", DEFAULT_PATH))
        try:
            app.state.catalog = Catalog.load(path)
        except (OSError, ValueError) as exc:
            logging.getLogger(__name__).error("Cannot load course snapshot %s: %s", path, exc)
            app.state.catalog = None
        yield

    app = FastAPI(title="Unofficial UofT Course API (2026–2027)", version="1.0.0",
                  description="An independent, read-only API for UofT academic calendar listings.",
                  lifespan=lifespan)

    @app.get("/health", responses={503: {"model": Health}})
    def health(request: Request, response: Response) -> Health:
        """Readiness and snapshot generation time for this worker."""
        catalog = request.app.state.catalog
        if catalog is None:
            response.status_code = 503
            return Health(status="unavailable", ready=False, courses=0)
        meta = catalog.metadata
        return Health(status="ok", ready=True, courses=meta.courses,
                      generated_utc=meta.generated_utc, academic_year=meta.academic_year)

    @app.get("/metadata", responses=UNAVAILABLE)
    def metadata(catalog: LoadedCatalog) -> Metadata:
        """Snapshot provenance, unique course count, and counts by faculty ID."""
        return catalog.metadata

    @app.get("/faculties", responses=UNAVAILABLE)
    def faculties(catalog: LoadedCatalog) -> list[Faculty]:
        """List the eight source calendars. Cross-listed courses count once per faculty."""
        return [Faculty(id=s.slug, name=s.name, url=s.url, count=len(catalog.by_faculty[s.slug]))
                for s in SOURCES]

    @app.get("/courses", responses=UNAVAILABLE)
    def list_courses(
        catalog: LoadedCatalog,
        q: Annotated[str, Query(max_length=200, description="Case-insensitive text or partial code.")] = "",
        faculty: Annotated[str, Query(max_length=64, description="Faculty ID from /faculties.")] = "",
        page: Annotated[int, Query(ge=1)] = 1,
        page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    ) -> CoursePage:
        """Filter by faculty, then rank by exact code, prefix, title, interior code, and description.

        Ties and unfiltered listings are sorted by code. Total is measured before pagination.
        """
        slug = faculty.strip().casefold()
        if slug and slug not in SOURCE_BY_SLUG:
            raise HTTPException(422, detail="Unknown faculty ID. See /faculties.")
        return catalog.search(q, slug, page, page_size)

    @app.get("/courses/{code}", responses={**UNAVAILABLE, 404: {"description": "Course not found."}})
    def get_course(code: CourseCode, catalog: LoadedCatalog) -> Course:
        """Look up the full course code, ignoring case."""
        course = catalog.by_code.get(code)
        if course is None:
            raise HTTPException(404, detail=f"Course {code} not found")
        return course

    return app


app = create_app()
