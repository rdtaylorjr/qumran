"""Tests for the Qumran-Digital downloader."""

import importlib.util
import json
import sys
from http.client import IncompleteRead
from pathlib import Path

import pytest

PROGRAM = Path(__file__).resolve().parent.parent / "programs" / "download.py"
spec = importlib.util.spec_from_file_location("download", PROGRAM)
download = importlib.util.module_from_spec(spec)
sys.modules["download"] = download
spec.loader.exec_module(download)

from download import (  # noqa: E402
    BASE_URL,
    Downloader,
    Entry,
    FetchError,
    HttpStatusError,
    Policy,
    Selection,
    fetch,
    manuscript_id,
    parse_index,
    parse_word_ids,
    transcription_url,
    urllib_transport,
)

VERSION = "2026-10-06/index.html?v=2026-10-06"
INDEX = f"""<ol id="item-list" class="item-list">
<li class="list-item dss"><a href="/transcriptions/1QS/{VERSION}" class="text-href-link">1QS</a></li>
<li class="list-item dss"><a href="/transcriptions/1QH^a^/{VERSION}" class="text-href-link">1QH<sup>a</sup></a></li>
<li class="list-item dss-biblical"><a href="/transcriptions/5~6Hev1b/{VERSION}">5/6Hev1b</a></li>
<li class="list-item non-dss"><a href="/transcriptions/Ps/{VERSION}" class="text-href-link">Ps</a></li>
</ol>"""

TRANSCRIPTION = """<table id="c1" class="chapter-column"><tbody>
<tr id="c1-i1" class="line-verse"><td class="line-text"><span class="body-text">
<span id="11" class="word no-details" data-word-id="91">--</span><span class="word-space"> </span>
<span id="12" class="word" data-word-id="92">דרככה</span><span class="word-space"> </span>
</span></td></tr>
<tr class="parallel-line"><td><ul><li><span class="body-text">
<span id="par-13" class="word" data-word-id="93" data-parallel-id="12">דרככה</span>
</span></li></ul></td></tr>
<tr id="c1-i2" class="line-verse"><td class="line-text"><span class="body-text">
<span id="14" class="word" data-word-id="94">נפש</span>
</span></td></tr>
</tbody></table>"""

PATHS = ("1QS", "1QH^a^", "5~6Hev1b", "Ps")
SHELL = '<div id="transcription_id_7"><header>CC-BY-SA 4.0</header></div>'
SYNTAX = b'{"dependedOnBy": [], "dependentUpon": [{"syntacticCategory": "gen. Attribut", "wordReadingId": 14}]}'
QUIET = Policy(sleep=lambda _: None)


class FakeTransport:
    """Serves fixed responses by URL and records every request."""

    def __init__(self, pages: dict[str, bytes]) -> None:
        """Store the pages."""
        self.pages = pages
        self.requests: list[str] = []

    def __call__(self, url: str) -> bytes:
        """Return the page for a URL or raise a 404."""
        self.requests.append(url)
        if url not in self.pages:
            raise HttpStatusError(url, 404)
        return self.pages[url]


def site() -> dict[str, bytes]:
    """Return a fake site with three transcriptions whose detailed words have parsings."""
    pages = {
        f"{BASE_URL}/transcription-index": INDEX.encode(),
        f"{BASE_URL}/data-version-names": b'{"versionDates": ["2026-10-06", "2026-05-21"]}',
    }
    for path in PATHS:
        pages[transcription_url(path)] = TRANSCRIPTION.encode()
        pages[transcription_url(path, "/columns")] = b'{"columns": [{"id": "c1"}]}'
        pages[transcription_url(path, "/shell")] = SHELL.encode()
    for word in ("12", "14"):
        pages[f"{BASE_URL}/manuscript-word-reading-parsings/{word}"] = b'{"parsings": [{"lemma": "x"}]}'
        pages[f"{BASE_URL}/manuscript-word-reading-details/{word}"] = b'{"lemmas": [{"lemma": "x"}]}'
        pages[f"{BASE_URL}/manuscript/7/syntactic-data/{word}"] = SYNTAX
    return pages


