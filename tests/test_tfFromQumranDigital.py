import os
import sys
import json
import importlib.util
from concurrent.futures import ThreadPoolExecutor

import pytest
from tf.fabric import Fabric

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROGRAM = os.path.join(ROOT_DIR, 'programs', 'tfFromQumranDigital.py')

spec = importlib.util.spec_from_file_location('tfFromQumranDigital', PROGRAM)
converter = importlib.util.module_from_spec(spec)
sys.modules['tfFromQumranDigital'] = converter
spec.loader.exec_module(converter)

INDEX = '''<ol id="item-list" class="item-list"><li class="list-item dss">
    <a href="/transcriptions/1QS/2026-10-06/index.html?v=2026-10-06" class="text-href-link">1QS</a>
</li><li class="list-item dss">
    <a href="/transcriptions/4QS/2026-10-06/index.html?v=2026-10-06" class="text-href-link">4QS</a>
</li><li class="list-item non-dss">
    <a href="/transcriptions/1_Sam/2026-10-06/index.html?v=2026-10-06" class="text-href-link">1 Sam</a>
</li></ol>'''


def word(number, text, word_id=None, classes='word'):
    return f'<span id="{number}" class="{classes}" data-word-id="{word_id or number}">{text}</span>'


SPACE = '<span class="word-space"> </span>'


def line(number, label, *content):
    return (
        f'<tr id="c1-i{number}" class="line-verse" data-name="{label}"><td class="line-verse-label" dir="ltr">'
        f'{label}</td><td class="line-text"><span class="body-text">{"".join(content)}</span></td></tr>'
    )


def margin(label, *content):
    return (
        f'<tr class="margin"><td class="margin-label" dir="ltr">{label}</td><td class="margin-text-line">'
        f'<span class="margin-line-text">{"".join(content)}</span></td></tr>'
    )


def reference(path, column, label):
    return (
        f'<span class="reference-label" dir="ltr"><a href="/transcriptions/{path}/2026-10-06/index.html#c9-i9">'
        f'<span class="label-formatting">(</span><span>{path}</span> <span class="chapter-column-label">{column}'
        f'</span>,<span class="line-verse-label">{label}</span><span class="label-formatting">)</span></a></span>'
    )


def parallel(*items):
    body = ''.join(f'<li data-manuscript-id="2">{item}</li>' for item in items)
    return f'<tr class="parallel-line"><td></td><td><ul data-manuscript-id=1 data-line-id=7>{body}</ul></td></tr>'


def par(number, text, here=None):
    aligned = f' data-parallel-id="{here}"' if here else ''
    return f'<span id="par-{number}" class="word" data-word-id="{number}"{aligned}>{text}</span>'


def column(number, label, *rows):
    return (
        f'<table id="c{number}" class="chapter-column" data-name="{label}"><thead><tr>'
        f'<th class="chapter-column-label" colspan="3" dir="ltr">{label}</th></tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table>'
    )


def page(*columns):
    return f'<div id="transcription_id_1"><header></header><main>{"".join(columns)}</table></main></div>'


S1 = page(
    column(
        11, '1',
        line(
            11, '1',
            '<span class="secondary-reference"> (1QH<sup>a</sup> 2,12) </span>',
            word(11, 'ב<span class="formatting start-broken-context">[</span>ר<span class="formatting stop-broken-context">]</span>ית'),
            SPACE,
            word(12, 'ליה<ins><sub>ו</sub></ins>ה'),
            SPACE,
            '<span class="alternative-reading level-1"><span class="formatting start-alternative">(</span>',
            word(13, 'ליהוה', word_id=12, classes='word no-details'),
            '<span class="formatting end-alternative">)</span></span>',
            SPACE,
            word(14, 'עמו'),
            '<sup class="marginal-pointer" data-margin-word-group="0">a‏</sup>',
            SPACE,
            '<span class="margin-text"><span class="marginal-reading" data-margin-word-group="0"><sup>a</sup>',
            word(15, 'עם'),
            '</span></span>',
        ),
        parallel(
            '<span class="body-text">' + par('7c4c74c0', '…').replace('data-word-id="7c4c74c0"', 'data-word-id="0"')
            + '</span>' + reference('4QS', 'frg. 1', '2') + '<span class="line-text"><span class="body-text">'
            + par(21, 'ברית', 11) + SPACE + par(22, 'עמו', '14,15') + SPACE + par(23, 'כול') + '</span></span>',
        ),
        line(16, '2'),
        line(17, '3', word(17, 'ויאמר'), SPACE, word(18, 'משה'), SPACE),
        margin('Rd.', word(19, 'אל')),
        parallel(
            reference('4QS', 'frg. 1', '3') + '<span class="line-text"><span class="body-text">'
            + par(24, 'אל', 19) + '</span></span>',
        ),
    ),
)

