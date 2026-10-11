import os
import re
import html
import json
import functools
import collections
from html.parser import HTMLParser
from concurrent.futures import ProcessPoolExecutor

import yaml
from tf.fabric import Fabric

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TF_FOLDER = 'tf'
SOURCE_FOLDER = 'source'
latest_data_folder = sorted(os.listdir(os.path.join(ROOT_DIR, TF_FOLDER)))[-1]
SOURCE_DIR = os.path.join(ROOT_DIR, SOURCE_FOLDER, latest_data_folder)

with open(os.path.join(ROOT_DIR, 'yaml', 'morph.yaml'), encoding='utf-8') as f:
    MORPH = yaml.safe_load(f)

INDEX = re.compile(r'<li class="list-item ([^"]+)">\s*<a href="/transcriptions/([^/"]+)/')
SHELL = re.compile(r'id="transcription_id_(\d+)"')
LEVEL = re.compile(r'level-(\d+)')
TAG = re.compile(r'<[^>]+>')
VOID = {'br', 'hr', 'img', 'input', 'meta', 'link', 'wbr'}
NOT_YET = '(noch nicht bearbeitet)'


class Page(HTMLParser):
    """Collects the lines and words of the main text, and the references and aligned words of the parallels."""

    def __init__(self):
        super().__init__()
        self.lines, self.words, self.references, self.pairs = [], [], set(), set()
        self.stack = []
        self.row = None
        self.line = None
        self.cell = None
        self.word = None
        self.reference = None
        self.anchor = None
        self.field = None

    def depth(self):
        return len(self.stack)

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        classes = (values.get('class') or '').split()
        if self.word is not None:
            self.word['tagged'] = True
        if tag not in VOID:
            self.stack.append((tag, classes))
        if tag == 'tr':
            self.row = None
            if 'line-verse' in classes or 'margin' in classes:
                self.row = 'line'
                number = values.get('id')
                self.line = {'id': int(number.split('-i')[1]) if number else None, 'margin': 'margin' in classes,
                             'label': '', 'text': ''}
            elif 'parallel-line' in classes:
                self.row = 'parallel'
        elif self.row == 'line' and ('line-verse-label' in classes or 'margin-label' in classes):
            self.cell = ('label', self.depth())
        elif self.row == 'line' and ('line-text' in classes or 'margin-text-line' in classes):
            self.cell = ('text', self.depth())
        elif self.row == 'line' and self.cell and self.cell[0] == 'text' and 'word' in classes and not self.word:
            levels = [int(m.group(1)) for _, names in self.stack for name in names if (m := LEVEL.fullmatch(name))]
            self.word = {'id': int(values['id']), 'word_id': int(values['data-word-id']), 'text': '',
                         'alt': max(levels) if levels else None, 'tagged': False, 'depth': self.depth(),
                         'margin': any('margin-text' in names for _, names in self.stack)}
        elif self.row == 'parallel' and tag == 'a' and values.get('href', '').startswith('/transcriptions/'):
            self.reference = [values['href'].split('/')[2], '', '']
            self.anchor = self.depth()
        elif self.row == 'parallel' and ('chapter-column-label' in classes or 'line-verse-label' in classes):
            self.field = (1 if 'chapter-column-label' in classes else 2, self.depth())
        elif self.row == 'parallel' and 'word' in classes and values.get('data-word-id') != '0':
            if self.reference is None:
                raise ValueError('a parallel word without a reference')
            for here in (values.get('data-parallel-id') or '').split(',') if values.get('data-parallel-id') else ():
                self.pairs.add((int(here), self.reference[0], int(values['id'][4:])))

    def handle_endtag(self, tag):
        if tag not in [name for name, _ in self.stack]:
            return
        while self.stack.pop()[0] != tag:
            pass
        if self.word is not None and self.depth() < self.word['depth']:
            self.words.append(self.word)
            self.word = None
        if self.field is not None and self.depth() < self.field[1]:
            self.field = None
        if self.anchor is not None and self.depth() < self.anchor:
            self.anchor = None
            self.references.add(tuple(self.reference))
        if self.cell is not None and self.depth() < self.cell[1]:
            self.cell = None
        if tag == 'tr' and self.row == 'line':
            self.lines.append(self.line)
            self.row = None
        elif tag == 'tr':
            self.row = None
            self.reference = None

    def handle_data(self, data):
        if self.word is not None:
            self.word['text'] += data
        if self.cell is not None and self.line is not None:
            self.line[self.cell[0]] += data
        if self.field is not None:
            self.reference[self.field[0]] += data


