"""Parse U of T Drupal course-search result listings (not full program pages).

No generated course details are fabricated: only items with an identifiable
course code in a course-result heading are accepted.
"""

from __future__ import annotations

import logging
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from .merge import merge_courses

# Most U of T courses use MAT237Y1/CSC207H1; MD courses can use ANS310Y.
REGULAR_HEADING = re.compile(r"^\s*(?P<code>[A-Z]{2,5}\d{3}[A-Z][0-9])\s*[-–:]\s*(?P<title>.+?)\s*$", re.I)
MEDICAL_HEADING = re.compile(r"^\s*(?P<title>.+?)\s*\[(?P<code>[A-Z]{2,5}\d{3}[A-Z])\]\s*$", re.I)
FIELD = re.compile(r"^(?P<key>Hours|Prerequisite|Corequisite|Exclusion|Recommended Preparation|Breadth Requirements|Credit Value|Fixed Credit|Course Category|Course Duration|Course Directors?|Chief Examiner|Mode of Delivery|Timetable|Availability|Course Experience|Enrolment Limits|Program Tags|Total AUs|Note)\s*:\s*(?P<value>.*)$", re.I)


def parse_heading(text: str):
    heading = " ".join(text.split())
    match = REGULAR_HEADING.match(heading) or MEDICAL_HEADING.match(heading)
    if not match:
        return None
    return match.group("code").upper(), match.group("title").strip()


def _parent_block(heading: Tag) -> Tag:
    # Drupal Views typically wraps each course in a .views-row. This avoids
    # accidentally capturing the entire page as one course description.
    for ancestor in heading.parents:
        if not isinstance(ancestor, Tag):
            continue
        classes = set(ancestor.get("class", []))
        if classes.intersection({"views-row", "view-row", "course-card", "course-result"}):
            return ancestor
        if ancestor.name in {"main", "body", "html"}:
            break
    # Fallback: find the smallest enclosing container with the heading and
    # substantive content, without another course heading.
    for ancestor in heading.parents:
        if not isinstance(ancestor, Tag) or ancestor.name in {"main", "body", "html"}:
            break
        candidate_headers = [h for h in ancestor.find_all(["h2", "h3", "h4"])
                             if parse_heading(h.get_text(" ", strip=True))]
        if len(candidate_headers) > 1:
            break
        if len(candidate_headers) == 1 and len(ancestor.get_text(" ", strip=True)) > len(heading.get_text(" ", strip=True)) + 20:
            return ancestor
    return heading


def _block_text(block: Tag) -> str:
    # HTML text nodes already contain the punctuation between inline course links.
    # Preserve those boundaries and insert breaks only for block elements.
    for br in block.find_all("br"):
        br.replace_with("\n")
    for paragraph in block.find_all(["p", "div", "li", "tr", "h2", "h3", "h4"]):
        paragraph.insert_before("\n")
        paragraph.insert_after("\n")
    return block.get_text()


def _extract_fields(block_text: str, code: str, title: str) -> dict:
    lines = [" ".join(ln.split()).strip() for ln in block_text.splitlines()]
    lines = [ln for ln in lines if ln]
    info: dict = {}
    narrative: list[str] = []
    for line in lines:
        if parse_heading(line) == (code, title):
            continue
        # Some Medical pages repeat the course title once before description.
        if line == f"{title} [{code}]" or line == f"{code} - {title}":
            continue
        m = FIELD.match(line)
        if m:
            key = m.group("key").lower().replace(" ", "_")
            value = m.group("value").strip()
            if value:
                info[key] = "\n".join(filter(None, (info.get(key), value)))
        elif not line.lower().startswith("program tags:"):
            narrative.append(line)
    info["description"] = "\n".join(narrative)
    return info


def _row_fields(block: Tag, code: str, title: str) -> dict:
    info = {}
    for field in block.select(".views-field"):
        classes = field.get("class", [])
        if "views-field-title" in classes:
            field.replace_with("\n")
            continue
        if "views-field-body" in classes or "views-field-field-desc" in classes:
            continue
        # Some calendars put the label beside .field-content, others inside it.
        label = field.select_one(".views-label") or field.find("strong")
        if label and label.get_text(strip=True).endswith(":"):
            key = label.get_text(strip=True).rstrip(":").strip()
            label.extract()
        else:
            key = next((c.removeprefix("views-field-field-") for c in classes
                        if c.startswith("views-field-field-")), "")
        if key:
            value = " ".join(_block_text(field).split())
            if value:
                info[re.sub(r"[\s-]+", "_", key.casefold())] = value
            field.replace_with("\n")
    # The remaining paragraphs may be inside a Drupal body field or directly in the row.
    return {**_extract_fields(_block_text(block), code, title), **info}


def parse_course_page(html: str, source, page_url: str | None = None) -> tuple[list[dict], bool]:
    soup = BeautifulSoup(html, "html.parser")
    # Prefer the actual search results; menu/footer frequently also have h3s.
    main = soup.select_one("main") or soup.select_one("#main-content") or soup
    results = main.select_one(".view-content") or main
    found: dict[str, dict] = {}
    headings = results.find_all(["h2", "h3", "h4"])
    for heading in headings:
        parsed = parse_heading(heading.get_text(" ", strip=True))
        if not parsed:
            if "js-views-accordion-group-header" in heading.get("class", []):
                logging.getLogger(__name__).warning("Unrecognized course heading on %s: %s",
                                                    page_url or source.url, heading.get_text(" ", strip=True))
            continue
        code, title = parsed
        block = _parent_block(heading)
        if block is heading:
            # Some printer-friendly course views place paragraphs as direct
            # siblings of headings rather than wrapping them in .views-row.
            # Never include the next course's content.
            parts = [heading.get_text(" ", strip=True)]
            for sibling in heading.next_siblings:
                if isinstance(sibling, Tag):
                    if (sibling.name in {"h2", "h3", "h4"} and
                            parse_heading(sibling.get_text(" ", strip=True))):
                        break
                    if any(parse_heading(h.get_text(" ", strip=True))
                           for h in sibling.find_all(["h2", "h3", "h4"])):
                        break
                    text = _block_text(sibling)
                    if text:
                        parts.append(text)
            extra = _extract_fields("\n".join(parts), code, title)
        else:
            extra = _row_fields(block, code, title)
        a = heading.find("a", href=True)
        listing_url = page_url or source.url
        source_url = urljoin(listing_url, a["href"]) if a else listing_url
        explicit_credit = extra.get("credit_value") or extra.get("fixed_credit")
        credits = float(explicit_credit) if re.fullmatch(r"\d+(?:\.\d+)?", explicit_credit or "") else None
        # Do not infer credits if explicit value absent; Music has exceptions.
        course = {
            "code": code,
            "title": title,
            "description": extra.get("description", ""),
            "faculty": source.name,
            "faculties": [source.slug],
            "credits": credits,
            "prerequisites": extra.get("prerequisite", ""),
            "corequisites": extra.get("corequisite", ""),
            "exclusions": extra.get("exclusion", ""),
            "source_url": source_url,
            "source_fields": {k: v for k, v in extra.items() if k != "description"},
        }
        found[code] = merge_courses(found[code], course) if code in found else course
    has_next = soup.select_one('a[rel~="next"], .pager__item--next a') is not None
    return list(found.values()), has_next


def parse_course_list(html: str, source) -> list[dict]:
    return parse_course_page(html, source)[0]