S2 = page(
    column(
        21, 'frg. 1',
        line(20, '1', word(20, '--]')),
        line(21, '2', word(21, 'ברית'), SPACE, word(22, 'עמו'), SPACE, word(23, 'כול')),
        line(24, '3', word(24, 'אל')),
    ),
)

S3 = page(column(31, '1', line(31, '1', word(31, 'וַיְהִי', classes='word no-details'), SPACE)))

PARSINGS = {
    '11': {
        'parsings': [
            {'lemma': 'ב', 'lemmaId': 1, 'wordPart': 0, 'parsingPriority': 0, 'wordClass': 'Präposition',
             'wordClassAbbr': 'praep.'},
            {'lemma': 'ברית', 'lemmaId': 2, 'wordPart': 1, 'parsingPriority': 0, 'wordClass': 'Nomen femininum',
             'wordClassAbbr': 'n.f.', 'gender': 'femininum', 'genderAbbr': 'f.', 'number': 'singularis',
             'numberAbbr': 'sg.', 'state': 'determinatus', 'stateAbbr': 'det.'},
        ],
        'lemmas': [
            {'lemma': 'ב', 'lemmaId': 1, 'rootDesignation': 'I', 'shortDefinition': 'in, an, bei',
             'wordClassAbbreviation': 'praep.'},
            {'lemma': 'ברית', 'lemmaId': 2, 'rootDesignation': 'I', 'shortDefinition': '(noch nicht bearbeitet)',
             'wordClassAbbreviation': 'n.f.'},
        ],
    },
    '17': {
        'parsings': [
            {'lemma': 'ו', 'lemmaId': 3, 'wordPart': 0, 'parsingPriority': 0, 'wordClass': 'Konjunktion',
             'wordClassAbbr': 'conj.'},
            {'lemma': 'אמר', 'lemmaId': 4, 'wordPart': 1, 'parsingPriority': 0, 'wordClass': 'Verbalwurzel',
             'wordClassAbbr': 'vb.', 'verbStem': 'Qal (Hebr.)', 'verbStemAbbr': 'qal',
             'verbTense': 'Imperfekt consecutivus', 'verbTenseAbbr': 'impf.cons.', 'person': '3. Person',
             'personAbbr': '3.', 'gender': 'maskulinum', 'genderAbbr': 'm.', 'number': 'singularis',
             'numberAbbr': 'sg.'},
        ],
        'lemmas': [
            {'lemma': 'ו', 'lemmaId': 3, 'shortDefinition': 'und', 'wordClassAbbreviation': 'conj.'},
            {'lemma': 'אמר', 'lemmaId': 4, 'shortDefinition': 'sagen', 'wordClassAbbreviation': 'vb.'},
        ],
    },
    '18': {
        'parsings': [
            {'lemma': 'משה', 'lemmaId': 5, 'wordPart': 0, 'parsingPriority': 0, 'wordClass': 'Personenname',
             'wordClassAbbr': 'n.pr.'},
            {'lemma': 'משה', 'lemmaId': 5, 'wordPart': 0, 'parsingPriority': 1, 'wordClass': 'Ortsname',
             'wordClassAbbr': 'n.l.'},
        ],
        'lemmas': [{'lemma': 'משה', 'lemmaId': 5, 'shortDefinition': 'Mose', 'wordClassAbbreviation': 'n.pr.'}],
    },
    '12': {'parsings': [], 'lemmas': []},
}