def test_parse_index_reads_path_siglum_and_kind() -> None:
    """Each index link yields its URL path, its displayed siglum, and its corpus class."""
    assert parse_index(INDEX) == [
        Entry(path="1QS", siglum="1QS", kind="dss"),
        Entry(path="1QH^a^", siglum="1QHa", kind="dss"),
        Entry(path="5~6Hev1b", siglum="5/6Hev1b", kind="dss-biblical"),
        Entry(path="Ps", siglum="Ps", kind="non-dss"),
    ]


def test_parse_word_ids_keeps_main_text_words_with_details_only() -> None:
    """Words marked no-details and words in parallel lines are skipped."""
    assert parse_word_ids(TRANSCRIPTION) == ["12", "14"]


def test_transcription_url_keeps_tilde_and_quotes_other_characters() -> None:
    """The index's tilde separator stays literal while spaces are percent-encoded."""
    assert transcription_url("5~6Hev1b") == f"{BASE_URL}/transcriptions/5~6Hev1b"
    assert transcription_url("XHev Se", "/columns") == f"{BASE_URL}/transcriptions/XHev%20Se/columns"


def test_urllib_transport_refuses_non_https() -> None:
    """The real transport only opens HTTPS URLs."""
    with pytest.raises(ValueError, match="non-HTTPS"):
        urllib_transport("file:///etc/passwd")


def test_fetch_retries_transient_errors_then_succeeds() -> None:
    """A 503 is retried until a response arrives."""
    calls: list[str] = []

    def flaky(url: str) -> bytes:
        calls.append(url)
        if len(calls) < 3:
            raise HttpStatusError(url, 503)
        return b"ok"

    assert fetch("u", flaky, retries=3, sleep=lambda _: None) == b"ok"
    assert len(calls) == 3


def test_fetch_raises_after_the_last_retry() -> None:
    """A server that stays down exhausts the retries and raises FetchError."""
    def down(url: str) -> bytes:
        raise HttpStatusError(url, 503)

    with pytest.raises(FetchError, match="503"):
        fetch("u", down, retries=2, sleep=lambda _: None)


def test_fetch_retries_connection_errors() -> None:
    """A dropped connection counts as transient."""
    calls: list[str] = []

    def dropping(url: str) -> bytes:
        calls.append(url)
        if len(calls) == 1:
            message = "reset"
            raise ConnectionError(message)
        return b"ok"

    assert fetch("u", dropping, retries=2, sleep=lambda _: None) == b"ok"


def test_fetch_retries_a_truncated_response() -> None:
    """A body cut off mid-transfer counts as transient."""
    calls: list[str] = []

    def truncating(url: str) -> bytes:
        calls.append(url)
        if len(calls) == 1:
            partial = b"partial"
            raise IncompleteRead(partial, 10)
        return b"ok"

    assert fetch("u", truncating, retries=2, sleep=lambda _: None) == b"ok"


def test_an_unexpected_error_fails_one_manuscript_and_the_rest_complete(tmp_path: Path) -> None:
    """An exception that is not a FetchError is reported for its manuscript and does not stop the run."""
    pages = site()

    def broken(url: str) -> bytes:
        if url == f"{BASE_URL}/transcriptions/Ps/columns":
            message = "malformed"
            raise ValueError(message)
        return FakeTransport(pages)(url)

    report = Downloader(tmp_path, broken, policy=QUIET).run()
    assert sorted(report.done) == ["1QH^a^", "1QS", "5~6Hev1b"]
    assert report.failed == {"Ps": "ValueError: malformed"}


def test_fetch_does_not_retry_a_404() -> None:
    """A permanent error fails at once."""
    calls: list[str] = []

    def missing(url: str) -> bytes:
        calls.append(url)
        raise HttpStatusError(url, 404)

    with pytest.raises(FetchError, match="404"):
        fetch("u", missing, retries=5, sleep=lambda _: None)
    assert len(calls) == 1


