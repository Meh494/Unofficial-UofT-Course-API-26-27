"""Combine calendar listings that identify the same course."""


def merge_courses(existing: dict, incoming: dict) -> dict:
    combined = dict(existing)
    combined["faculties"] = list(dict.fromkeys(existing["faculties"] + incoming["faculties"]))
    urls = []
    for course in (existing, incoming):
        urls.append(course["source_url"])
        urls.extend(course.get("source_urls", []))
    combined["source_urls"] = list(dict.fromkeys(urls))
    # Calendar order determines the primary listing when sources disagree.
    for key in ("title", "description", "credits", "prerequisites", "corequisites", "exclusions"):
        if combined.get(key) in (None, "") and incoming.get(key) not in (None, ""):
            combined[key] = incoming[key]
    combined["source_fields"] = {**incoming.get("source_fields", {}), **existing.get("source_fields", {})}
    return combined
