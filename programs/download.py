"""Downloads the Qumran-Digital transcriptions, and optionally their word parsings, through the public API."""

import argparse
import json
import re
import sys
import threading
import time
import urllib.parse
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import partial
from html.parser import HTMLParser
from http.client import HTTPException, HTTPSConnection
from pathlib import Path

BASE_URL = "https://lexicon.qumran-digital.org/v1/qumran"
USER_AGENT = "qumran-digital-downloader/1.0 (academic research)"
RETRYABLE = {429, 500, 502, 503, 504}
PRINT = partial(print, flush=True)

Transport = Callable[[str], bytes]
Sleep = Callable[[float], None]


class FetchError(RuntimeError):
    """A request that failed permanently or after every retry."""


class StoppedError(RuntimeError):
    """Raised in a worker after the run has been interrupted."""


class HttpStatusError(RuntimeError):
    """An HTTP response with an error status."""

    def __init__(self, url: str, code: int) -> None:
        """Store the URL and the status code."""
        super().__init__(f"{url}: HTTP {code}")
        self.code = code


@dataclass(frozen=True)
class Entry:
    """One transcription in the index: its URL path, its siglum, and its corpus class."""

    path: str
    siglum: str
    kind: str


@dataclass(frozen=True)
class Selection:
    """Which transcriptions to download, and whether to fetch word parsings."""

    kinds: frozenset[str] | None = None
    sigla: frozenset[str] | None = None
    parsings: bool = False


@dataclass(frozen=True)
class Policy:
    """How many manuscripts run in parallel, the pause after each request, and the retry budget."""

    workers: int = 4
    pause: float = 0.25
    retries: int = 5
    sleep: Sleep = time.sleep


@dataclass
class Report:
    """The manuscripts a run completed and the ones that failed, with the error for each."""

    done: list[str] = field(default_factory=list)
    failed: dict[str, str] = field(default_factory=dict)


def https_transport(url: str) -> bytes:
    """Fetch an HTTPS URL with the downloader's user agent.

    The request does not ask the server to close the connection: when asked to, it cuts large responses short.
    """
    parts = urllib.parse.urlsplit(url)
    if parts.scheme != "https":
        raise ValueError(f"refusing non-HTTPS URL {url}")
    connection = HTTPSConnection(parts.netloc, timeout=120)
    try:
        connection.request("GET", parts.path, headers={"User-Agent": USER_AGENT})
        response = connection.getresponse()
        body = response.read()
    finally:
        connection.close()
    if response.status != 200:
        raise HttpStatusError(url, response.status)
    return body


def fetch(url: str, transport: Transport, retries: int = 5, sleep: Sleep = time.sleep) -> bytes:
    """Fetch a URL, retrying transient failures with exponential backoff."""
    for attempt in range(retries):
        try:
            return transport(url)
        except HttpStatusError as error:
            if error.code not in RETRYABLE:
                raise FetchError(str(error)) from error
            last = str(error)
        except (OSError, HTTPException) as error:
            last = f"{url}: {error}"
        if attempt < retries - 1:
            sleep(2.0**attempt)
    raise FetchError(last)


def transcription_url(path: str, suffix: str = "") -> str:
    """Return the API URL of a transcription, with the index's tilde kept literal."""
    return f"{BASE_URL}/transcriptions/{urllib.parse.quote(path, safe='~')}{suffix}"


class _IndexParser(HTMLParser):
    """Collects the transcription links of the index page."""

    def __init__(self) -> None:
        """Start with no entries."""
        super().__init__()
        self.entries: list[Entry] = []
        self._kind: str | None = None
        self._path: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Remember the class of a list item and the path of its link."""
        values = dict(attrs)
        classes = (values.get("class") or "").split()
        if tag == "li" and "list-item" in classes:
            self._kind = next((c for c in classes if c != "list-item"), "")
        elif tag == "a" and self._kind is not None and (values.get("href") or "").startswith("/transcriptions/"):
            self._path = (values.get("href") or "").split("/")[2]

    def handle_data(self, data: str) -> None:
        """Collect the link text, which may be split by a superscript."""
        if self._path is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        """Record the entry when its link closes."""
        if tag == "a" and self._path is not None and self._kind is not None:
            self.entries.append(Entry(path=self._path, siglum="".join(self._text).strip(), kind=self._kind))
            self._path = None
            self._kind = None
            self._text = []


def parse_index(html: str) -> list[Entry]:
    """Return the transcriptions listed on the index page."""
    parser = _IndexParser()
    parser.feed(html)
    return parser.entries


class _WordParser(HTMLParser):
    """Collects the ids of main-text words that carry lexical details."""

    def __init__(self) -> None:
        """Start outside any parallel line."""
        super().__init__()
        self.ids: list[str] = []
        self._parallel = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Track parallel lines and keep word spans that are not marked no-details."""
        values = dict(attrs)
        classes = (values.get("class") or "").split()
        if tag == "tr":
            self._parallel = "parallel-line" in classes
        elif tag == "span" and "word" in classes and "no-details" not in classes and not self._parallel:
            self.ids.append(values.get("id") or "")


