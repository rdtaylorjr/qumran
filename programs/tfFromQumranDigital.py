"""Converts the Qumran-Digital download to Text-Fabric."""

from __future__ import annotations

import argparse
import html
import json
import re
from collections import Counter, defaultdict
from concurrent.futures import Executor, ProcessPoolExecutor
from html.parser import HTMLParser
from pathlib import Path
from shutil import rmtree
from typing import TYPE_CHECKING, Any, NamedTuple

import yaml
from tf.convert.walker import CV
from tf.fabric import Fabric

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

ORG = "rdtaylorjr"
REPO = "qumran"
VERSION = "0.1"

BASE = Path("~/github").expanduser()
REPO_DIR = BASE / ORG / REPO
SOURCE_DIR = REPO_DIR / "source" / VERSION
TF_DIR = REPO_DIR / "tf" / VERSION
MORPH = Path(__file__).resolve().parent.parent / "yaml" / "morph.yaml"
CHUNK = 4

INDEX = re.compile(r'<li class="list-item ([^"]+)">\s*<a href="/transcriptions/([^/"]+)/')
SHELL_ID = re.compile(r'id="transcription_id_(\d+)"')
LEVEL = re.compile(r"level-(\d+)")
NOT_YET = "(noch nicht bearbeitet)"
FLAGS = {"head_uncertain": "isUncertain", "head_generated": "isGenerated", "head_external": "isExternalToPhrase"}
VOID = frozenset({"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"})

slotType = "word"

generic = {
    "name": "Qumran",
    "source": "Qumran-Digital: Text und Lexikon, API version 1",
    "sourceUrl": "https://lexicon.qumran-digital.org/v1/qumran",
    "sourceFormat": "HTML and JSON",
    "compiler": "DFG-Projekt 465277421 Qumran-Digital: Text und Lexikon",
    "converters": "Rusty Taylor",
    "license": "Creative Commons Attribution-ShareAlike 4.0 International",
    "licenseUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
    "copynote1": "© 2022 DFG-Projekt 465277421 Qumran-Digital: Text und Lexikon",
    "copynote2": (
        "Bereitgestellt durch das DFG-Projekt Nr. 465277421 Qumran-Digital: Text und Lexikon"
        " auf der Grundlage eines Textes des früheren Projekts Qumran-Wörterbuch der"
        " Niedersächsischen Akademie der Wissenschaften zu Göttingen, der auf einem"
        " Vorläufertext von Martin Abegg basierte."
    ),
    "copynote3": (
        "Modified: converted from HTML and JSON to Text-Fabric, see docs/transcription.md."
        " Provided as is, without warranties, see the disclaimer in the license."
    ),
    "version": VERSION,
}

otext = {
    "sectionTypes": "text,column,line",
    "sectionFeatures": "text,column,line",
    "fmt:text-orig-full": "{prefix}{text}{trailer}",
}

intFeatures = {"alt", "id", "lex_id", "margin", "part", "priority", "word_id"}

