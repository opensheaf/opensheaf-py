"""Inputs from YAML (or JSON) files: `osheaf deposit --from paper.yaml`.

A file holds the same options as the command line, with their names (`title`,
`author` or `authors`, `extra-source` or `extra-sources`, `keyword` or
`keywords`, `abstract`, `abstract-file`, `available`, ...); a list of such
mappings makes several deposits, in order. Options given on the command line
override the file. Paths are relative to the file.

YAML is read with every value kept as text (PyYAML's BaseLoader), so that
nothing is converted silently: `2611.14296` stays an arXiv identifier,
`2025-01-02` a date, `1.10` a version. The metadata the tools write stays
JSON.

    id: kpz-uniqueness
    source: paper.tex
    pdf: paper.pdf
    extra-sources:
      - refs.bib
      - {file: figures/fig1.pdf, path: figures/fig1.pdf}
    title: Energy solutions of KPZ are unique
    authors:
      - Doe, Jane|Example University
      - {name: "Roe, Richard", affiliation: Another University}
    abstract: |
      We prove uniqueness of energy solutions of $\\partial_t h = \\Delta h + \\xi$.

      A second paragraph.
    keywords: [KPZ, energy solutions]
    rights: cc-by-4.0
    available: 2015-08-31
    related: ["IsIdenticalTo:arxiv:1508.07764"]
"""

import json
import sys
from pathlib import Path

ALIASES = {"authors": "author", "keywords": "keyword", "extra_sources": "extra_source",
           "relations": "related", "tools": "toolchain", "date": "available"}
PATHS = ("source", "pdf", "abstract_file", "folder")
LISTS = ("author", "keyword", "extra_source", "related", "toolchain")


def load(path):
    """The entries of a YAML or JSON file: a list of mappings."""
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if p.suffix.lower() == ".json":
        data = json.loads(text)
    else:
        try:
            import yaml
        except ImportError:
            sys.exit("reading YAML needs PyYAML: pip install pyyaml")
        try:
            data = yaml.load(text, Loader=yaml.BaseLoader)
        except yaml.YAMLError as e:
            sys.exit(f"{path}: not valid YAML: {e}\n(texts with ': ' or starting with a"
                     " special character need quotes)")
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list) or not all(isinstance(x, dict) for x in data):
        sys.exit(f"{path}: expected a mapping of options, or a list of them")
    return [normalise(x, p.parent) for x in data]


def normalise(entry, base):
    out = {}
    for k, v in entry.items():
        k = str(k).strip().lower().replace("-", "_")
        k = ALIASES.get(k, k)
        if k in LISTS and not isinstance(v, list):
            v = [v]
        if k == "author":
            v = [a if isinstance(a, str) else
                 a["name"] + (f"|{a['affiliation']}" if a.get("affiliation") else "") for a in v]
        elif k == "extra_source":
            v = [str(base / x) if isinstance(x, str) and "=" not in x else
                 (str(base / x.partition("=")[0]) + "=" + x.partition("=")[2]) if isinstance(x, str) else
                 str(base / x["file"]) + (f"={x['path']}" if x.get("path") else "") for x in v]
        elif k == "toolchain":
            v = [x if isinstance(x, str) else "=".join(next(iter(x.items()))) for x in v]
        elif k in PATHS and isinstance(v, str):
            v = str(base / v)
        elif k == "after":
            v = int(v)
        out[k] = v
    return out


def merge(args, entry, parser, command):
    """A copy of ARGS with the values of ENTRY where the command line gave none."""
    import argparse
    ns = argparse.Namespace(**vars(args))
    known = set(vars(args))
    unknown = [k for k in entry if k not in known]
    if unknown:
        parser.error(f"{command}: unknown option(s) in the file: {', '.join(sorted(unknown))}")
    for k, v in entry.items():
        if getattr(ns, k) in (None, False, []):
            setattr(ns, k, v)
    return ns
