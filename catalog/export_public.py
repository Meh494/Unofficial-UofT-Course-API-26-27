"""Export factual course metadata from a local snapshot for public distribution."""

import argparse
from pathlib import Path

from .scrape import write_snapshot
from .store import Catalog


ROOT = Path(__file__).resolve().parent.parent
PUBLIC_PATH = ROOT / "public_catalog" / "catalog.json"
PUBLIC_SOURCE = "Unofficial factual course catalog extracted from the University of Toronto faculty calendars."
FACT_FIELDS = {"code", "title", "faculty", "faculties", "credits", "source_url", "source_urls"}


def export_public(source: Path, destination: Path) -> int:
    if source.resolve() == destination.resolve():
        raise ValueError("The public destination must differ from the private input")
    catalog = Catalog.load(source)
    courses = []
    for code in sorted(catalog.by_code):
        facts = catalog.by_code[code].model_dump(include=FACT_FIELDS)
        courses.append({
            **facts,
            "description": "",
            "prerequisites": "",
            "corequisites": "",
            "exclusions": "",
            "source_fields": {},
        })
    metadata = catalog.metadata
    write_snapshot(destination, {
        "academic_year": metadata.academic_year,
        "generated_utc": metadata.generated_utc.isoformat(),
        "source": PUBLIC_SOURCE,
        "coverage": metadata.coverage,
        "errors": [],
        "courses": courses,
    })
    return len(courses)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT / "data" / "courses.json",
                        help="Private snapshot path (default: data/courses.json)")
    args = parser.parse_args()
    try:
        count = export_public(args.input, PUBLIC_PATH)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"Public catalog export failed: {exc}\n")
    print(f"Exported {count:,} courses to {PUBLIC_PATH}")


if __name__ == "__main__":
    main()