def read(path, kind):
    folder = os.path.join(SOURCE_DIR, 'transcriptions', path)
    page = Page()
    with open(os.path.join(folder, 'transcription.html'), encoding='utf-8') as f:
        page.feed(f.read())
    found = {'kind': kind}
    for name in ('columns', 'parsings', 'syntax'):
        with open(os.path.join(folder, f'{name}.json'), encoding='utf-8') as f:
            found[name] = json.load(f)
    with open(os.path.join(folder, 'shell.html'), encoding='utf-8') as f:
        found['id'] = int(SHELL.search(f.read()).group(1))
    return path, page, found


@functools.cache
def source():
    with open(os.path.join(SOURCE_DIR, 'transcription-index.html'), encoding='utf-8') as f:
        entries = INDEX.findall(f.read())
    with ProcessPoolExecutor() as pool:
        found = pool.map(read, [path for _, path in entries], [kind for kind, _ in entries], chunksize=4)
        return {path: (page, data) for path, page, data in found}


@functools.cache
def tf():
    TF = Fabric(locations=os.path.join(ROOT_DIR, TF_FOLDER, latest_data_folder), silent='deep')
    api = TF.load('''
        otype text html kind id word_id column line margin alt prefix trailer
        lex lex_id root_designation gloss@de word_class part priority
        sp nametype gn nu ps st vs vt prs_gn prs_nu prs_ps augment
        head parallel
    ''', silent='deep')
    texts = {api.F.text.v(t): t for t in api.F.otype.s('text')}
    nodes = {path: texts[data['columns']['sigla']] for path, (_, data) in source().items()}
    return api, nodes


@functools.cache
def paths():
    _, nodes = tf()
    return {node: path for path, node in nodes.items()}


def path_of(api, n):
    return paths()[api.L.u(n, 'text')[0]]


def test_every_transcription_is_a_text_with_its_siglum_class_id_and_columns():
    (api, nodes), SOURCE = tf(), source()
    F, L = api.F, api.L
    assert list(nodes.values()) == list(F.otype.s('text'))
    for path, (_, data) in SOURCE.items():
        text = nodes[path]
        assert (F.text.v(text), F.kind.v(text), F.id.v(text)) == (data['columns']['sigla'], data['kind'], data['id'])
        columns = [(f'c{F.id.v(c)}', F.column.v(c)) for c in L.d(text, 'column')]
        assert columns == [(c['id'], c['name']) for c in data['columns']['columns']], path


def test_every_line_has_the_id_label_margin_and_text_of_the_source():
    (api, nodes), SOURCE = tf(), source()
    F, L, T = api.F, api.L, api.T
    for path, (page, _) in SOURCE.items():
        found = [
            {'id': F.id.v(n), 'margin': F.margin.v(n) == 1, 'label': F.line.v(n) or '', 'text': T.text(n)}
            for n in L.d(nodes[path], 'line')
        ]
        assert found == page.lines, path


def test_every_word_of_the_main_text_is_a_slot_with_the_ids_text_level_and_margin_of_the_source():
    (api, nodes), SOURCE = tf(), source()
    F, L = api.F, api.L
    for path, (page, _) in SOURCE.items():
        found = [
            {'id': F.id.v(w), 'word_id': F.word_id.v(w), 'text': F.text.v(w) or '', 'alt': F.alt.v(w),
             'margin': F.margin.v(w) == 1, 'tagged': F.html.v(w) is not None}
            for w in L.d(nodes[path], 'word') if F.id.v(w)
        ]
        assert found == [{k: v for k, v in word.items() if k != 'depth'} for word in page.words], path


def test_the_markup_of_every_word_holds_its_text():
    api, _ = tf()
    F = api.F
    for w in F.otype.s('word'):
        if F.html.v(w):
            assert html.unescape(TAG.sub('', F.html.v(w))) == F.text.v(w)


def lexeme(lemma):
    return '_'.join(part for part in (lemma['lemma'], lemma.get('rootDesignation')) if part)