def link(number, reading, category, column='1', label='3', uncertain=False):
    return {
        'wordReadingId': number, 'reading': reading, 'syntacticCategory': category, 'location1': column,
        'location2': label, 'isUncertain': uncertain, 'isGenerated': False, 'isExternalToPhrase': False,
        'priorityOfReading': 0, 'orderedId': 0,
    }


SYNTAX = {
    '17': {'wordReadingId': 17, 'reading': 'ויאמר',
           'dependentUpon': [link(18, 'משה', 'Subjekt', uncertain=True), link(18, 'משה', 'Pendens')],
           'dependedOnBy': []},
    '18': {'wordReadingId': 18, 'reading': 'משה', 'dependentUpon': [],
           'dependedOnBy': [link(17, 'ויאמר', 'Subjekt', uncertain=True)]},
    '11': {'wordReadingId': 11, 'reading': 'ברית', 'dependentUpon': [link(19, 'אל', 'gen. Attribut', label='1')],
           'dependedOnBy': []},
}


def write(folder, path, siglum, number, html, parsings=None, syntax=None):
    target = folder / 'transcriptions' / path
    target.mkdir(parents=True)
    (target / 'transcription.html').write_text(html, encoding='utf-8')
    (target / 'columns.json').write_text(json.dumps({'columns': [], 'sigla': siglum}), encoding='utf-8')
    (target / 'shell.html').write_text(f'<div id="transcription_id_{number}"></div>', encoding='utf-8')
    if parsings is not None:
        (target / 'parsings.json').write_text(json.dumps(parsings), encoding='utf-8')
        (target / 'syntax.json').write_text(json.dumps(syntax), encoding='utf-8')


def source(tmp_path):
    folder = tmp_path / 'source'
    folder.mkdir()
    (folder / 'transcription-index.html').write_text(INDEX, encoding='utf-8')
    write(folder, '1QS', '1QS', 1, S1, PARSINGS, SYNTAX)
    write(folder, '4QS', '4QS', 2, S2, {}, {})
    write(folder, '1_Sam', '1_Sam', 3, S3)
    return folder


def build(tmp_path, report=None):
    target = tmp_path / 'tf'
    assert converter.convert(source(tmp_path), target, ThreadPoolExecutor, report=report)
    return Fabric(locations=str(target), silent='deep').loadAll(silent='deep')


def test_index_entries_give_path_and_class_in_index_order():
    assert converter.index_entries(INDEX) == [('1QS', 'dss'), ('4QS', 'dss'), ('1_Sam', 'non-dss')]


def test_transcription_reads_columns_lines_and_words_with_the_text_around_them():
    columns, _ = converter.transcription(S1)
    (first,) = columns
    assert (first.id, first.label) == (11, '1')
    assert [(line.id, line.label, line.margin, len(line.words)) for line in first.lines] == [
        (11, '1', False, 5), (16, '2', False, 0), (17, '3', False, 2), (None, 'Rd.', True, 1),
    ]
    words = first.lines[0].words
    assert [(w.id, w.word_id, w.text, w.prefix, w.trailer, w.alt, w.margin) for w in words] == [
        (11, 11, 'ב[ר]ית', ' (1QHa 2,12) ', ' ', None, False),
        (12, 12, 'ליהוה', '', ' (', None, False),
        (13, 12, 'ליהוה', '', ') ', 1, False),
        (14, 14, 'עמו', '', 'a‏ a', None, False),
        (15, 15, 'עם', '', '', None, True),
    ]


