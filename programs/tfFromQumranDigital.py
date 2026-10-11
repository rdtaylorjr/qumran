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
from xml.etree.ElementTree import Element, TreeBuilder, tostring

import yaml
from tf.convert.walker import CV
from tf.fabric import Fabric

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Iterator

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
    "gn": {"description": "grammatical gender (m; f; NA) or the source abbreviation"},
    "head": {"description": "from a word to the word it depends on, valued by the syntactic categories of the links"},
    "head_external": {"description": "as head, valued by the categories of the links marked external to the phrase"},
    "head_generated": {"description": "as head, valued by the categories of the links marked generated"},
    "head_uncertain": {"description": "as head, valued by the categories of the links marked uncertain"},
    "html": {"description": "markup of the word in the source, where it has any"},
    "id": {"description": "database id: transcription, column, line, or word reading"},
    "kind": {"description": "class of the transcription in the source index"},
    "lex": {"description": "lemma, with its root designation where it has one, such as יחד_II"},
    "lex_id": {"description": "database id of the lemma"},
    "line": {"description": "label of a line or verse"},
    "margin": {"description": "the line is a margin line, or the word is in a marginal reading"},
    "nametype": {"description": "named entity type (pers; gens; topo) or the source abbreviation"},
    "nu": {"description": "grammatical number (sg; pl; du; NA)"},
    "parallel": {"description": "from a line or word to a parallel line or a parallel word aligned with it"},
    "part": {"description": "number of the part within the word, 0 being the first"},
    "prefix": {"description": "text of the line before its first word"},
    "priority": {"description": "rank of the analysis the part belongs to, 0 being the first"},
    "prs_gn": {"description": "pronominal suffix gender (m; f; NA) or the source abbreviation"},
    "prs_nu": {"description": "pronominal suffix number (sg; pl; du; NA)"},
    "prs_ps": {"description": "pronominal suffix person (p1; p2; p3; NA)"},
    "ps": {"description": "grammatical person (p1; p2; p3; NA)"},
    "root_designation": {"description": "number of the root of the lemma"},
    "sp": {"description": "part of speech (subs; verb; prep; ...) or the source abbreviation"},
    "st": {"description": "state of a noun (a; c; NA) or the source abbreviation"},
    "text": {"description": "siglum of a transcription, or the text of a word"},
    "trailer": {"description": "text after a word up to the next word of its line"},
    "vs": {"description": "verbal stem (qal; nif; piel; ...; NA) or the source abbreviation"},
    "vt": {"description": "verbal tense (perf; impf; wayq; impv; infc; NA) or the source abbreviation"},
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
    """One parallel line, by the text and labels of its reference, with its words and the words they align with.

    `lines` are the numbers of the first and last line of the text it stands under, 0 being the first.
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


class _Tree(HTMLParser):
    """Builds the element tree of a page, closing void elements and ignoring end tags of elements that are not open."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.builder = TreeBuilder()
        self.builder.start("page", {})
        self.open: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.builder.start(tag, {name: value or "" for name, value in attrs})
        if tag in VOID:
            self.builder.end(tag)
        else:
            self.open.append(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag in self.open:
            while (name := self.open.pop()) != tag:
                self.builder.end(name)
            self.builder.end(tag)

    def handle_data(self, data: str) -> None:
        self.builder.data(data)

    def page(self) -> Element:
        while self.open:
            self.builder.end(self.open.pop())
        self.builder.end("page")
        return self.builder.close()


def tree(page: str) -> Element:
    """Parses a page into an element tree."""
    parser = _Tree()
    parser.feed(page)
    parser.close()
    return parser.page()


def has(element: Element, name: str) -> bool:
    """Tells whether an element has a class."""
    return name in element.get("class", "").split()


def first(element: Element, name: str) -> Element:
    """Gives the first descendant of an element with a class."""
    return next(found for found in element.iter() if has(found, name))


def content(element: Element) -> str:
    """Gives the text of an element and its descendants."""
    return "".join(element.itertext())


def markup(element: Element) -> str | None:
    """Gives the markup inside an element, if it has child elements."""
    if not len(element):
        return None
    inner = (tostring(child, encoding="unicode", method="html") for child in element)
    return html.escape(element.text or "", quote=False) + "".join(inner)


def pieces(element: Element, alt: int | None = None, margin: bool = False) -> Iterator[tuple[Element | str, int | None, bool]]:
    """Yields the words and the text between them in page order, with the alternative level and margin of each word."""
    if element.text:
        yield element.text, alt, margin
    for child in element:
        if has(child, "word"):
            yield child, alt, margin
        else:
            levels = [int(found.group(1)) for name in child.get("class", "").split() if (found := LEVEL.fullmatch(name))]
            yield from pieces(child, max(levels) if levels else alt, margin or has(child, "margin-text"))
        if child.tail:
            yield child.tail, alt, margin


def read_line(row: Element) -> Line:
    """Reads a line or margin line with its words, giving the text between words to the word before it."""
    margin = has(row, "margin")
    cell = first(row, "margin-text-line" if margin else "line-text")
    words: list[Word] = []
    pending: list[str] = []
    for piece, alt, in_margin in pieces(cell):
        if isinstance(piece, str):
            pending.append(piece)
            continue
        if words:
            words[-1] = words[-1]._replace(trailer="".join(pending))
        prefix = "" if words else "".join(pending)
        pending = []
        number, word = int(piece.get("id")), int(piece.get("data-word-id"))
        words.append(Word(number, word, content(piece), markup(piece), prefix, "", alt, in_margin))
    if words:
        words[-1] = words[-1]._replace(trailer="".join(pending))
    elif "".join(pending):
        raise ValueError(f"line {row.get('id')} has text but no words")
    number = int(row.get("id").partition("-i")[2]) if "id" in row.attrib else None
    label = content(first(row, "margin-label" if margin else "line-verse-label"))
    return Line(number, label, margin, tuple(words))


def read_parallels(row: Element, lines: tuple[int, int]) -> Iterator[Parallel]:
    """Reads the parallel lines of a parallel row, each after its reference, with their aligned words.

    The ellipses that stand for omitted text are not words.
    """
    for item in row.iter("li"):
        found: list[tuple[str, str, str, list[tuple[int, tuple[int, ...]]]]] = []
        for element in item.iter():
            if has(element, "reference-label"):
                link = element.find("a")
                path = link.get("href").split("/")[2]
                found.append((path, content(first(link, "chapter-column-label")), content(first(link, "line-verse-label")), []))
            elif has(element, "word") and element.get("data-word-id") != "0":
                if not found:
                    raise ValueError(f"a parallel word without a reference under lines {lines}")
                aligned = element.get("data-parallel-id")
                here = tuple(int(number) for number in aligned.split(",")) if aligned else ()
                found[-1][3].append((int(element.get("id").removeprefix("par-")), here))
        for path, column, label, words in found:
            yield Parallel(lines, path, column, label, tuple(words))


def transcription(page: str) -> tuple[tuple[Column, ...], tuple[Parallel, ...]]:
    """Reads the columns and parallels of a transcription page.

    A parallel row stands under the lines since the previous parallel row, counting margin lines.
    """
    columns: list[Column] = []
    found: list[Parallel] = []
    count = 0
    group = 0
    for table in tree(page).iter("table"):
        if not has(table, "chapter-column"):
            continue
        lines: list[Line] = []
        for row in table.iter("tr"):
            if has(row, "line-verse") or has(row, "margin"):
                lines.append(read_line(row))
                count += 1
            elif has(row, "parallel-line"):
                found.extend(read_parallels(row, (min(group, count - 1), count - 1)))
                group = count
        columns.append(Column(int(table.get("id")[1:]), content(first(table, "chapter-column-label")), tuple(lines)))
    return tuple(columns), tuple(found)


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
        json.loads((folder / "parsings.json").read_text(encoding="utf-8")),
        json.loads((folder / "syntax.json").read_text(encoding="utf-8")),
    )


