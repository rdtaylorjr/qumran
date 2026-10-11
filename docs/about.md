# About Qumran-Digital

The source of this dataset is Qumran-Digital: Text und Lexikon, the DFG project 465277421 of the
Niedersächsische Akademie der Wissenschaften zu Göttingen, data version 2026-10-06, through its
public API `https://lexicon.qumran-digital.org/v1/qumran`.

The project transcribes the Dead Sea Scrolls and related manuscripts, lemmatizes and parses their
words, links dependent words to their heads, and shows every line beside its parallels in other
manuscripts, the Masoretic Text, and the Samaritan Pentateuch, word by word.

# Corpus

The [source](../source) directory contains the API responses for the 1,173 transcriptions of the
transcription index: 866 non-biblical manuscripts (`dss`), 263 biblical manuscripts
(`dss-biblical`), and 44 comparison texts (`non-dss`), the 39 books of the Masoretic Text and the
5 books of the Samaritan Pentateuch. For every transcription there are

*   `transcription.html`, the text with its parallels;
*   `columns.json`, the columns with their ids and names;
*   `shell.html`, the header with the manuscript id and the copyright notice;
*   `parsings.json`, the parsings and lemmas of every word that has them;
*   `syntax.json`, the dependency links of every word that has them.

These files have been downloaded by [download.py](../programs/download.py) and converted into
Text-Fabric format by [tfFromQumranDigital.py](../programs/tfFromQumranDigital.py).
We have a [specification](transcription.md) of how we model the text in Text-Fabric.
The conversion result is available in the [tf](../tf) directory.

The source also gives the database date of every parsing and lemma, the order and reading
priority of the other word of a dependency link, the database ids of the parallel manuscripts and
lines, the version links of the pages, and the marker linking a marginal reading to its place.
These are not included in the Text-Fabric data. They remain in the source files.

# License and citation

Qumran-Digital is created by the DFG project 465277421 Qumran-Digital: Text und Lexikon, which
publishes its data under the
[CC BY-SA 4.0 license](https://creativecommons.org/licenses/by-sa/4.0/).
Every transcription carries the copyright notice

```
© 2022 DFG-Projekt 465277421 Qumran-Digital: Text und Lexikon CC-BY-SA 4.0
Bereitgestellt durch das DFG-Projekt Nr. 465277421 Qumran-Digital: Text und Lexikon auf der Grundlage eines Textes des früheren Projekts Qumran-Wörterbuch der Niedersächsischen Akademie der Wissenschaften zu Göttingen, der auf einem Vorläufertext von Martin Abegg basierte.
```

The files in [source](../source) are the API responses as downloaded, without modification.

The Text-Fabric data in [tf](../tf) is a modified form of these files:

*   the data is converted from HTML and JSON to Text-Fabric, with every transcription a text,
    every word reading a word, and every part of an analysis a part;
*   the morphology is given in BHSA features, with the values mapped as declared in
    [morph.yaml](../yaml/morph.yaml), and `NA` where the parsing has no label for a category;
*   the placeholder `(noch nicht bearbeitet)` is left out of the glosses;
*   a line without words is given one empty word;
*   parallels and dependencies are given as edges between the nodes they link;
*   the fields listed under [Corpus](#corpus) are left out.

The [transcription](transcription.md) describes the conversion in full.

The source files and the Text-Fabric data are licensed under the
[CC BY-SA 4.0 license](https://creativecommons.org/licenses/by-sa/4.0/),
see [LICENSE](../LICENSE). They are provided as is, without warranties of any kind,
as stated in Section 5 of the license. If you share adapted material, you must license it
under the same license.
