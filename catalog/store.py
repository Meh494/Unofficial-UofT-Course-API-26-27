"""Validated, process-local index of one calendar snapshot."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Annotated
from urllib.parse import urlsplit

from pydantic import (
    AfterValidator, AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints,
    ValidationError, ValidationInfo, field_validator,
)

from .merge import merge_courses
from .sources import SOURCE_BY_SLUG


def official_url(value: str) -> str:
    url = urlsplit(value)
    if url.scheme != "https" or not (url.hostname or "").endswith(".utoronto.ca"):
        raise ValueError("expected an official UofT HTTPS URL")
    return value


SourceURL = Annotated[str, AfterValidator(official_url)]
Nonempty = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
CourseCode = Annotated[str, StringConstraints(strip_whitespace=True, to_upper=True,
                                              pattern=r"^[a-zA-Z]{2,5}[0-9]{3}[a-zA-Z][0-9]?$")]


class Course(BaseModel):
    model_config = ConfigDict(strict=True, allow_inf_nan=False)

    code: CourseCode
    title: Nonempty
    description: str = ""
    faculty: Nonempty
    faculties: list[str] = Field(min_length=1)
    credits: float | None = Field(default=None, ge=0)
    prerequisites: str = ""
    corequisites: str = ""
    exclusions: str = ""
    source_url: SourceURL
    source_urls: list[SourceURL] = Field(default_factory=list, validate_default=True)
    source_fields: dict[str, str] = Field(default_factory=dict)

    @field_validator("faculties")
    @classmethod
    def known_faculties(cls, slugs: list[str]) -> list[str]:
        if any(slug not in SOURCE_BY_SLUG for slug in slugs):
            raise ValueError("unrecognized faculty ID")
        return list(dict.fromkeys(slugs))

    @field_validator("source_urls")
    @classmethod
    def include_primary_url(cls, urls: list[str], info: ValidationInfo) -> list[str]:
        primary = info.data.get("source_url")
        return list(dict.fromkeys([primary, *urls])) if primary else urls


class Snapshot(BaseModel):
    model_config = ConfigDict(strict=True)

    academic_year: Nonempty
    generated_utc: AwareDatetime
    source: Nonempty
    coverage: dict[str, Annotated[int, Field(ge=0)]]
    errors: list[str] = Field(max_length=0)
    courses: list[Course] = Field(min_length=1)


class Metadata(BaseModel):
    academic_year: str
    generated_utc: AwareDatetime
    source: str
    courses: int
    coverage: dict[str, int]
    multi_faculty_courses: int


class CoursePage(BaseModel):
    total: int
    page: int
    page_size: int
    courses: list[Course]


def search_text(value: str) -> str:
    return " ".join(value.casefold().split())


@dataclass(frozen=True)
class SearchEntry:
    course: Course
    code: str
    title: str
    description: str

    def rank(self, term: str) -> int | None:
        if self.code == term:
            return 0
        if self.code.startswith(term):
            return 1
        if term in self.title:
            return 2
        if term in self.code:
            return 3
        if term in self.description:
            return 4
        return None


class Catalog:
    def __init__(self, snapshot: Snapshot):
        self.by_code: dict[str, Course] = {}
        for course in snapshot.courses:
            existing = self.by_code.get(course.code)
            if existing is not None:
                course = Course(**merge_courses(existing.model_dump(), course.model_dump()))
            self.by_code[course.code] = course

        self.entries: list[SearchEntry] = []
        self.by_faculty: dict[str, list[SearchEntry]] = {slug: [] for slug in SOURCE_BY_SLUG}
        for code, course in sorted(self.by_code.items()):
            entry = SearchEntry(course, code.casefold(), search_text(course.title),
                                search_text(course.description))
            self.entries.append(entry)
            for slug in course.faculties:
                self.by_faculty[slug].append(entry)

        coverage = {slug: len(entries) for slug, entries in self.by_faculty.items() if entries}
        if coverage != snapshot.coverage:
            raise ValueError("snapshot coverage differs from unique course memberships")
        self.metadata = Metadata(
            academic_year=snapshot.academic_year, generated_utc=snapshot.generated_utc,
            source=snapshot.source, courses=len(self.entries), coverage=coverage,
            multi_faculty_courses=sum(len(c.faculties) > 1 for c in self.by_code.values()),
        )

    @classmethod
    def load(cls, path: Path) -> Catalog:
        try:
            snapshot = Snapshot.model_validate_json(path.read_bytes())
        except ValidationError as exc:
            first = exc.errors(include_input=False, include_url=False)[0]
            where = ".".join(map(str, first["loc"])) or "document"
            raise ValueError(f"Invalid snapshot at {where}: {first['msg']}") from None
        return cls(snapshot)

    def search(self, q: str, faculty: str, page: int, page_size: int) -> CoursePage:
        candidates = self.by_faculty[faculty] if faculty else self.entries
        term = search_text(q)
        if term:
            buckets: list[list[SearchEntry]] = [[] for _ in range(5)]
            for entry in candidates:
                rank = entry.rank(term)
                if rank is not None:
                    buckets[rank].append(entry)
            candidates = [entry for bucket in buckets for entry in bucket]
        start = (page - 1) * page_size
        return CoursePage(total=len(candidates), page=page, page_size=page_size,
                          courses=[e.course for e in candidates[start:start + page_size]])
