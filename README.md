# opensheaf-py

[![tests](https://github.com/opensheaf/opensheaf-py/actions/workflows/tests.yml/badge.svg)](https://github.com/opensheaf/opensheaf-py/actions/workflows/tests.yml)
[![pages](https://github.com/opensheaf/opensheaf-py/actions/workflows/pages.yml/badge.svg)](https://github.com/opensheaf/opensheaf-py/actions/workflows/pages.yml)
[![archive examples](https://github.com/opensheaf/archive-template/actions/workflows/examples.yml/badge.svg)](https://github.com/opensheaf/archive-template/actions/workflows/examples.yml)
[![Python](https://img.shields.io/badge/python-3.9%E2%80%933.13-blue)](pyproject.toml)
[![licence: GPL v3+](https://img.shields.io/badge/licence-GPL--3.0--or--later-blue)](LICENSE)

> [!WARNING]
> **Draft.** OpenSheaf 0.1 is a draft specification. Until version 1.0, any
> revision may change the format in incompatible ways. Archives and collections made now
> may have to be rebuilt or migrated, and the tools follow the latest draft.
> Do not rely on it yet for anything you cannot redo.

The unit tests run on Python 3.9 and 3.13; the testing grounds of the two
templates build archives and collections from the
[example papers](https://github.com/opensheaf/example-papers) and go through
every workflow, on every push and every week.

Python tools for [OpenSheaf](https://opensheaf.org) archives: archives of
scholarly documents kept as plain files (an OCFL 1.1 storage root with
DataCite metadata), checkable by anyone and combinable into collections. This
is the reference implementation of the
[specification](https://github.com/opensheaf/opensheaf.github.io), version 0.1 (draft).

The package is `opensheaf`; its command is `osheaf` (also installed as
`opensheaf`).

## Installation

```
pipx install "opensheaf[validate] @ git+https://github.com/opensheaf/opensheaf-py"
```

(or `pip install` in a virtual environment). Python 3.9 or later (PyYAML is installed with it). The extra
`validate` adds `jsonschema` and `ocfl-py`, with which `osheaf verify` also
validates the JSON files against the schemas and the storage root with an
independent OCFL validator. Depositing TeXmacs documents needs
[GNU TeXmacs](https://www.texmacs.org) (`TEXMACS_BIN`, by default the macOS
application).

## An archive

The quickest start is the template
[opensheaf/archive-template](https://github.com/opensheaf/archive-template):
a ready website, published with GitHub Pages. Or create one anywhere:

```
osheaf init my-papers --archive-id tag:example.org,2026:my-papers \
  --name "Papers of Jane Doe" --base-url https://example.org/papers/ --curator "Doe, Jane"
```

An archive is a folder with a configuration file `osheaf.json` (identifier,
name, address, curator, depositor, the website or the TeXmacs profile;
`osheaf help-config` describes it). The tools find it from the current folder
or from `--root`. They maintain:

- `ocfl/`: the storage root, one OCFL object per document, and the main
  collection;
- `opensheaf.json`: the discovery document;
- the website (appendix C): `index.html`, a landing page `paper/<id>/` per
  document (current version, every version in the order of the history,
  notices, files, DOI, the `citation_*` tags read by Google Scholar, JSON-LD,
  Signposting links) and `sitemap.xml`, from the templates in `templates/`
  (`{{name}}` placeholders; MathJax renders `$...$`);
- or, with the TeXmacs profile, `site/<id>/` (HTML versions of TeXmacs
  documents) and an index made from a TeXmacs template, with the same
  landing pages `paper/<id>/` and `sitemap.xml` as the website (from the
  archive's own `templates/paper.html`, if it has one).

## Commands

```
osheaf init FOLDER --archive-id URI --name NAME --base-url URL --curator "Family, Given"
osheaf deposit ID SOURCE --pdf PAPER.pdf --title T --author "Family, Given|Affiliation" ...
osheaf deposit ID SOURCE.tm --title T --author ...           (TeXmacs: typeset by the archive)
osheaf deposit ID --pdf PAPER.pdf --no-source REASON ...
osheaf deposit ... --stage VoR --agreement "the journal's publication terms"
osheaf notice ID --about N --text "..." [--file erratum.pdf]
osheaf withdraw ID --reason "..."
osheaf complete ID --version N --source paper.tex [--extra-source ...]
osheaf relicense ID --rights cc-by-4.0 --method "..."
osheaf relate ID --to arxiv:ID|doi:DOI [--relation IsIdenticalTo]
osheaf describe ID [--title T] [--abstract TEXT | --abstract-file F] [--keyword K ...] [--author A ...]
osheaf collect
osheaf accept ARCHIVE-URL ID --version vN [--as ID] [--stage VoR] [--agreement ...]
osheaf mirror ARCHIVE-URL ID [--licence-checked]
osheaf collection sync [ID] --from collection.yaml
osheaf collection update [ID]
osheaf index
osheaf verify [--remote]
osheaf zenodo ID [--production]
osheaf arxiv fetch DOWNLOADS --author AUTHOR-ID | ARXIV-ID ...
osheaf arxiv import DOWNLOADS [ARXIV-ID ...] [--update] [--versions v1,v3]
```

- **deposit** a document, or a new document version of it: any source (LaTeX,
  Markdown, ...) with its PDF (`--pdf`; other sources with `--extra-source`,
  the abstract with `--abstract` or `--abstract-file`), a PDF alone
  (`--no-source REASON`), or a TeXmacs source, typeset by the archive. Files
  are copied byte for byte. Dates follow the specification (`--available`, or
  `--created` for a version not public at the time; `--issued`), with
  `--stage` (NISO-JAV), `--changes`, and `--after N` for a version found
  later, which writes the history. A new version keeps the abstract, keywords
  and licence of the previous one unless they are given.
- **--from FILE.yaml** (deposit, relicense, relate, describe, init): the options from a
  YAML or JSON file, with the same names (`title`, `authors`, `abstract`,
  `extra-sources`, `available`, ...; paths relative to the file); a list
  makes several deposits in order, and the command line overrides the file.
  YAML is read with every value kept as text, so that nothing is converted
  silently (`2611.14296`, `2025-01-02` and `1.10` stay as written). The
  settings may also be `osheaf.yaml`. Example:

  ```yaml
  id: kpz-uniqueness
  source: paper.tex
  pdf: paper.pdf
  extra-sources: [refs.bib, {file: figures/fig1.pdf, path: figures/fig1.pdf}]
  title: Energy solutions of KPZ are unique
  authors:
    - Doe, Jane|Example University
    - {name: "Roe, Richard", affiliation: Another University}
  abstract: |
    We prove that energy solutions of the KPZ equation are unique.
  rights: cc-by-4.0
  available: 2015-08-31
  related: ["IsIdenticalTo:arxiv:1508.07764"]
  ```
- **notice**, **withdraw**: later statements about a version (an erratum, by
  a description-only version; notices stay in every later version) and the
  withdrawal of a document (the content stays; no new versions).
- **complete**: adds the sources of a version deposited without them
  (`--no-source`); its number stays.
- **collection sync / update**: curated collections, with members from this
  archive or any other (an `https://` address, or a local folder), in the
  curator's order, each pinned by the SHA-512 of an inventory and checked
  against the checksum file its archive publishes. `collection.yaml` gives
  the kind (section 10.1): `type: catalogue` (the default, with a message, for
  files without a type) pins each object at its head, and `update` follows
  the members with `follow: latest` to their new heads, whatever they hold (a
  withdrawal too), bringing up to date the mirrors held here; `type:
  selection` pins the revisions vetted (`revisions: [2, 3]`, document
  versions, or object versions such as `v4`), which `sync` writes exactly
  and `update` never changes: it reports the versions not vetted.
  A collection of the archive other than the main one is named by its
  identifier (`osheaf collection sync reading-list --from FILE`), and may be
  featured on the home page, before the main collection
  (`"featured": "reading-list"` under `index.html` in `osheaf.json`);
  `osheaf init --curated` makes an archive whose main collection itself is
  curated; `osheaf verify --remote` fetches every member and checks its pins,
  trying the mirrors listed in the member and in its archive's discovery
  document when the archive fails. See `osheaf collection --help` and the
  template [opensheaf/archive-template](https://github.com/opensheaf/archive-template).
- **accept** (a journal, a series): copies exactly one version of another
  archive's object (the version that was vetted) into a document of this
  archive, byte for byte, recording its source and pin in `object.json`
  (`external`, role `source`) and linking it from `datacite.json`. The
  authors' later versions change nothing; a correction is an editorial act:
  `accept` again with a later version (a new document version of the
  journal's document) or `notice`. Only the accepted version needs an open
  licence (or `--licence-checked`, with `--agreement` to record the authors'
  agreement). The journal's issue is a selection of these documents
  (`{archive: ., id: ..., revisions: [1]}`), and `verify --remote` compares
  each accepted copy with its source. A journal that typesets its own version
  of record deposits it instead (`deposit` with `--stage VoR`, its licence
  and `--agreement`).
- **mirror** (a library, a preservation copy): copies another archive's
  object, every version, each file checked against its digest, so that this
  archive serves it too; refused unless every version is under an open
  licence (CC BY, CC BY-SA, CC0, GPL), or `--licence-checked` says that
  redistribution is allowed. Run again, it copies the new versions only. The
  discovery document lists the copy with `mirrorOf`. `mirror: yes` on a
  member of `collection.yaml` mirrors it and lists the copy in the member's
  `mirrors`, and `collection update` keeps it up to date; `verify --remote`
  checks a member on its mirrors when its archive fails.
- **relicense**, **relate**: description-only versions (a new licence with the
  authors' agreement; a link to the same work elsewhere).
- **describe**: a description-only version correcting the title, the abstract
  (`--abstract` or `--abstract-file`), the keywords (`--keyword`, repeated,
  replacing the keywords; arXiv categories stay) or the authors (`--author`,
  repeated, as in a deposit, replacing the list); the other fields are kept,
  and a correction that changes nothing is refused.
- **collect**: a new version of the main collection, a catalogue,
  when a document has a new object version; members are ordered
  `issued-desc`, pin the head of their object and follow it, and the index
  shows their current versions.
- **index**: the discovery document and the readable index: the website, or
  the TeXmacs index (`index.tm`, exported to `index.html`) with the landing
  pages and the sitemap of the website. No `robots.txt` is written: an archive
  in a folder of a larger site adds `Sitemap: <baseUrl>sitemap.xml` to the
  site's own.
- **verify**: the checks of section 14 of the specification (identifiers,
  inventories and digests, `object.json` and `datacite.json`, numbering of
  document versions, history and notices, collections, their kinds and their
  pins, mirrors; with `--remote`, members of other archives and the sources
  of accepted copies).
- **zenodo**: the Zenodo binding (appendix A): deposits the current document
  version (on the sandbox, on a copy of the object, unless `--production`).
  Tokens are read from the macOS keychain (`zenodo-token`,
  `zenodo-sandbox-token`).
- **arxiv fetch / import**: download papers from arXiv (every version, with
  each version's licence and comments; one request every 3 seconds) and
  import them, one document version per arXiv version, with arXiv's files
  byte for byte. Object identifiers come from `identifiers.json` in the
  downloads folder, chosen by the depositor. The tools only append versions:
  a version that is not on arXiv is placed by importing up to the arXiv
  version before it, depositing it, and continuing with `--update`.

## A literate program

The source of these tools is a literate program: the Markdown documents in
[literate/](literate/index.md) explain the code in the order in which it is
best understood, and the Python files under `src/` and `tests/` are
*tangled* out of them (in the style of Kragen Sitaker's
[handaxeweb](https://github.com/kragen/peg-bootstrap/blob/master/handaxeweb.md)).
The tangled files are kept in the repository, so the package installs as
usual. Tangling and weaving are done by
[opensheaf-literate](https://github.com/opensheaf/literate) (the `literate`
command; its own literate program is at
[opensheaf.org/literate](https://opensheaf.org/literate/)), pinned in
`requirements-literate.txt` and configured by `literate.json`. To change
the code, edit the documents (never the tangled files: see
[AGENTS.md](AGENTS.md)) and run

```
pip install -r requirements-literate.txt   # once
literate tangle         # write the files out of literate/
literate tangle --check # nothing differs (what the continuous integration checks)
literate weave          # the website, in site/
```

The website is published at
[opensheaf.org/opensheaf-py](https://opensheaf.org/opensheaf-py/).
`literate tangle --where FILE:LINE` tells which line of which document a
line of a tangled file comes from.

## The first archive

[mgubi.org/papers](https://mgubi.org/papers/)
([repository](https://github.com/mgubi/papers)) is kept with these tools.

## Licence

GNU General Public License, version 3 or later. The JSON Schemas in
`src/opensheaf/schemas/` are those of the specification, dedicated to the
public domain under CC0 1.0. The OpenSheaf symbol, `literate/opensheaf-symbol.svg`
(used by the woven website), is licensed under CC BY 4.0, and its use as a mark follows
the OpenSheaf
[trademark policy](https://github.com/opensheaf/opensheaf.github.io/blob/main/TRADEMARKS.md).