def texts(source: Path, executor: Executor) -> list[Text]:
    """Reads every transcription of the index across workers, in index order."""
    entries = index_entries((source / "transcription-index.html").read_text(encoding="utf-8"))
    folders = [source / "transcriptions" / path for path, _ in entries]
    kinds = [kind for _, kind in entries]
    return list(executor.map(read_text, folders, kinds, chunksize=CHUNK))


def lexeme(lemma: dict[str, Any]) -> str:
    """Gives the lemma with its root designation, which tells homonyms apart, such as יחד_II."""
    designation = lemma.get("rootDesignation")
    return f"{lemma['lemma']}_{designation}" if designation else lemma["lemma"]


def load_morph(path: Path = MORPH) -> dict[str, Any]:
    """Reads the declared mapping of source morphology to BHSA features."""
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def morphology(parsing: dict[str, Any], morph: dict[str, Any]) -> dict[str, str]:
    """Gives the BHSA features of one parsing, by the declared mapping."""
    result = {}
    for feature, spec in morph.items():
        label = parsing.get(spec["field"])
        if label is None:
            if "missing" in spec:
                result[feature] = spec["missing"]
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
        self.in_column: dict[tuple[str, int], list[Any]] = defaultdict(list)

    def add_line(self, column: Column, line: Line, node: Any) -> None:
        self.lines.append(node)
        self.labelled[(column.label, line.label)].append(node)

    def add(self, column: Column, line: Line, node: Any, word: Word, slot: Any) -> None:
        self.anywhere[word.id].append(slot)
        self.in_line[(node, word.id)].append(slot)
        self.in_column[(column.label, word.id)].append(slot)

    def find(self, column: str, line: str, word: int) -> list[Any]:
        """Gives the slots of a word at a column and line, or its one slot in the column if the line does not hold it."""
        found = [slot for node in self.labelled.get((column, line), []) for slot in self.in_line.get((node, word), [])]
        elsewhere = self.in_column.get((column, word), [])
        return found or (elsewhere if len(elsewhere) == 1 else [])


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
                "lex": lexeme(lemma),
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
                        lex=lexeme(parsing),
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
    The lines that hold an aligned word are linked, or the line right above the parallel row where none does.
    """
    here = places[text.path]
    for parallel in text.parallels:
        there = places[parallel.text]
        first, last = parallel.lines
        group = here.lines[first : last + 1]
        others = there.labelled.get((parallel.column, parallel.label), [])
        linked = _parallel_words(cv, parallel, group, here, there, report)
        if not others:
            report["parallel lines not found"] += 1
        for line in linked or group[-1:]:
            for other in others:
                cv.edge(line, other, parallel=None)
                report["parallel lines"] += 1


def _parallel_words(
    cv: Any, parallel: Parallel, group: list[Any], here: Places, there: Places, report: Counter[str]
) -> list[Any]:
    """Links the aligned words of a parallel line, and gives the lines of the group that hold an aligned word."""
    linked: list[Any] = []
    for word_there, words_here in parallel.words:
        if not words_here:
            report["parallel words without alignment"] += 1
            continue
        found = {line: [slot for word in words_here for slot in here.in_line.get((line, word), [])] for line in group}
        linked += [line for line, slots in found.items() if slots and line not in linked]
        sources = [slot for slots in found.values() for slot in slots]
        targets = there.find(parallel.column, parallel.label, word_there)
        if not sources or not targets:
            report["parallel words not found"] += 1
        for source in sources:
            for target in targets:
                cv.edge(source, target, parallel=None)
                report["parallel words"] += 1
    return linked


def _syntax(cv: Any, text: Text, places: Places, report: Counter[str]) -> None:
    """Links every word to the words it depends on, valued by the syntactic categories of the links.

    Two words can be linked more than once, so each edge carries the categories of all links between them,
    in source order and separated by commas, and each flag edge the categories of the links that have the flag.
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
        cv.edge(dependent, head, **{feature: ",".join(categories) for feature, categories in found.items()})


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
