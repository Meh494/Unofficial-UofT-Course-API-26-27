"""Verified official U of T undergraduate calendar search pages (2026-27)."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Source:
    slug: str
    name: str
    url: str


SOURCES = (
    Source("artsci", "Arts & Science", "https://artsci.calendar.utoronto.ca/search-courses"),
    Source("engineering", "Engineering", "https://engineering.calendar.utoronto.ca/search-courses"),
    Source("architecture", "Daniels / Architecture", "https://daniels.calendar.utoronto.ca/search-courses"),
    Source("music", "Music", "https://music.calendar.utoronto.ca/search-courses"),
    Source("kinesiology", "Kinesiology", "https://kpe.calendar.utoronto.ca/search-courses"),
    Source("information", "Information", "https://ischool.calendar.utoronto.ca/search-courses"),
    Source("medicine", "Medicine (MD)", "https://md.calendar.utoronto.ca/search-courses"),
    Source("nursing", "Nursing", "https://nursing.calendar.utoronto.ca/search-courses"),
)

SOURCE_BY_SLUG = {s.slug: s for s in SOURCES}
