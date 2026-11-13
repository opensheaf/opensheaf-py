# opensheaf-py

Python tools for [OpenSheaf](https://opensheaf.org) archives: archives of
scholarly documents kept as plain files (an OCFL 1.1 storage root with
DataCite metadata), checkable by anyone and combinable into collections. This
is the reference implementation of the
[specification](https://github.com/opensheaf/opensheaf), version 0.1 (draft).

The package is `opensheaf`; its command is `osheaf` (also installed as
`opensheaf`).

## Installation

```
pipx install "opensheaf[validate] @ git+https://github.com/opensheaf/opensheaf-py"
```

(or `pip install` in a virtual environment). Python 3.9 or later. The extra
`validate` adds `jsonschema` and `ocfl-py`, with which `osheaf verify` also
validates the JSON files against the schemas and the storage root with an
independent OCFL validator. Depositing TeXmacs documents needs
[GNU TeXmacs](https://www.texmacs.org) (`TEXMACS_BIN`, by default the macOS
application).

## An archive

An archive is a folder with a configuration file `osheaf.json` (identifier,
name, address, curator, depositor, and optionally the TeXmacs profile and the
index template; `osheaf help-config` describes it). The tools find it from
the current folder or from `--root`. They maintain:

- `ocfl/`: the storage root, one OCFL object per document, and the main
  collection;
- `opensheaf.json`: the discovery document;
- `site/<id>/`: the HTML versions of documents with TeXmacs sources;
- `index.tm`, `index.html`: a readable index, from a TeXmacs template of the
  archive (optional).

## Commands

```
osheaf deposit ID SOURCE.tm --title T --author "Family, Given|Affiliation" ...
osheaf relicense ID --rights cc-by-4.0 --method "..."
osheaf relate ID --to arxiv:ID|doi:DOI [--relation IsIdenticalTo]
osheaf collect
osheaf index
osheaf verify
osheaf zenodo ID [--production]
osheaf arxiv fetch DOWNLOADS --author AUTHOR-ID | ARXIV-ID ...
osheaf arxiv import DOWNLOADS [ARXIV-ID ...] [--update] [--versions v1,v3]
```

- **deposit** a TeXmacs document, or a new document version of it: the source
  is copied byte for byte, the PDF typeset with TeXmacs, the HTML version
  exported. Dates follow the specification (`--available`, or `--created` for
  a version not public at the time; `--issued`), with `--stage` (NISO-JAV),
  `--changes`, and `--after N` for a version found later, which writes the
  history.
- **relicense**, **relate**: description-only versions (a new licence with the
  authors' agreement; a link to the same work elsewhere).
- **collect**: a new version of the main collection when a document has a new
  current version; members are ordered `issued-desc` and pin the object
  version holding the current version.
- **index**: the discovery document and the readable index.
- **verify**: the checks of section 14 of the specification (identifiers,
  inventories and digests, `object.json` and `datacite.json`, numbering of
  document versions, history and notices, collections and their pins).
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

## The first archive

[mgubi.org/papers](https://mgubi.org/papers/)
([repository](https://github.com/mgubi/papers)) is kept with these tools.

## Licence

GNU General Public License, version 3 or later. The JSON Schemas in
`src/opensheaf/schemas/` are those of the specification, dedicated to the
public domain under CC0 1.0.
