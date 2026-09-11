#!/usr/bin/env python3
"""Download and prepare Zenius-I-vanisher simfile IDs into an external song library."""

from __future__ import annotations

import argparse
from http.client import HTTPException
from html.parser import HTMLParser
import json
from pathlib import Path, PurePosixPath
import shutil
import stat
import subprocess
import sys
from tempfile import TemporaryDirectory
from urllib.parse import parse_qs, urljoin, urlparse
from urllib.request import Request, urlopen
from zipfile import BadZipFile, ZipFile

import prepare_songs


BASE_URL = "https://zenius-i-vanisher.com/v5.2/"
MAX_DOWNLOAD_BYTES = 256 * 1024 * 1024
MAX_EXTRACTED_BYTES = 512 * 1024 * 1024


def read_ids(path: Path) -> list[int]:
    """Read one positive ID per line, allowing comments and duplicate entries."""
    result = []
    for number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        value = line.split("#", 1)[0].strip()
        if not value:
            continue
        if not value.isascii() or not value.isdecimal() or int(value) <= 0:
            raise ValueError(f"{path}:{number}: expected a positive simfile ID")
        simfile_id = int(value)
        if simfile_id not in result:
            result.append(simfile_id)
    return result


class SimfilePage(HTMLParser):
    """Collect the heading and table rows without depending on the site's CSS."""

    def __init__(self) -> None:
        super().__init__()
        self.heading = ""
        self.in_heading = False
        self.row: list[str] = []
        self.cell: list[str] | None = None
        self.rows: list[list[str]] = []
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "h1":
            self.in_heading = True
        elif tag == "tr":
            self.row = []
        elif tag == "td":
            self.cell = []
        elif tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.links.append(href)

    def handle_endtag(self, tag: str) -> None:
        if tag == "h1":
            self.in_heading = False
        elif tag == "td" and self.cell is not None:
            self.row.append(" ".join("".join(self.cell).split()))
            self.cell = None
        elif tag == "tr":
            self.rows.append(self.row)

    def handle_data(self, data: str) -> None:
        if self.in_heading:
            self.heading += data
        if self.cell is not None:
            self.cell.append(data)


def parse_page(html: str, simfile_id: int) -> dict[str, object]:
    page = SimfilePage()
    page.feed(html)
    title, separator, artist = page.heading.strip().partition(" / ")
    if not title:
        raise ValueError("simfile page has no song heading")
    download_url = None
    for link in page.links:
        url = urljoin(BASE_URL, link)
        parsed = urlparse(url)
        query = parse_qs(parsed.query)
        if (parsed.scheme == "https" and parsed.netloc == "zenius-i-vanisher.com"
                and parsed.path == "/v5.2/download.php"
                and query.get("type") == ["ddrsimfile"]
                and query.get("simfileid") == [str(simfile_id)]):
            download_url = url
            break
    if download_url is None:
        raise ValueError("simfile page has no matching ZIP download link")
    updated_by = next((row[1] for row in page.rows
                       if len(row) >= 2 and row[0] == "Last Updated By"), "")
    return {
        "title": title,
        "artist": artist if separator else "",
        "source_url": f"{BASE_URL}viewsimfile.php?simfileid={simfile_id}",
        "ziv_simfile_id": simfile_id,
        "ziv_last_updated_by": updated_by,
        "download_url": download_url,
    }


def download(url: str, output: Path) -> None:
    """Publish a download only after the entire response has arrived."""
    temporary = output.with_name(output.name + ".part")
    request = Request(url, headers={"User-Agent": "pi-dance-song-importer/1.0"})
    try:
        with urlopen(request, timeout=60) as response, temporary.open("wb") as target:
            expected = response.headers.get("Content-Length")
            size = 0
            while chunk := response.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_DOWNLOAD_BYTES:
                    raise ValueError("download exceeds 256 MiB limit")
                target.write(chunk)
            if expected is not None and size != int(expected):
                raise ValueError("incomplete download")
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)


