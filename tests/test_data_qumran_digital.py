import os
import re
import json
import functools
import collections
from html.parser import HTMLParser
from concurrent.futures import ProcessPoolExecutor

from tf.fabric import Fabric

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TF_FOLDER = 'tf'
SOURCE_FOLDER = 'source'
latest_data_folder = sorted(os.listdir(os.path.join(ROOT_DIR, TF_FOLDER)))[-1]
SOURCE_DIR = os.path.join(ROOT_DIR, SOURCE_FOLDER, latest_data_folder)

PATH = re.compile(r'<li class="list-item [^"]+">\s*<a href="/transcriptions/([^/"]+)/')
VOID = {'br', 'hr', 'img', 'input', 'meta', 'link', 'wbr'}


class Page(HTMLParser):
    """Collects the words and the line texts of the main text, and the aligned pairs of the parallels."""

    def __init__(self):
        super().__init__()
        self.words, self.lines, self.pairs = [], [], set()
        self.depth = 0
        self.parallel = False
        self.text = None
        self.word = None

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        classes = (values.get('class') or '').split()
        if tag not in VOID:
            self.depth += 1
        if tag == 'tr':
            self.parallel = 'parallel-line' in classes
        if self.parallel and 'word' in classes and values.get('data-parallel-id'):
            for here in values['data-parallel-id'].split(','):
                self.pairs.add((int(here), int(values['id'][4:])))
        if self.parallel:
            return
        if tag == 'td' and ('line-text' in classes or 'margin-text-line' in classes):
            self.text = ['', self.depth]
        elif tag == 'span' and 'word' in classes and self.text is not None and self.word is None:
            self.word = [int(values['id']), int(values['data-word-id']), '', self.depth]

    def handle_endtag(self, tag):
        self.depth -= 1
        if self.word is not None and self.depth < self.word[3]:
            self.words.append(tuple(self.word[:3]))
            self.word = None
        if self.text is not None and self.depth < self.text[1]:
            self.lines.append(self.text[0])
            self.text = None

    def handle_data(self, data):
        if self.word is not None:
            self.word[2] += data
        if self.text is not None:
            self.text[0] += data


def read(path):
    folder = os.path.join(SOURCE_DIR, 'transcriptions', path)
    page = Page()
    with open(os.path.join(folder, 'transcription.html'), encoding='utf-8') as f:
        page.feed(f.read())
    found = {}
    for name in ('columns', 'parsings', 'syntax'):
        file = os.path.join(folder, f'{name}.json')
        if os.path.exists(file):
            with open(file, encoding='utf-8') as f:
                found[name] = json.load(f)
    return path, page.words, page.lines, page.pairs, found


@functools.cache
def source():
    with open(os.path.join(SOURCE_DIR, 'transcription-index.html'), encoding='utf-8') as f:
        paths = PATH.findall(f.read())
    with ProcessPoolExecutor() as pool:
        return {path: rest for path, *rest in pool.map(read, paths, chunksize=4)}


@functools.cache
def tf():
    TF = Fabric(locations=os.path.join(ROOT_DIR, TF_FOLDER, latest_data_folder), silent='deep')
    api = TF.load('''
        otype text kind id word_id column line margin prefix trailer
        lex_id part priority head parallel
    ''', silent='deep')
    texts = {api.F.text.v(t): t for t in api.F.otype.s('text')}
    sigla = {path: data[3]['columns']['sigla'] for path, data in source().items()}
    return api, {path: texts[siglum] for path, siglum in sigla.items()}


def test_every_transcription_is_a_text_with_the_columns_of_the_source():
    (api, nodes), SOURCE = tf(), source()
    F, L = api.F, api.L
    assert len(F.otype.s('text')) == len(SOURCE)
    for path, (_, _, _, found) in SOURCE.items():
        columns = [(f'c{F.id.v(c)}', F.column.v(c)) for c in L.d(nodes[path], 'column')]
        assert columns == [(c['id'], c['name']) for c in found['columns']['columns']], path


def test_every_word_of_the_main_text_is_a_slot_with_the_same_ids_and_text():
    (api, nodes), SOURCE = tf(), source()
    F, L = api.F, api.L
    for path, (words, _, _, _) in SOURCE.items():
        found = [(F.id.v(w), F.word_id.v(w), F.text.v(w) or '') for w in L.d(nodes[path], 'word') if F.id.v(w)]
        assert found == words, path


def test_the_text_of_every_line_is_the_text_of_the_source_line():
    (api, nodes), SOURCE = tf(), source()
    L, T = api.L, api.T
    for path, (_, lines, _, _) in SOURCE.items():
        assert [T.text(n) for n in L.d(nodes[path], 'line')] == lines, path


def test_every_parsing_is_a_part_of_its_word():
    (api, nodes), SOURCE = tf(), source()
    F, L = api.F, api.L
    for path, (_, _, _, found) in SOURCE.items():
        parsings = found.get('parsings', {})
        for w in L.d(nodes[path], 'word'):
            entry = parsings.get(str(F.id.v(w)), {'parsings': []})
            expected = sorted((p['lemmaId'], p['wordPart'], p['parsingPriority']) for p in entry['parsings'])
            parts = sorted((F.lex_id.v(p), F.part.v(p), F.priority.v(p)) for p in L.u(w, 'part'))
            assert parts == expected, (path, F.id.v(w))


def test_every_dependency_edge_carries_the_links_of_the_source():
    (api, nodes), SOURCE = tf(), source()
    F, L, E = api.F, api.L, api.E
    links = collections.defaultdict(list)
    missing = 0
    for path, (words, _, _, found) in SOURCE.items():
        present = {word[0] for word in words}
        for reading, entry in found.get('syntax', {}).items():
            for link in entry['dependentUpon']:
                links[(path, link['wordReadingId'], int(reading))].append(link['syntacticCategory'])
                missing += link['wordReadingId'] not in present
    edges = set()
    for path in SOURCE:
        for w in L.d(nodes[path], 'word'):
            for head, categories in E.head.f(w):
                key = (path, F.id.v(w), F.id.v(head))
                assert not collections.Counter(categories.split(', ')) - collections.Counter(links[key]), key
                edges.add(key)
    assert sum(len(categories) for key, categories in links.items() if key not in edges) == missing == 13


def test_every_parallel_word_edge_is_an_alignment_of_the_source():
    (api, _), SOURCE = tf(), source()
    F, E = api.F, api.E
    pairs = set()
    for path, (_, _, aligned, _) in SOURCE.items():
        pairs |= aligned
    edges = {(F.id.v(w), F.id.v(o)) for w in F.otype.s('word') for o in E.parallel.f(w)}
    assert edges <= pairs


def test_every_parallel_edge_of_a_line_links_a_line():
    api, _ = tf()
    F, E = api.F, api.E
    assert all(F.otype.v(m) == 'line' for n in F.otype.s('line') for m in E.parallel.f(n))