def test_run_writes_every_manuscript_and_the_manifest(tmp_path: Path) -> None:
    """A full run stores each transcription's files, the index, and a manifest with the newest data version."""
    report = Downloader(tmp_path, FakeTransport(site()), policy=QUIET).run()
    assert sorted(report.done) == sorted(PATHS)
    assert report.failed == {}
    for path in PATHS:
        folder = tmp_path / "transcriptions" / path
        assert (folder / "transcription.html").read_text(encoding="utf-8") == TRANSCRIPTION
        assert json.loads((folder / "columns.json").read_text(encoding="utf-8")) == {"columns": [{"id": "c1"}]}
        assert (folder / "shell.html").read_text(encoding="utf-8") == SHELL
        assert not (folder / "parsings.json").exists()
    assert (tmp_path / "transcription-index.html").read_text(encoding="utf-8") == INDEX
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["data_version"] == "2026-10-06"
    assert manifest["entries"][2] == {"path": "5~6Hev1b", "siglum": "5/6Hev1b", "kind": "dss-biblical"}


def test_run_filters_by_kind_and_siglum(tmp_path: Path) -> None:
    """Only entries matching both filters are downloaded."""
    selection = Selection(kinds=frozenset({"dss-biblical", "non-dss"}), sigla=frozenset({"Ps"}))
    report = Downloader(tmp_path, FakeTransport(site()), selection=selection, policy=QUIET).run()
    assert report.done == ["Ps"]
    assert not (tmp_path / "transcriptions" / "1QS").exists()


def test_siglum_filter_accepts_the_displayed_siglum(tmp_path: Path) -> None:
    """A siglum with a slash selects the entry whose path uses a tilde."""
    selection = Selection(sigla=frozenset({"5/6Hev1b"}))
    assert Downloader(tmp_path, FakeTransport(site()), selection=selection, policy=QUIET).run().done == ["5~6Hev1b"]


def test_run_with_parsings_stores_parsings_and_lemmas_per_word(tmp_path: Path) -> None:
    """With parsings on, every detailed main-text word gets its parsings and lemmas."""
    selection = Selection(sigla=frozenset({"1QS"}), parsings=True)
    Downloader(tmp_path, FakeTransport(site()), selection=selection, policy=QUIET).run()
    stored = json.loads((tmp_path / "transcriptions" / "1QS" / "parsings.json").read_text(encoding="utf-8"))
    assert stored == {
        "12": {"parsings": [{"lemma": "x"}], "lemmas": [{"lemma": "x"}]},
        "14": {"parsings": [{"lemma": "x"}], "lemmas": [{"lemma": "x"}]},
    }


def test_manuscript_id_is_read_from_the_shell() -> None:
    """The shell's transcription id is the manuscript id the syntax endpoint expects."""
    assert manuscript_id(SHELL) == "7"


def test_a_shell_without_a_transcription_id_is_an_error() -> None:
    """A changed shell fails loudly instead of fetching syntax for the wrong manuscript."""
    with pytest.raises(ValueError, match="transcription_id"):
        manuscript_id("<div></div>")


def test_run_with_parsings_stores_the_syntax_of_every_parsed_word(tmp_path: Path) -> None:
    """Each parsed word gets its dependency links from the syntax endpoint of its manuscript."""
    selection = Selection(sigla=frozenset({"1QS"}), parsings=True)
    Downloader(tmp_path, FakeTransport(site()), selection=selection, policy=QUIET).run()
    stored = json.loads((tmp_path / "transcriptions" / "1QS" / "syntax.json").read_text(encoding="utf-8"))
    assert stored == {"12": json.loads(SYNTAX), "14": json.loads(SYNTAX)}
    assert not (tmp_path / "transcriptions" / "1QS" / "syntax.jsonl").exists()


def test_parsings_downloaded_before_syntax_existed_are_reused(tmp_path: Path) -> None:
    """A manuscript with parsings.json but no syntax.json gets only syntax requests."""
    folder = tmp_path / "transcriptions" / "1QS"
    selection = Selection(sigla=frozenset({"1QS"}), parsings=True)
    Downloader(tmp_path, FakeTransport(site()), selection=selection, policy=QUIET).run()
    (folder / "syntax.json").unlink()
    again = FakeTransport(site())
    Downloader(tmp_path, again, selection=selection, policy=QUIET).run()
    assert not any("manuscript-word-reading" in url for url in again.requests)
    assert sum("syntactic-data" in url for url in again.requests) == 2
    assert (folder / "syntax.json").exists()


