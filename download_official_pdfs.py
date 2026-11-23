"""Download two verified 2026-27 UofT calendar PDFs for offline reference.

This is OPTIONAL. The scraper uses HTML (better metadata and updates).
No 2026-27 direct PDF URL has been verified for the other faculties.
"""

from pathlib import Path
import requests

PDFS = {
    "artsci-2026-27.pdf": "https://artsci.calendar.utoronto.ca/sites/default/files/PDFs/2026-27_ARTSCI_Calendar.pdf",
    "engineering-2026-27.pdf": "https://engineering.calendar.utoronto.ca/sites/default/files/PDFs/Engineering-2026-2027.pdf",
}


def main():
    destination = Path("data/raw_pdfs")
    destination.mkdir(parents=True, exist_ok=True)
    for filename, url in PDFS.items():
        path = destination / filename
        print(f"Downloading {url} -> {path}")
        with requests.get(url, stream=True, timeout=(15, 120)) as response:
            response.raise_for_status()
            content_type = response.headers.get("Content-Type", "")
            iterator = response.iter_content(chunk_size=1024 * 128)
            first = next(iterator, b"")
            if not first.startswith(b"%PDF"):
                raise RuntimeError(f"Expected PDF, received {content_type} from {url}")
            with path.open("wb") as out:
                out.write(first)
                for chunk in iterator:
                    if chunk:
                        out.write(chunk)
        print(f"Saved {path} ({path.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