def parse_word_ids(html: str) -> list[str]:
    """Return the reading ids of main-text words that have parsings, in text order."""
    parser = _WordParser()
    parser.feed(html)
    return [word for word in parser.ids if word]


def manuscript_id(shell: str) -> str:
    """Return the manuscript id that the transcription shell carries as transcription_id_<id>."""
    found = re.search(r'id="transcription_id_(\d+)"', shell)
    if found is None:
        message = "the transcription shell has no transcription_id"
        raise ValueError(message)
    return found.group(1)


def _write(path: Path, data: bytes) -> None:
    """Write a file atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(path.suffix + ".part")
    partial.write_bytes(data)
    partial.replace(path)


class Downloader:
    """Downloads the selected transcriptions in parallel, resuming where an earlier run stopped."""

    def __init__(self, out_dir: Path, transport: Transport = https_transport,
                 selection: Selection = Selection(), policy: Policy = Policy(),
                 log: Callable[[str], None] = PRINT) -> None:
        """Set the output folder, the transport, the selection, the request policy, and the progress log."""
        self.log = log
        self.out_dir = out_dir
        self.transport = transport
        self.selection = selection
        self.policy = policy
        self._stop = threading.Event()

    def _get(self, url: str) -> bytes:
        """Fetch a URL and pause afterwards, unless the run has been interrupted."""
        if self._stop.is_set():
            raise StoppedError(url)
        body = fetch(url, self.transport, self.policy.retries, self.policy.sleep)
        self.policy.sleep(self.policy.pause)
        return body

    def _folder(self, entry: Entry) -> Path:
        """Return the folder of a transcription."""
        return self.out_dir / "transcriptions" / entry.path

    def _files(self, entry: Entry) -> list[Path]:
        """Return the files a complete download of a transcription consists of."""
        names = ["transcription.html", "columns.json", "shell.html"]
        if self.selection.parsings:
            names += ["parsings.json", "syntax.json"]
        return [self._folder(entry) / name for name in names]

    def _selected(self, entries: Iterable[Entry]) -> list[Entry]:
        """Return the entries matching the kind and siglum filters."""
        kinds, sigla = self.selection.kinds, self.selection.sigla
        return [e for e in entries
                if (kinds is None or e.kind in kinds) and (sigla is None or e.siglum in sigla or e.path in sigla)]

    def _download(self, entry: Entry) -> None:
        """Fetch every file of one transcription and write them only once all have arrived."""
        self.log(f"start {entry.path}")
        transcription = self._get(transcription_url(entry.path))
        files = {
            "transcription.html": transcription,
            "columns.json": self._get(transcription_url(entry.path, "/columns")),
            "shell.html": self._get(transcription_url(entry.path, "/shell")),
        }
        if self.selection.parsings:
            words = parse_word_ids(transcription.decode("utf-8"))
            ms = manuscript_id(files["shell.html"].decode("utf-8"))
            files["parsings.json"] = self._journaled(entry, "parsings", words, self._word)
            files["syntax.json"] = self._journaled(entry, "syntax", words, lambda word: self._syntax(ms, word))
        for name, data in files.items():
            _write(self._folder(entry) / name, data)
        for name in ("parsings", "syntax"):
            (self._folder(entry) / f"{name}.jsonl").unlink(missing_ok=True)

    def _journaled(self, entry: Entry, name: str, words: list[str], one: Callable[[str], object]) -> bytes:
        """Fetch one record per word, reusing a finished file and a journal so an interrupted run can resume."""
        folder = self._folder(entry)
        finished, journal = folder / f"{name}.json", folder / f"{name}.jsonl"
        done: dict[str, object] = json.loads(finished.read_text(encoding="utf-8")) if finished.exists() else {}
        if journal.exists():
            for line in journal.read_text(encoding="utf-8").splitlines():
                record = json.loads(line)
                done[record["id"]] = record["data"]
        self.log(f"{entry.path} {name}: {len(words)} words, {sum(w in done for w in words)} already fetched")
        folder.mkdir(parents=True, exist_ok=True)
        with journal.open("a", encoding="utf-8") as log:
            for word in words:
                if word not in done:
                    done[word] = one(word)
                    log.write(json.dumps({"id": word, "data": done[word]}, ensure_ascii=False) + "\n")
                    log.flush()
                    if len(done) % 10 == 0:
                        self.log(f"{entry.path} {name}: {len(done)}/{len(words)} words")
        return json.dumps({word: done[word] for word in words}, ensure_ascii=False, indent=1).encode("utf-8")

    def _syntax(self, ms: str, word: str) -> object:
        """Fetch the dependency links of one word reading."""
        return json.loads(self._get(f"{BASE_URL}/manuscript/{ms}/syntactic-data/{word}"))

    def _word(self, word: str) -> dict[str, object]:
        """Fetch the parsings and lemmas of one word reading."""
        parsings = json.loads(self._get(f"{BASE_URL}/manuscript-word-reading-parsings/{word}"))["parsings"]
        lemmas = json.loads(self._get(f"{BASE_URL}/manuscript-word-reading-details/{word}"))["lemmas"]
        return {"parsings": parsings, "lemmas": lemmas}

    def _manifest(self, selected: list[Entry], versions: list[str], report: Report, *, interrupted: bool) -> None:
        """Write the manifest of this run."""
        manifest = {
            "source": BASE_URL,
            "licence": "CC BY-SA 4.0 (notice on each transcription shell)",
            "data_version": max(versions),
            "downloaded": datetime.now(UTC).isoformat(timespec="seconds"),
            "parsings": self.selection.parsings,
            "interrupted": interrupted,
            "entries": [{"path": e.path, "siglum": e.siglum, "kind": e.kind} for e in selected],
            "failed": report.failed,
        }
        _write(self.out_dir / "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=1).encode("utf-8"))

    def run(self) -> Report:
        """Download the index and every selected, unfinished transcription, and write the manifest."""
        self.log("fetching the transcription index")
        index = self._get(f"{BASE_URL}/transcription-index")
        versions = json.loads(self._get(f"{BASE_URL}/data-version-names"))["versionDates"]
        entries = parse_index(index.decode("utf-8"))
        _write(self.out_dir / "transcription-index.html", index)
        selected = self._selected(entries)
        pending = [e for e in selected if not all(f.exists() for f in self._files(e))]
        self.log(f"{len(pending)} transcriptions to download, {len(selected) - len(pending)} already complete")
        report = Report(done=[e.path for e in selected if e not in pending])
        pool = ThreadPoolExecutor(max_workers=self.policy.workers)
        try:
            futures = {pool.submit(self._download, entry): entry for entry in pending}
            for future in as_completed(futures):
                entry = futures[future]
                try:
                    future.result()
                    report.done.append(entry.path)
                    self.log(f"done {entry.path} ({len(report.done)}/{len(selected)})")
                except FetchError as error:
                    report.failed[entry.path] = str(error)
                    self.log(f"failed {entry.path}: {error}")
                except Exception as error:
                    report.failed[entry.path] = f"{type(error).__name__}: {error}"
                    self.log(f"failed {entry.path}: {error}")
        except BaseException:
            self._stop.set()
            pool.shutdown(wait=True, cancel_futures=True)
            self._manifest(selected, versions, report, interrupted=True)
            raise
        pool.shutdown(wait=True)
        self._manifest(selected, versions, report, interrupted=False)
        self.log(f"finished: {len(report.done)} complete, {len(report.failed)} failed")
        return report


def main(argv: list[str] | None = None) -> int:
    """Parse the command line, run the download, and print a summary."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True, help="output folder")
    parser.add_argument("--kind", action="append", choices=["dss", "dss-biblical", "non-dss"],
                        help="corpus class to include, repeatable (default: all)")
    parser.add_argument("--siglum", action="append", help="siglum to include, repeatable (default: all)")
    parser.add_argument("--parsings", action="store_true",
                        help="also fetch parsings and lemmas of every word that has them (one request pair per word)")
    parser.add_argument("--workers", type=int, default=4, help="parallel manuscripts (default 4)")
    parser.add_argument("--pause", type=float, default=0.25, help="seconds to wait after each request (default 0.25)")
    args = parser.parse_args(argv)
    selection = Selection(kinds=frozenset(args.kind) if args.kind else None,
                          sigla=frozenset(args.siglum) if args.siglum else None, parsings=args.parsings)
    try:
        report = Downloader(args.out, selection=selection, policy=Policy(workers=args.workers, pause=args.pause)).run()
    except KeyboardInterrupt:
        print("interrupted, rerun the same command to resume")
        return 130
    return 1 if report.failed else 0


if __name__ == "__main__":
    sys.exit(main())