def test_resume_after_interrupt_fetches_only_missing_syntax(tmp_path: Path) -> None:
    """Syntax fetched before an interrupt is kept and not requested again."""
    selection = Selection(sigla=frozenset({"1QS"}), parsings=True)
    first = InterruptingTransport(site(), "/syntactic-data/14")
    with pytest.raises(KeyboardInterrupt):
        Downloader(tmp_path, first, selection=selection, policy=QUIET).run()
    second = FakeTransport(site())
    Downloader(tmp_path, second, selection=selection, policy=QUIET).run()
    assert [url for url in second.requests if "syntactic-data" in url] == [f"{BASE_URL}/manuscript/7/syntactic-data/14"]
    assert not any("manuscript-word-reading" in url for url in second.requests)


def test_rerun_skips_completed_manuscripts(tmp_path: Path) -> None:
    """A second run requests no transcription that is already complete."""
    Downloader(tmp_path, FakeTransport(site()), policy=QUIET).run()
    second = FakeTransport(site())
    report = Downloader(tmp_path, second, policy=QUIET).run()
    assert sorted(report.done) == sorted(PATHS)
    assert all("/transcriptions/" not in url for url in second.requests)


def test_a_saved_transcription_of_the_current_version_is_not_downloaded_again(tmp_path: Path) -> None:
    """An unfinished manuscript reuses its saved transcription.html when the data version matches."""
    folder = tmp_path / "transcriptions" / "1QS"
    folder.mkdir(parents=True)
    (folder / "transcription.html").write_text('<time datetime="2026-10-06">' + TRANSCRIPTION, encoding="utf-8")
    transport = FakeTransport(site())
    selection = Selection(sigla=frozenset({"1QS"}), parsings=True)
    Downloader(tmp_path, transport, selection=selection, policy=QUIET).run()
    assert f"{BASE_URL}/transcriptions/1QS" not in transport.requests
    assert (folder / "parsings.json").exists()


def test_a_saved_transcription_of_an_older_version_is_downloaded_again(tmp_path: Path) -> None:
    """A saved transcription.html of an earlier data version is replaced."""
    folder = tmp_path / "transcriptions" / "1QS"
    folder.mkdir(parents=True)
    (folder / "transcription.html").write_text('<time datetime="2026-05-21">old', encoding="utf-8")
    transport = FakeTransport(site())
    Downloader(tmp_path, transport, selection=Selection(sigla=frozenset({"1QS"})), policy=QUIET).run()
    assert f"{BASE_URL}/transcriptions/1QS" in transport.requests
    assert (folder / "transcription.html").read_text(encoding="utf-8") == TRANSCRIPTION


def test_adding_parsings_later_refetches_only_what_is_missing(tmp_path: Path) -> None:
    """A manuscript downloaded without parsings counts as unfinished when parsings are requested."""
    Downloader(tmp_path, FakeTransport(site()), selection=Selection(sigla=frozenset({"1QS"})), policy=QUIET).run()
    selection = Selection(sigla=frozenset({"1QS"}), parsings=True)
    Downloader(tmp_path, FakeTransport(site()), selection=selection, policy=QUIET).run()
    assert (tmp_path / "transcriptions" / "1QS" / "parsings.json").exists()


def test_a_failing_manuscript_is_reported_and_leaves_no_partial_files(tmp_path: Path) -> None:
    """One failing transcription does not stop the others and writes nothing of its own."""
    pages = site()
    del pages[f"{BASE_URL}/transcriptions/Ps/shell"]
    report = Downloader(tmp_path, FakeTransport(pages), policy=QUIET).run()
    assert sorted(report.done) == ["1QH^a^", "1QS", "5~6Hev1b"]
    assert list(report.failed) == ["Ps"]
    assert not (tmp_path / "transcriptions" / "Ps").exists()
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert list(manifest["failed"]) == ["Ps"]


class InterruptingTransport(FakeTransport):
    """Raises KeyboardInterrupt on the first request whose URL contains a marker, as Ctrl-C would."""

    def __init__(self, pages: dict[str, bytes], marker: str) -> None:
        """Store the pages and the marker."""
        super().__init__(pages)
        self.marker = marker

    def __call__(self, url: str) -> bytes:
        """Interrupt on the marked URL, otherwise serve the page."""
        if self.marker in url:
            self.requests.append(url)
            raise KeyboardInterrupt
        return super().__call__(url)