def expected_morphology(parsing):
    values = {}
    for feature, spec in MORPH.items():
        label = parsing.get(spec['field'])
        if label is None:
            values[feature] = spec.get('missing')
        elif label in spec['bhsa']:
            values[feature] = spec['bhsa'][label]
        elif label in (spec.get('kept') or {}):
            values[feature] = parsing.get(spec['field'] + 'Abbr') or label
        else:
            values[feature] = None
    return values


def test_every_parsing_is_a_part_of_its_word_with_its_lemma_and_morphology():
    (api, nodes), SOURCE = tf(), source()
    F, L, Fs = api.F, api.L, api.Fs
    for path, (_, data) in SOURCE.items():
        for w in L.d(nodes[path], 'word'):
            entry = data['parsings'].get(str(F.id.v(w)), {'parsings': []})
            expected = sorted(
                (lexeme(p), p['lemmaId'], p['wordPart'], p['parsingPriority'], tuple(expected_morphology(p).items()))
                for p in entry['parsings']
            )
            parts = sorted(
                (F.lex.v(p), F.lex_id.v(p), F.part.v(p), F.priority.v(p),
                 tuple((feature, Fs(feature).v(p)) for feature in MORPH))
                for p in L.u(w, 'part')
            )
            assert parts == expected, (path, F.id.v(w))


def test_every_lemma_is_a_lexeme_over_the_words_that_have_it():
    (api, nodes), SOURCE = tf(), source()
    F, L, Fs = api.F, api.L, api.Fs
    lemmas, words = {}, collections.defaultdict(set)
    for path, (_, data) in SOURCE.items():
        for w in L.d(nodes[path], 'word'):
            for lemma in data['parsings'].get(str(F.id.v(w)), {'lemmas': []})['lemmas']:
                lemmas[lemma['lemmaId']] = lemma
                words[lemma['lemmaId']].add(w)
    assert sorted(F.lex_id.v(n) for n in F.otype.s('lex')) == sorted(lemmas)
    for n in F.otype.s('lex'):
        lemma = lemmas[F.lex_id.v(n)]
        definition = lemma.get('shortDefinition')
        assert (F.lex.v(n), F.root_designation.v(n), F.word_class.v(n), Fs('gloss@de').v(n)) == (
            lexeme(lemma), lemma.get('rootDesignation'), lemma.get('wordClassAbbreviation') or None,
            None if definition in (None, NOT_YET) else definition,
        )
        assert set(L.d(n, 'word')) == words[F.lex_id.v(n)]


def test_every_dependency_edge_carries_the_links_of_the_source():
    (api, nodes), SOURCE = tf(), source()
    F, L, E = api.F, api.L, api.E
    links = collections.defaultdict(list)
    missing = 0
    for path, (page, data) in SOURCE.items():
        present = {word['id'] for word in page.words}
        for reading, entry in data['syntax'].items():
            for link in entry['dependentUpon']:
                links[(path, link['wordReadingId'], int(reading))].append(link['syntacticCategory'])
                missing += link['wordReadingId'] not in present
    edges = set()
    for path in SOURCE:
        for w in L.d(nodes[path], 'word'):
            for head, categories in E.head.f(w):
                key = (path, F.id.v(w), F.id.v(head))
                assert not collections.Counter(categories.split(',')) - collections.Counter(links[key]), key
                edges.add(key)
    assert sum(len(categories) for key, categories in links.items() if key not in edges) == missing == 13


def test_every_aligned_pair_of_parallel_words_is_an_edge():
    api, SOURCE = tf()[0], source()
    F, E = api.F, api.E
    pairs = {(path, here, there, other) for path, (page, _) in SOURCE.items() for here, there, other in page.pairs}
    edges = {
        (path_of(api, w), F.id.v(w), path_of(api, o), F.id.v(o)) for w in F.otype.s('word') for o in E.parallel.f(w)
    }
    assert edges == pairs


def test_every_parallel_reference_is_a_line_edge():
    api, SOURCE = tf()[0], source()
    F, E, T = api.F, api.E, api.T
    references = {(path, *reference) for path, (page, _) in SOURCE.items() for reference in page.references}
    edges = {
        (path_of(api, n), path_of(api, m), *T.sectionFromNode(m)[1:])
        for n in F.otype.s('line') for m in E.parallel.f(n)
    }
    assert edges == references