def write_json(path: Path, value: dict[str, object]) -> None:
    temporary = path.with_name(path.name + ".part")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def extract_bundle(archive: Path, output: Path) -> Path:
    """Extract a single song, rejecting unsafe paths and ambiguous chart bundles."""
    with ZipFile(archive) as zipped:
        members = zipped.infolist()
        if len(members) > 10000 or sum(item.file_size for item in members) > MAX_EXTRACTED_BYTES:
            raise ValueError("ZIP exceeds extraction limits")
        for item in members:
            path = PurePosixPath(item.filename)
            if (path.is_absolute() or ".." in path.parts or "\\" in item.filename
                    or ":" in item.filename or stat.S_ISLNK(item.external_attr >> 16)):
                raise ValueError(f"unsafe ZIP entry: {item.filename}")
            if item.flag_bits & 1:
                raise ValueError("encrypted ZIP entries are unsupported")
        zipped.extractall(output)
    charts = sorted(path for path in output.rglob("*")
                    if path.suffix.lower() == ".sm" and "__MACOSX" not in path.parts)
    if len(charts) != 1:
        raise ValueError(f"expected one .sm chart in ZIP, found {len(charts)}; SSC-only bundles are unsupported")
    # The existing converter and runtime use the lower-case extension.
    chart = charts[0]
    if chart.suffix != ".sm":
        chart = chart.rename(chart.with_suffix(".sm"))
    return chart.parent


def restore_sources(source: Path, destination: Path) -> None:
    """Restore missing original files, leaving local files and generated metadata intact."""
    for path in sorted(source.rglob("*")):
        relative = path.relative_to(source)
        if relative == Path("song.json"):
            continue
        target = destination / relative
        if not target.resolve().is_relative_to(destination.resolve()):
            raise ValueError(f"source target escapes song directory: {target}")
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        elif not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_name(target.name + ".part")
            shutil.copyfile(path, temporary)
            temporary.replace(target)


def import_song(simfile_id: int, destination: Path) -> None:
    cache = destination / ".ziv-cache" / str(simfile_id)
    cache.mkdir(parents=True, exist_ok=True)
    page_path = cache / "page.json"
    if page_path.exists():
        page = prepare_songs.existing_metadata(page_path)
    else:
        html_path = cache / "page.html"
        download(f"{BASE_URL}viewsimfile.php?simfileid={simfile_id}", html_path)
        page = parse_page(html_path.read_text(encoding="utf-8-sig"), simfile_id)
        write_json(page_path, page)
    archive = cache / "source.zip"
    if not archive.exists():
        print(f"{simfile_id}: downloading {page['title']}", flush=True)
        download(str(page["download_url"]), archive)
    bundle = destination / f"ziv-{simfile_id}"
    with TemporaryDirectory(prefix="extract-", dir=cache) as temporary:
        try:
            source = extract_bundle(archive, Path(temporary))
        except BadZipFile:
            archive.unlink(missing_ok=True)
            raise
        bundle.mkdir(exist_ok=True)
        restore_sources(source, bundle)
    # Site metadata seeds new bundles; the converter preserves these values and
    # any subsequent user edits while adding the runtime fields.
    metadata_path = bundle / "song.json"
    metadata = {key: value for key, value in page.items() if key != "download_url"}
    existing = prepare_songs.existing_metadata(metadata_path)
    metadata.update(existing)
    if metadata != existing:
        write_json(metadata_path, metadata)
    prepare_songs.prepare_song(bundle, overwrite=False, dry_run=False)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ids_file", type=Path, help="external text file containing one simfile ID per line")
    parser.add_argument("destination", type=Path, help="external song directory to populate")
    args = parser.parse_args()
    repository = Path(__file__).resolve().parents[1]
    if any(path.resolve().is_relative_to(repository) for path in (args.ids_file, args.destination)):
        parser.error("keep the ID list and downloaded song library outside this repository")
    try:
        ids = read_ids(args.ids_file)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    if not ids:
        parser.error("ID list is empty")
    missing = [name for name in ("ffmpeg", "ffprobe", "magick") if shutil.which(name) is None]
    if missing:
        parser.error(f"install required conversion tools: {', '.join(missing)}")
    failures = 0
    for simfile_id in ids:
        try:
            import_song(simfile_id, args.destination.expanduser().resolve())
        except (OSError, ValueError, BadZipFile, HTTPException,
                NotImplementedError, subprocess.CalledProcessError) as error:
            failures += 1
            print(f"{simfile_id}: failed: {error}", file=sys.stderr)
    print(f"{len(ids) - failures}/{len(ids)} songs prepared; {failures} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