def test_interrupt_cancels_manuscripts_not_yet_started(tmp_path: Path) -> None:
    """After an interrupt no further transcription is requested and the manifest records it."""
    transport = InterruptingTransport(site(), "/transcriptions/1QS")
    policy = Policy(workers=1, sleep=lambda _: None)
    with pytest.raises(KeyboardInterrupt):
        Downloader(tmp_path, transport, policy=policy).run()
    assert [url for url in transport.requests if "/transcriptions/" in url] == [f"{BASE_URL}/transcriptions/1QS"]
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["interrupted"] is True


def test_resume_after_interrupt_fetches_only_missing_parsings(tmp_path: Path) -> None:
    """Parsings fetched before an interrupt are kept and not requested again."""
    selection = Selection(sigla=frozenset({"1QS"}), parsings=True)
    first = InterruptingTransport(site(), "/manuscript-word-reading-parsings/14")
    with pytest.raises(KeyboardInterrupt):
        Downloader(tmp_path, first, selection=selection, policy=QUIET).run()
    second = FakeTransport(site())
    report = Downloader(tmp_path, second, selection=selection, policy=QUIET).run()
    assert report.done == ["1QS"]
    assert not any("manuscript-word-reading" in url and url.endswith("/12") for url in second.requests)
    stored = json.loads((tmp_path / "transcriptions" / "1QS" / "parsings.json").read_text(encoding="utf-8"))
    assert sorted(stored) == ["12", "14"]
    assert not (tmp_path / "transcriptions" / "1QS" / "parsings.jsonl").exists()


def test_progress_reports_every_stage_from_the_first_request(tmp_path: Path) -> None:
    """The log speaks before the first request and names each manuscript start, word count, and completion."""
    lines: list[str] = []
    selection = Selection(sigla=frozenset({"1QS", "Ps"}), parsings=True)
    Downloader(tmp_path, FakeTransport(site()), selection=selection, policy=QUIET, log=lines.append).run()
    assert lines[0] == "fetching the transcription index"
    assert "2 transcriptions to download, 0 already complete" in lines
    assert "start 1QS" in lines
    assert "1QS parsings: 2 words, 0 already fetched" in lines
    assert "1QS syntax: 2 words, 0 already fetched" in lines
    assert any(line.startswith("done 1QS (") for line in lines)
    assert lines[-1] == "finished: 2 complete, 0 failed"


def test_the_pause_runs_after_every_request(tmp_path: Path) -> None:
    """The policy's pause is applied once per request."""
    pauses: list[float] = []
    transport = FakeTransport(site())
    policy = Policy(workers=1, pause=0.5, sleep=pauses.append)
    Downloader(tmp_path, transport, selection=Selection(sigla=frozenset({"Ps"})), policy=policy).run()
    assert pauses == [0.5] * len(transport.requests)


def test_word_progress_is_reported_every_ten_words(tmp_path: Path) -> None:
    """A manuscript with eleven parsed words logs one progress line, at the tenth word."""
    words = "".join(f'<span id="{n}" class="word" data-word-id="{n}">x</span>' for n in range(1, 12))
    pages = site()
    pages[f"{BASE_URL}/transcriptions/1QS"] = f'<table><tr class="line-verse"><td>{words}</td></tr></table>'.encode()
    for n in range(1, 12):
        pages[f"{BASE_URL}/manuscript-word-reading-parsings/{n}"] = b'{"parsings": []}'
        pages[f"{BASE_URL}/manuscript-word-reading-details/{n}"] = b'{"lemmas": []}'
        pages[f"{BASE_URL}/manuscript/7/syntactic-data/{n}"] = SYNTAX
    lines: list[str] = []
    selection = Selection(sigla=frozenset({"1QS"}), parsings=True)
    Downloader(tmp_path, FakeTransport(pages), selection=selection, policy=QUIET, log=lines.append).run()
    assert [line for line in lines if "/11 words" in line] == ["1QS parsings: 10/11 words", "1QS syntax: 10/11 words"]