featureMeta = {
    "alt": {"description": "level of the alternative reading the word belongs to"},
    "augment": {"description": "augment of the word part (source abbreviation)"},
    "column": {"description": "label of a column, fragment, or chapter"},
    "gloss@de": {
        "description": "German short definition of the lexeme",
        "language": "German",
        "languageCode": "de",
        "languageEnglish": "german",
    },
    "gn": {"description": "grammatical gender (m; f) or the source abbreviation"},
    "head": {"description": "from a word to the word it depends on, valued by the syntactic categories of the links"},
    "head_external": {"description": "as head, valued by the categories of the links marked external to the phrase"},
    "head_generated": {"description": "as head, valued by the categories of the links marked generated"},
    "head_uncertain": {"description": "as head, valued by the categories of the links marked uncertain"},
    "html": {"description": "markup of the word in the source, where it has any"},
    "id": {"description": "database id: transcription, column, line, or word reading"},
    "kind": {"description": "class of the transcription in the source index"},
    "lex": {"description": "lemma"},
    "lex_id": {"description": "database id of the lemma"},
    "line": {"description": "label of a line or verse"},
    "margin": {"description": "the line is a margin line, or the word is in a marginal reading"},
    "nametype": {"description": "named entity type (pers; gens; topo) or the source abbreviation"},
    "nu": {"description": "grammatical number (sg; pl; du)"},
    "parallel": {"description": "from a line or word to a parallel line or a parallel word aligned with it"},
    "part": {"description": "number of the part within the word, 0 being the first"},
    "prefix": {"description": "text of the line before its first word"},
    "priority": {"description": "rank of the analysis the part belongs to, 0 being the first"},
    "prs_gn": {"description": "pronominal suffix gender (m; f) or the source abbreviation"},
    "prs_nu": {"description": "pronominal suffix number (sg; pl; du)"},
    "prs_ps": {"description": "pronominal suffix person (p1; p2; p3)"},
    "ps": {"description": "grammatical person (p1; p2; p3)"},
    "root_designation": {"description": "number of the root of the lemma"},
    "sp": {"description": "part of speech (subs; verb; prep; ...) or the source abbreviation"},
    "st": {"description": "state of a noun (a; c) or the source abbreviation"},
    "text": {"description": "siglum of a transcription, or the text of a word"},
    "trailer": {"description": "text after a word up to the next word of its line"},
    "vs": {"description": "verbal stem (qal; nif; piel; ...) or the source abbreviation"},
    "vt": {"description": "verbal tense (perf; impf; wayq; impv; infc) or the source abbreviation"},
    "word_class": {"description": "word class of the lemma (source abbreviation)"},
    "word_id": {"description": "database id of the word; the readings of one word share it"},
}


class Word(NamedTuple):
    """One word reading of the main text with the text around it."""

    id: int
    word_id: int
    text: str
    html: str | None
    prefix: str
    trailer: str
    alt: int | None
    margin: bool


class Line(NamedTuple):
    """One line or margin line of a column."""

    id: int | None
    label: str
    margin: bool
    words: tuple[Word, ...]


class Column(NamedTuple):
    """One column, fragment, or chapter of a transcription."""

    id: int
    label: str
    lines: tuple[Line, ...]


class Parallel(NamedTuple):
    """One parallel line shown under a line, by the labels of its reference, with its words and their alignment.

    `lines` are the numbers of the first and last line it is shown under, counting margin lines,
    0 being the first line of the text: the lines since the previous parallel row.
    """

    lines: tuple[int, int]
    text: str
    column: str
    label: str
    words: tuple[tuple[int, tuple[int, ...]], ...]


class Text(NamedTuple):
    """One transcription with its parallels, parsings, and syntax."""

    path: str
    kind: str
    siglum: str
    id: int
    columns: tuple[Column, ...]
    parallels: tuple[Parallel, ...]
    parsings: dict[str, Any]
    syntax: dict[str, Any]


