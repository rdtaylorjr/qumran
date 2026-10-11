# Feature documentation

Here you find a description of the transcription of Qumran-Digital,
the
[Text-Fabric model](https://annotation.github.io/text-fabric/tf/about/datamodel.html)
in general, and the node types and features of the Qumran-Digital corpus in particular.

See also

*   [about](about.md) for the provenance of the data;
*   [TF docs](https://annotation.github.io/text-fabric/tf) for documentation on Text-Fabric.

## Transcription

The source is the Qumran-Digital API, version 1, data version 2026-10-06: for every transcription
of the index a transcription page, its columns, its header, and the parsings and syntax of its
words. A transcription page lays out the text in columns (fragments or columns of a scroll,
chapters of a book), the columns in lines (lines or verses), and the lines in word readings. Under
a line it shows the parallel lines of other texts, word by word.

Every transcription becomes a [*text*](#node-type-text), in the order of the index, following the
[ETCBC Targum corpus](https://github.com/ETCBC/targum), where every manuscript is a text.
The name of a text is the siglum of its `columns.json`, which writes a superscript between carets,
a space as an underscore, and a slash as a tilde, such as `1QH^a^`, `Mur._6`, `5~6Hev1b`.
Its `kind` is its class in the index: `dss` (866 texts), `dss-biblical` (263), or `non-dss` (44:
the Masoretic Text, `Gen` to `2_Chron`, and the Samaritan Pentateuch, `Gen_SP` to `Dtn_SP`).
Names are those of the source.

A column becomes a [*column*](#node-type-column), and a line, or a margin line of the composite
Ben Sira texts, a [*line*](#node-type-line). Labels are those of the source.

A word reading of the main text becomes a [*word*](#node-type-word). The readings of one word,
such as a reading and its alternatives, are separate words with the same `word_id`. A reading
that occurs twice in a transcription, as in the composite texts and in repeated lines, is a word at
each place. The text of a word is its text in the page, with the editorial brackets and the
circlet of an uncertain letter as given. Where the word has markup, such as a supralinear
insertion `<ins><sup>ו</sup></ins>` or a deletion `<del>`, the markup is kept in `html`.
The text of a line before its first word is the `prefix` of that word, such as the reference
` (1QHa 2,12) ` of a composite text. The text after a word up to the next word of its line is
its `trailer`: the space, the brackets of an alternative reading, the marker of a marginal reading.
The `prefix`, `text`, and `trailer` of the words of a line give the text of the line.
A line without words is given one empty word, without `text` and `id`. This affects 20 lines.

Every parsing of a word becomes a [*part*](#node-type-part) over the word: a word divided into
parts, such as ו and מן, has a part for each, and a word with competing analyses has the parts of
each analysis, ranked by `priority`. The morphology is given in the features of the
[BHSA](https://etcbc.github.io/bhsa/), with the values of the BHSA where the source label has a
value of the same meaning, and the abbreviation of the source label where it has not, such as
`det.` for a noun with the article. Where the parsing has no label for a category, the value is
`NA`, as in the BHSA. Each label is declared in [morph.yaml](../yaml/morph.yaml), with the reason
for every label that keeps its abbreviation. A label that is not declared stops the conversion.

Every lemma becomes a [*lex*](#node-type-lex) over the words that have it. Its `lex` is the
lemma with its root designation, which tells homonyms apart, such as `יחד_I` and `יחד_II`; this
gives 4,359 values for the 4,411 lemmas, since for 51 values the source has more than one lemma
with the same lemma and root designation, such as the two entries of לא. Its gloss is the German
short definition of the source, left out where the source has the placeholder
`(noch nicht bearbeitet)`.

The parallels become the edge [*parallel*](#edge-parallel), and the dependency links the edges
[*head*](#edge-head), as described below.

## Text-Fabric model

The Text-Fabric model views the text as a series of atomic units, called
*slots*. In this corpus [*words*](#node-type-word) are the slots.

On top of that, more complex textual objects can be represented as *nodes*. In
this corpus we have node types for:

[*word*](#node-type-word),
[*part*](#node-type-part),
[*line*](#node-type-line),
[*lex*](#node-type-lex),
[*column*](#node-type-column),
[*text*](#node-type-text).

The type of every node is given by the feature
[*`otype`*](https://annotation.github.io/text-fabric/tf/cheatsheet.html#f-node-features).
Every node is linked to a subset of slots by
[*`oslots`*](https://annotation.github.io/text-fabric/tf/cheatsheet.html#special-edge-feature-oslots).

Nodes can be annotated with features, and pairs of nodes with edge features.
See the tables below.

Text-Fabric supports up to three customisable section levels.
In this corpus we use
[*text*](#node-type-text), [*column*](#node-type-column), and [*line*](#node-type-line).

A part has the same slot as its word, and Text-Fabric places it above the word. In a search
template, put a part directly under its line or text:

```
text text=1QS
  part sp=verb vs=hif
```

# Reference table of features

*(Keep this under your pillow)*

## *absent*

When we say that a feature is *absent* for a node, we mean that the node has no value
for the feature. For example, if the feature `alt` is absent for node `n`, then
`F.alt.v(n)` results in the Python value `None`, not the string `'None'`.

In queries, you can test for absence by means of `#`:

```
word alt#
```

gives all words where the feature `alt` is absent.

See also
[search templates](https://annotation.github.io/text-fabric/tf/about/searchusage.html)
under **Value specifications**.

## Node type [*word*](#word)

A word reading of the main text: 807,931 words.

feature | values | description
------- | ------ | ------
*`text`* | `ב[ר]ית` `וַיְהִי` | the text of the reading as given, without markup
*`html`* | `ליה<ins><sub>ו</sub></ins>ה` | the markup of the reading, where it has any (22,992 words)
*`prefix`* | ` (1QHa 2,12) ` | the text of the line before its first word (5,109 words)
*`trailer`* | ` ` ` (` `) ` | the text after the word up to the next word of its line
*`id`* | `4071` | database id of the reading
*`word_id`* | `4071` | database id of the word; a reading and its alternatives share it
*`alt`* | `1` `2` `3` `4` | level of the alternative reading the word is in (4,030, 253, 31, 4 words)
*`margin`* | `1` | the word is in a marginal reading (1,235 words)

## Node type [*part*](#part)

A part of an analysis of a word: 146,407 parts of 106,223 words, of which 5,184 belong to
analyses after the first.

feature | values | description
------- | ------ | ------
*`lex`* | `ברית` `יחד_II` | lemma, with its root designation where it has one
*`lex_id`* | `38` | database id of the lemma
*`part`* | `0` `1` `2` | number of the part within the word, 0 being the first
*`priority`* | `0` `1` | rank of the analysis, 0 being the first
*`sp`* | `subs` `verb` `prep` `conj` `nmpr` `advb` `nega` `prps` `prde` `prin` `intj` `inrg`; `n.` `not.acc.` `part.rel.` `pron.indef.` `Buchstabe` `Zahlzeichen` `ohne` | part of speech
*`nametype`* | `pers` `gens` `topo`; `n.d.` `MN` | named entity type
*`gn`* | `m` `f` `NA`; `comm.` | grammatical gender
*`nu`* | `sg` `pl` `du` `NA` | grammatical number
*`ps`* | `p1` `p2` `p3` `NA` | grammatical person
*`st`* | `a` `c` `NA`; `det.` | state, `det.` a noun with the article
*`vs`* | `qal` `pasq` `nif` `piel` `pual` `hif` `hof` `hit` `htpo` `hsht` `peal` `peil` `pael` `htpe` `etpe` `NA`; `po.` `polal` `hitpo.` `pil.` `pulpal` `hitpal.` `puʿlal` `nufʿal` `etaf.` | verbal stem
*`vt`* | `perf` `impf` `wayq` `impv` `infc` `NA`; `pf.cons.` `ptz.` `koh.` | verbal tense
*`prs_gn`* | `m` `f` `NA`; `comm.` | pronominal suffix gender
*`prs_nu`* | `sg` `pl` `du` `NA` | pronominal suffix number
*`prs_ps`* | `p1` `p2` `p3` `NA` | pronominal suffix person
*`augment`* | `loc.` `energ.` `adv.` | augment, which the BHSA does not have

The values before the semicolon are those of the BHSA, the values after it the abbreviations of
the source labels without a BHSA value, see [morph.yaml](../yaml/morph.yaml).

## Node type [*lex*](#lex)

A lemma, over the words that have it: 4,411 lemmas.

feature | values | description
------- | ------ | ------
*`lex`* | `ברית` `יחד_II` | lemma, with its root designation where it has one
*`lex_id`* | `38` | database id of the lemma
*`root_designation`* | `I` `II` | number of the root of the lemma
*`gloss@de`* | `Vertrag, Bund` | German short definition (2,309 lemmas)
*`word_class`* | `n.m.` `vb.` `pron. 3.m.sg.` | word class of the lemma, as the source abbreviates it

## Node type [*line*](#line)

Section level 3. A line or verse: 88,287 lines.

feature | values | description
------- | ------ | ------
*`line`* | `1` `25b` `Rd.` | label of the line
*`id`* | `4071` | database id of the line, absent where the source gives none: margin lines and 17 lines of SirB and SirM
*`margin`* | `1` | the line is a margin line of a composite Ben Sira text (106 lines)

## Node type [*column*](#column)

Section level 2. A column, fragment, or chapter: 13,074 columns.

feature | values | description
------- | ------ | ------
*`column`* | `1` `frg. 5` `Handle Sheet v.` | label of the column
*`id`* | `4071` | database id of the column

## Node type [*text*](#text)

Section level 1. A transcription: 1,173 texts.

feature | values | description
------- | ------ | ------
*`text`* | `1QS` `1QH^a^` `Gen` `Gen_SP` | siglum of the transcription
*`kind`* | `dss` `dss-biblical` `non-dss` | class of the transcription in the index
*`id`* | `1` | database id of the manuscript

## Edge [*parallel*](#parallel)

From a line to a parallel line in another text or in the same text, and from a word to the
parallel word aligned with it: 146,345 line edges and 919,527 word edges.

The page shows the parallels of a line in a row under it, each parallel line after a reference
such as `(4Q256 9,1)`. The parallel line is the line of that text with the column and line
labels of the reference. A parallel word aligned with a word gives the id of that reading; the
word is looked up in the lines the row stands under, which are the lines since the previous
parallel row, more than one where a verse of a composite text runs over several lines. The line
edges go from the lines that hold an aligned word, or from the line right above the row where
none does. Where the line of a reference does not hold the parallel word, as when the word is in a
margin line, the word is taken from the column of the reference if the column holds it once.

The 10,392 ellipses `…` that stand for omitted text in the parallel rows are not words and are
not linked. Of the other parallel words, 45,175 are not aligned with a word, and 11 give a reading
that is not in the lines the row stands under; these are not linked. The source lists 331 lines,
such as 1QS 6,5, as parallel to themselves.

## Edge [*head*](#head)

From a word to the word it depends on, valued by the syntactic category of the dependent:
75,511 edges.

The source lists, for every word, the words that depend on it, as `dependentUpon`, with the
syntactic category of the dependent, such as `Subjekt`, and the column and line where it is.
Where that line does not hold the dependent, as when it is in a margin line, the dependent is taken
from the column if the column holds it once.
Two words can be linked more than once, such as a preposition that is both `Präposition` and
`Adverb` of its verb, so the value of an edge is the categories of all the links between the two
words, in source order, separated by commas, as the BHSA separates the values of `nametype`.
This affects 10,582 edges. Of the source links,
13 give a reading that is not in the text; these are not linked.

edge | values | description
------- | ------ | ------
*`head`* | `Subjekt` `Objekt` `Präposition` `Adverb` `gen. Attribut` `Adverb,Präposition` | from a word to its head, valued by the categories of the links
*`head_uncertain`* | `Subjekt` | as `head`, valued by the categories of the links the source marks as uncertain (2,180 edges)
*`head_generated`* | `Präposition` | as `head`, valued by the categories of the links the source marks as generated (979 edges)
*`head_external`* | `Subjekt` | as `head`, valued by the categories of the links the source marks as external to the phrase (5,318 edges)

In a search template:

```
w1:word
w2:word
w1 -head~Subjekt> w2
```

# Text formats

The following text formats are defined (you can also list them with `T.formats`).

format | description
--- | ---
`text-orig-full`     | the text of every line as in the source: the prefix, text, and trailer of its words