def test_transcription_keeps_the_markup_of_words_that_have_any():
    columns, _ = converter.transcription(S1)
    words = columns[0].lines[0].words
    assert words[1].html == 'ליה<ins><sub>ו</sub></ins>ה'
    assert words[0].html.startswith('ב<span class="formatting start-broken-context">[</span>')
    assert words[3].html is None


def test_transcription_reads_parallels_by_reference_with_the_lines_they_stand_under():
    _, parallels = converter.transcription(S1)
    assert parallels == (
        converter.Parallel((0, 0), '4QS', 'frg. 1', '2', ((21, (11,)), (22, (14, 15)), (23, ()))),
        converter.Parallel((1, 3), '4QS', 'frg. 1', '3', ((24, (19,)),)),
    )


def test_morphology_maps_declared_labels_and_keeps_the_others_as_abbreviations():
    morph = converter.load_morph()
    parsing = {
        'wordClass': 'Nomen', 'wordClassAbbr': 'n.', 'state': 'constructus', 'stateAbbr': 'cs.',
        'verbStem': 'Polel (Hebr.)', 'verbStemAbbr': 'po.', 'suffixPerson': '1. Person', 'suffixPersonAbbr': '1.',
    }
    assert converter.morphology(parsing, morph) == {'sp': 'n.', 'st': 'c', 'vs': 'po.', 'prs_ps': 'p1'}
    assert converter.morphology({'wordClass': 'ohne', 'wordClassAbbr': ''}, morph) == {'sp': 'ohne'}
    assert converter.morphology({'wordClass': 'Ortsname'}, morph) == {'sp': 'nmpr', 'nametype': 'topo'}


def test_morphology_stops_at_an_undeclared_label():
    with pytest.raises(KeyError, match='Supinum'):
        converter.morphology({'verbTense': 'Supinum'}, converter.load_morph())


def test_every_label_of_the_mapping_is_a_bhsa_value_or_kept():
    for spec in converter.load_morph().values():
        assert not set(spec['bhsa']) & set(spec.get('kept') or {})


def test_convert_makes_each_transcription_a_text_with_columns_and_lines(tmp_path):
    api = build(tmp_path)
    F, L, T = api.F, api.L, api.T
    texts = F.otype.s('text')
    assert [(F.text.v(t), F.kind.v(t), F.id.v(t)) for t in texts] == [
        ('1QS', 'dss', 1), ('4QS', 'dss', 2), ('1_Sam', 'non-dss', 3),
    ]
    lines = L.d(texts[0], 'line')
    assert [T.sectionFromNode(n) for n in lines] == [('1QS', '1', '1'), ('1QS', '1', '2'), ('1QS', '1', '3'),
                                                     ('1QS', '1', 'Rd.')]
    assert [(F.id.v(n), F.margin.v(n)) for n in lines] == [(11, None), (16, None), (17, None), (None, 1)]


def test_convert_reproduces_the_text_of_every_line(tmp_path):
    api = build(tmp_path)
    T, F = api.T, api.F
    first = F.otype.s('line')[0]
    assert T.text(first) == ' (1QHa 2,12) ב[ר]ית ליהוה (ליהוה) עמוa‏ aעם'


def test_convert_gives_a_line_without_words_one_empty_word(tmp_path):
    api = build(tmp_path)
    F, L = api.F, api.L
    (empty,) = L.d(F.otype.s('line')[1], 'word')
    assert (F.text.v(empty), F.id.v(empty)) == (None, None)


def test_convert_makes_a_part_for_every_part_of_every_analysis(tmp_path):
    api = build(tmp_path)
    F, L = api.F, api.L
    words = {F.id.v(w): w for w in F.otype.s('word') if F.id.v(w)}
    parts = sorted(L.u(words[17], 'part'), key=F.part.v)
    found = [(F.lex.v(p), F.lex_id.v(p), F.part.v(p), F.sp.v(p), F.vs.v(p), F.vt.v(p), F.ps.v(p), F.gn.v(p))
             for p in parts]
    assert found == [('ו', 3, 0, 'conj', None, None, None, None), ('אמר', 4, 1, 'verb', 'qal', 'wayq', 'p3', 'm')]
    analyses = sorted((F.priority.v(p), F.nametype.v(p)) for p in L.u(words[18], 'part'))
    assert analyses == [(0, 'pers'), (1, 'topo')]
    (noun,) = [p for p in L.u(words[11], 'part') if F.part.v(p) == 1]
    assert (F.st.v(noun), F.gn.v(noun), F.nu.v(noun)) == ('det.', 'f', 'sg')
    assert not L.u(words[12], 'part')