class _Transcription(HTMLParser):
    """Collects the columns, lines, words, and parallels of a transcription page."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.columns: list[Column] = []
        self.parallels: list[dict[str, Any]] = []
        self._stack: list[tuple[str, frozenset[str]]] = []
        self._column: dict[str, Any] | None = None
        self._line: dict[str, Any] | None = None
        self._label: list[str] | None = None
        self._row: str | None = None
        self._in_text = False
        self._word: dict[str, Any] | None = None
        self._pending: list[str] = []
        self._parallel: dict[str, Any] | None = None
        self._parallel_lines = (0, 0)
        self._lines = 0
        self._group = 0
        self._reference: tuple[str, int] | None = None
        self.ellipses = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        classes = frozenset((values.get("class") or "").split())
        if self._word is not None:
            self._word["html"].append(self.get_starttag_text() or "")
            self._word["tagged"] = True
        if tag not in VOID:
            self._stack.append((tag, classes))
        if self._word is not None:
            return
        if tag == "table" and "chapter-column" in classes:
            self._column = {"id": int((values.get("id") or "c0")[1:]), "label": "", "lines": []}
        elif tag == "th" and "chapter-column-label" in classes:
            self._label = []
        elif tag == "tr":
            self._start_row(values, classes)
        elif tag == "td" and self._row == "line":
            if classes & {"line-verse-label", "margin-label"}:
                self._label = []
            elif classes & {"line-text", "margin-text-line"}:
                self._in_text = True
        elif self._row == "parallel":
            self._start_parallel(tag, values, classes)
        elif self._in_text and tag == "span" and "word" in classes:
            self._start_word(values)

    def _start_row(self, values: dict[str, str | None], classes: frozenset[str]) -> None:
        self._row = None
        if "line-verse" in classes:
            number = (values.get("id") or "").partition("-i")[2]
            self._line = {"id": int(number) if number else None, "margin": False, "words": []}
            self._row = "line"
        elif "margin" in classes:
            self._line = {"id": None, "margin": True, "words": []}
            self._row = "line"
        elif "parallel-line" in classes:
            self._row = "parallel"
            self._parallel_lines = (min(self._group, self._lines - 1), self._lines - 1)

    def _start_parallel(self, tag: str, values: dict[str, str | None], classes: frozenset[str]) -> None:
        if tag == "li":
            self._parallel = None
        elif tag == "a" and (values.get("href") or "").startswith("/transcriptions/"):
            self._parallel = {
                "lines": self._parallel_lines,
                "text": (values.get("href") or "").split("/")[2],
                "column": "",
                "label": "",
                "words": [],
            }
            self.parallels.append(self._parallel)
        elif tag == "span" and self._parallel is not None and classes & {"chapter-column-label", "line-verse-label"}:
            field = "column" if "chapter-column-label" in classes else "label"
            self._reference = (field, len(self._stack))
        elif tag == "span" and "word" in classes:
            if values.get("data-word-id") == "0":
                self.ellipses += 1
                return
            if self._parallel is None:
                raise ValueError(f"a parallel word without a reference under line {self._parallel_lines}")
            other = int((values.get("id") or "").removeprefix("par-"))
            here = values.get("data-parallel-id")
            self._parallel["words"].append((other, tuple(int(number) for number in here.split(",")) if here else ()))

    def _start_word(self, values: dict[str, str | None]) -> None:
        words = self._line["words"] if self._line is not None else []
        if words:
            words[-1]["trailer"] = "".join(self._pending)
            prefix = ""
        else:
            prefix = "".join(self._pending)
        self._pending = []
        levels = [int(m.group(1)) for _, classes in self._stack for c in classes if (m := LEVEL.fullmatch(c))]
        self._word = {
            "id": int(values.get("id") or 0),
            "word_id": int(values.get("data-word-id") or 0),
            "text": [],
            "html": [],
            "tagged": False,
            "prefix": prefix,
            "trailer": "",
            "alt": max(levels) if levels else None,
            "margin": any("margin-text" in classes for _, classes in self._stack),
            "depth": len(self._stack),
        }

    def handle_endtag(self, tag: str) -> None:
        for index in range(len(self._stack) - 1, -1, -1):
            if self._stack[index][0] == tag:
                classes = self._stack[index][1]
                del self._stack[index:]
                break
        else:
            return
        if self._reference is not None and len(self._stack) < self._reference[1]:
            self._reference = None
        if self._word is not None:
            if len(self._stack) >= self._word["depth"]:
                self._word["html"].append(f"</{tag}>")
                return
            self._end_word()
            return
        if self._label is not None and (tag == "th" or tag == "td"):
            label = "".join(self._label)
            if tag == "th" and self._column is not None:
                self._column["label"] = label
            elif self._line is not None:
                self._line["label"] = label
            self._label = None
        elif tag == "td" and self._in_text:
            self._end_text()
        elif tag == "tr" and self._row == "line":
            self._end_line()
        elif tag == "tr":
            if self._row == "parallel":
                self._group = self._lines
            self._row = None
            self._parallel = None
        elif tag == "table" and "chapter-column" in classes and self._column is not None:
            self.columns.append(Column(self._column["id"], self._column["label"], tuple(self._column["lines"])))
            self._column = None

    def _end_word(self) -> None:
        word = self._word
        self._word = None
        if self._line is not None and word is not None:
            word["text"] = "".join(word["text"])
            word["html"] = "".join(word["html"]) if word["tagged"] else None
            self._line["words"].append(word)

    def _end_text(self) -> None:
        if self._line is not None and self._line["words"]:
            self._line["words"][-1]["trailer"] = "".join(self._pending)
        elif self._line is not None:
            self._line["prefix"] = "".join(self._pending)
        self._pending = []
        self._in_text = False

    def _end_line(self) -> None:
        line = self._line
        self._line = None
        self._row = None
        if line is None or self._column is None:
            return
        self._lines += 1
        words = tuple(
            Word(w["id"], w["word_id"], w["text"], w["html"], w["prefix"], w["trailer"], w["alt"], w["margin"])
            for w in line["words"]
        )
        if not words and line.get("prefix"):
            raise ValueError(f"line {line['id']} has text but no words: {line['prefix']!r}")
        self._column["lines"].append(Line(line["id"], line.get("label", ""), line["margin"], words))

    def handle_data(self, data: str) -> None:
        if self._word is not None:
            self._word["text"].append(data)
            self._word["html"].append(html.escape(data, quote=False))
        elif self._label is not None:
            self._label.append(data)
        elif self._reference is not None and self._parallel is not None:
            self._parallel[self._reference[0]] += data
        elif self._in_text:
            self._pending.append(data)


def transcription(page: str) -> tuple[tuple[Column, ...], tuple[Parallel, ...]]:
    """Reads the columns and parallels of a transcription page."""
    parser = _Transcription()
    parser.feed(page)
    parser.close()
    parallels = tuple(
        Parallel(p["lines"], p["text"], p["column"], p["label"], tuple(p["words"])) for p in parser.parallels
    )
    return tuple(parser.columns), parallels


def index_entries(page: str) -> list[tuple[str, str]]:
    """Lists the path and class of every transcription of the index page, in index order."""
    return [(path, kind) for kind, path in INDEX.findall(page)]


def read_text(folder: Path, kind: str) -> Text:
    """Reads the files of one transcription folder."""
    columns, parallels = transcription((folder / "transcription.html").read_text(encoding="utf-8"))
    shell = (folder / "shell.html").read_text(encoding="utf-8")
    found = SHELL_ID.search(shell)
    if found is None:
        raise ValueError(f"{folder.name}: the shell has no transcription id")
    return Text(
        folder.name,
        kind,
        json.loads((folder / "columns.json").read_text(encoding="utf-8"))["sigla"],
        int(found.group(1)),
        columns,
        parallels,
        _json(folder / "parsings.json"),
        _json(folder / "syntax.json"),
    )


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def texts(source: Path, executor: Executor) -> list[Text]:
    """Reads every transcription of the index across workers, in index order."""
    entries = index_entries((source / "transcription-index.html").read_text(encoding="utf-8"))
    folders = [source / "transcriptions" / path for path, _ in entries]
    kinds = [kind for _, kind in entries]
    return list(executor.map(read_text, folders, kinds, chunksize=CHUNK))


def load_morph(path: Path = MORPH) -> dict[str, Any]:
    """Reads the declared mapping of source morphology to BHSA features."""
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def morphology(parsing: dict[str, Any], morph: dict[str, Any]) -> dict[str, str]:
    """Gives the BHSA features of one parsing, by the declared mapping."""
    result = {}
    for feature, spec in morph.items():
        label = parsing.get(spec["field"])
        if label is None:
            continue
        if label in spec["bhsa"]:
            result[feature] = spec["bhsa"][label]
        elif label in (spec.get("kept") or {}):
            result[feature] = parsing.get(spec["field"] + "Abbr") or label
        elif spec.get("other") != "absent":
            raise KeyError(f"{spec['field']} {label!r} is not declared in yaml/morph.yaml")
    return result


class Places:
    """Finds the word slots of a text by reading id, by line, and by column and line label."""

    def __init__(self) -> None:
        self.lines: list[Any] = []
        self.labelled: dict[tuple[str, str], list[Any]] = defaultdict(list)
        self.anywhere: dict[int, list[Any]] = defaultdict(list)
        self.in_line: dict[tuple[Any, int], list[Any]] = defaultdict(list)
        self.at: dict[tuple[str, str, int], list[Any]] = defaultdict(list)
        self.in_column: dict[tuple[str, int], list[Any]] = defaultdict(list)

    def add_line(self, column: Column, line: Line, node: Any) -> None:
        self.lines.append(node)
        self.labelled[(column.label, line.label)].append(node)

    def add(self, column: Column, line: Line, node: Any, word: Word, slot: Any) -> None:
        self.anywhere[word.id].append(slot)
        self.in_line[(node, word.id)].append(slot)
        self.at[(column.label, line.label, word.id)].append(slot)
        self.in_column[(column.label, word.id)].append(slot)

    def find(self, column: str, line: str, word: int) -> list[Any]:
        """Gives the slots of a word at a column and line, or in the column if the line does not hold it."""
        return self.at.get((column, line, word)) or self.in_column.get((column, word), [])


def director(cv: Any, found: Iterable[Text], morph: dict[str, Any], report: Counter[str] | None = None) -> None:
    """Emits the texts, columns, lines, words, parts, and lexemes, then the parallel and syntax edges."""
    report = Counter() if report is None else report
    places: dict[str, Places] = {}
    lemmas: dict[int, dict[str, Any]] = {}
    occurrences: dict[int, set[int]] = defaultdict(set)
    found = list(found)
    for text in found:
        node = cv.node("text")
        cv.feature(node, text=text.siglum, kind=text.kind, id=text.id)
        places[text.path] = _text(cv, text, morph, lemmas, occurrences)
        cv.terminate(node)
    for number in sorted(occurrences):
        lemma = lemmas[number]
        node = cv.node("lex", slots=sorted(occurrences[number]))
        definition = lemma.get("shortDefinition")
        cv.feature(
            node,
            **{
                "lex": lemma["lemma"],
                "lex_id": number,
                "root_designation": lemma.get("rootDesignation"),
                "gloss@de": None if definition in (None, NOT_YET) else definition,
                "word_class": lemma.get("wordClassAbbreviation") or None,
            },
        )
    for text in found:
        _parallels(cv, text, places, report)
        _syntax(cv, text, places[text.path], report)
    for name in featureMeta:
        if not cv.occurs(name):
            cv.meta(name)


def _text(
    cv: Any, text: Text, morph: dict[str, Any], lemmas: dict[int, dict[str, Any]], occurrences: dict[int, set[int]]
) -> Places:
    """Emits the columns, lines, words, and parts of one text."""
    places = Places()
    for column in text.columns:
        column_node = cv.node("column")
        cv.feature(column_node, column=column.label, id=column.id)
        for line in column.lines:
            line_node = cv.node("line")
            cv.feature(line_node, line=line.label, id=line.id, margin=1 if line.margin else None)
            places.add_line(column, line, line_node)
            if not line.words:
                cv.slot()
            for word in line.words:
                entry = text.parsings.get(str(word.id)) or {"parsings": [], "lemmas": []}
                parts = [cv.node("part") for _ in entry["parsings"]]
                slot = cv.slot()
                cv.feature(
                    slot,
                    text=word.text or None,
                    html=word.html,
                    prefix=word.prefix or None,
                    trailer=word.trailer or None,
                    id=word.id,
                    word_id=word.word_id,
                    alt=word.alt,
                    margin=1 if word.margin else None,
                )
                for part, parsing in zip(parts, entry["parsings"]):
                    cv.feature(
                        part,
                        lex=parsing["lemma"],
                        lex_id=parsing["lemmaId"],
                        part=parsing["wordPart"],
                        priority=parsing["parsingPriority"],
                        **morphology(parsing, morph),
                    )
                    cv.terminate(part)
                for lemma in entry["lemmas"]:
                    lemmas.setdefault(lemma["lemmaId"], lemma)
                    occurrences[lemma["lemmaId"]].add(slot[1])
                places.add(column, line, line_node, word, slot)
            cv.terminate(line_node)
        cv.terminate(column_node)
    return places


def _parallels(cv: Any, text: Text, places: dict[str, Places], report: Counter[str]) -> None:
    """Links every line and word to the parallel line and word shown under it.

    A parallel row stands under the lines since the previous parallel row.
    The words are looked up in those lines, and the lines that hold an aligned word are linked,
    or the line right above the parallel row where none does.
    """
    here = places[text.path]
    for parallel in text.parallels:
        there = places.get(parallel.text)
        first, last = parallel.lines
        group = here.lines[first : last + 1]
        others = there.labelled.get((parallel.column, parallel.label), []) if there is not None else []
        linked = []
        for word_there, words_here in parallel.words:
            if not words_here:
                report["parallel words without alignment"] += 1
                continue
            sources = []
            for line in group:
                found = [slot for word in words_here for slot in here.in_line.get((line, word), [])]
                if found and line not in linked:
                    linked.append(line)
                sources.extend(found)
            targets = [slot for other in others for slot in there.in_line.get((other, word_there), [])]
            if not targets and there is not None:
                targets = there.find(parallel.column, parallel.label, word_there)
            if not sources or not targets:
                report["parallel words not found"] += 1
            for source in sources:
                for target in targets:
                    cv.edge(source, target, parallel=None)
                    report["parallel words"] += 1
        if not others:
            report["parallel lines not found"] += 1
        for line in linked or group[-1:]:
            for other in others:
                cv.edge(line, other, parallel=None)
                report["parallel lines"] += 1


def _syntax(cv: Any, text: Text, places: Places, report: Counter[str]) -> None:
    """Links every word to the words it depends on, valued by the syntactic categories of the links.

    Two words can be linked more than once, so each edge carries the categories of all links between them,
    in source order, and each flag edge the categories of the links that have the flag.
    """
    links: dict[tuple[Any, Any], dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    for reading, entry in text.syntax.items():
        heads = places.anywhere.get(int(reading), [])
        for link in entry["dependentUpon"]:
            dependents = places.find(link["location1"], link["location2"], link["wordReadingId"])
            if not heads or not dependents:
                report["dependencies not found"] += 1
            for head in heads:
                for dependent in dependents:
                    found = links[(dependent, head)]
                    found["head"].append(link["syntacticCategory"])
                    for feature, flag in FLAGS.items():
                        if link[flag]:
                            found[feature].append(link["syntacticCategory"])
                    report["dependencies"] += 1
    for (dependent, head), found in links.items():
        cv.edge(dependent, head, **{feature: ", ".join(categories) for feature, categories in found.items()})


def convert(
    source: Path = SOURCE_DIR,
    target: Path = TF_DIR,
    executor: Callable[[], Executor] = ProcessPoolExecutor,
    morph: Path = MORPH,
    report: Counter[str] | None = None,
) -> bool:
    """Writes the Text-Fabric dataset of the source folder to the target folder."""
    with executor() as pool:
        found = texts(source, pool)
    mapping = load_morph(morph)
    if target.exists():
        rmtree(target)
    cv = CV(Fabric(locations=str(target), silent="deep"), silent="deep")
    return bool(
        cv.walk(
            lambda walker: director(walker, found, mapping, report),
            slotType,
            otext=otext,
            generic=generic,
            intFeatures=intFeatures,
            featureMeta=featureMeta,
        )
    )


def main(argv: list[str] | None = None, executor: Callable[[], Executor] = ProcessPoolExecutor) -> int:
    """Converts the source given on the command line, or the source of this version."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=SOURCE_DIR)
    parser.add_argument("--target", type=Path, default=TF_DIR)
    args = parser.parse_args(argv)
    report: Counter[str] = Counter()
    good = convert(args.source, args.target, executor, report=report)
    for name, count in sorted(report.items()):
        print(f"{count:>8} {name}")
    return 0 if good else 1


if __name__ == "__main__":
    raise SystemExit(main())
