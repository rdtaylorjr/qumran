# Qumran

[![etcbc](docs/images/etcbc.png)](http://www.etcbc.nl)
![logo](docs/images/logo.png)
[![tf](docs/images/tf-small.png)](https://annotation.github.io/text-fabric/tf)

## About

This is the
[text-fabric](https://github.com/annotation/text-fabric)
representation of Qumran-Digital: Text und Lexikon, with the transcriptions of the Dead Sea
Scrolls and related manuscripts, their lemmas, morphology, and syntax, and their word-by-word
parallels with each other, the Masoretic Text, and the Samaritan Pentateuch.

See [about](docs/about.md) for more information about this textual source,
and for the copyright and license of the data.

The conversion to Text-Fabric is the work of Rusty Taylor.

There is more information on the
[transcription](docs/transcription.md).

## How to use

### Having Text-Fabric installed

This data can be processed by
[Text-Fabric](https://annotation.github.io/text-fabric/tf).

After [installing Text-Fabric](https://annotation.github.io/text-fabric/tf/about/install.html),
you can start the Text-Fabric browser by this command

```sh
text-fabric rdtaylorjr/qumran
```

Alternatively, you can work in a Jupyter notebook and say

```python
from tf.app import use

A = use('rdtaylorjr/qumran')
```

See also
[start](https://nbviewer.jupyter.org/github/rdtaylorjr/qumran/blob/main/tutorial/start.ipynb)
and
[search](https://nbviewer.jupyter.org/github/rdtaylorjr/qumran/blob/main/tutorial/search.ipynb).

# Author

Rusty Taylor