def test_convert_makes_a_lexeme_for_every_lemma_over_its_words(tmp_path):
    api = build(tmp_path)
    F, L, Fs = api.F, api.L, api.Fs
    lexemes = {F.lex_id.v(n): n for n in F.otype.s('lex')}
    assert sorted(lexemes) == [1, 2, 3, 4, 5]
    covenant = lexemes[2]
    assert (F.lex.v(covenant), F.root_designation.v(covenant), F.word_class.v(covenant)) == ('ברית', 'I', 'n.f.')
    assert Fs('gloss@de').v(covenant) is None
    assert Fs('gloss@de').v(lexemes[1]) == 'in, an, bei'
    assert [F.id.v(w) for w in L.d(lexemes[5], 'word')] == [18]


def test_convert_links_lines_and_aligned_words_to_their_parallels(tmp_path):
    report = converter.Counter()
    api = build(tmp_path, report)
    F, E, T = api.F, api.E, api.T
    pairs = sorted((F.id.v(a), F.id.v(b)) for a in F.otype.s('word') for b in E.parallel.f(a))
    assert pairs == [(11, 21), (14, 22), (15, 22), (19, 24)]
    lines = sorted(T.sectionFromNode(a) + T.sectionFromNode(b) for a in F.otype.s('line') for b in E.parallel.f(a))
    assert lines == [('1QS', '1', '1', '4QS', 'frg. 1', '2'), ('1QS', '1', 'Rd.', '4QS', 'frg. 1', '3')]
    assert report['parallel words without alignment'] == 1


def test_convert_links_every_dependent_to_its_head_with_its_category(tmp_path):
    report = converter.Counter()
    api = build(tmp_path, report)
    F, E = api.F, api.E
    words = {F.id.v(w): w for w in F.otype.s('word') if F.id.v(w)}
    assert E.head.f(words[18]) == ((words[17], 'Subjekt, Pendens'),)
    assert E.head_uncertain.f(words[18]) == ((words[17], 'Subjekt'),)
    assert E.head.f(words[19]) == ((words[11], 'gen. Attribut'),)
    assert not E.head_uncertain.f(words[19])
    assert report['dependencies'] == 3


def test_convert_writes_the_attribution_and_license_into_the_metadata(tmp_path):
    build(tmp_path)
    otext = (tmp_path / 'tf' / 'otext.tf').read_text(encoding='utf-8')
    assert '@copynote1=© 2022 DFG-Projekt 465277421 Qumran-Digital: Text und Lexikon' in otext
    assert '@licenseUrl=https://creativecommons.org/licenses/by-sa/4.0/' in otext


def test_convert_removes_features_of_an_earlier_conversion(tmp_path):
    target = tmp_path / 'tf'
    target.mkdir()
    (target / 'verse.tf').write_text('@node\n', encoding='utf-8')
    assert converter.convert(source(tmp_path), target, ThreadPoolExecutor)
    assert not (target / 'verse.tf').exists()


def test_main_reports_success_and_failure(tmp_path):
    folder = source(tmp_path)
    assert converter.main(['--source', str(folder), '--target', str(tmp_path / 'a')], ThreadPoolExecutor) == 0
    (tmp_path / 'empty').mkdir()
    (tmp_path / 'empty' / 'transcription-index.html').write_text('', encoding='utf-8')
    empty = ['--source', str(tmp_path / 'empty'), '--target', str(tmp_path / 'b')]
    assert converter.main(empty, ThreadPoolExecutor) == 1
